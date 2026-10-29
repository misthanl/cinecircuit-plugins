from typing import Any
import re
from time import time
from urllib.parse import urlsplit
from app.modules.plugins.contracts import PluginBase, PluginManifest, PluginJobSpec
from app.modules.plugins.permissions import PluginPermission as P
from .._shared.seeding import (
    complete,
    excluded,
    labels,
    inventory,
    key_for,
    payload_for,
    record,
    error_text,
    due,
    queue,
    check_queue,
    statistics,
    notify,
)
from .schema import schema
from .client import IyuuClient


class IyuuAutoSeedPlugin(PluginBase):
    disabled_read_actions = ("statistics",)

    manifest = PluginManifest(
        id="iyuu-autoseed",
        name="IYUU 辅种",
        version="1.0.3",
        entrypoint="plugin:IyuuAutoSeedPlugin",
        description="通过 IYUU 查找其他站点的同源种子，复用已有数据校验做种。",
        icon="mdi-source-branch",
        api_version=2,
        permissions=(
            P.DOWNLOADER_READ,
            P.DOWNLOADER_ADD,
            P.DOWNLOADER_RECHECK,
            P.DOWNLOADER_RESUME,
            P.SITE_READ,
            P.NOTIFICATION_SEND,
        ),
        capabilities=("scheduled_task", "statistics_page", "site_automation"),
        jobs=(PluginJobSpec(name="reseed", interval_seconds=60, timeout_seconds=3600),),
        config_schema=schema(),
        frontend_module="frontend.js",
    )
    client_factory = IyuuClient

    def caches(self, context):
        return [context.state.scoped("iyuu-" + name) for name in ("success", "error", "permanent")]

    async def run(self, context):
        sdk = context.sdk.require("torrents", min_version=1)
        if context.sdk.require("configuration", min_version=1).consume_switch("clearcache"):
            for scope in self.caches(context):
                scope.clear()
        scan = due(context)
        checking = await check_queue(context, sdk) if context.config.get("enabled") or scan else {}
        if not scan:
            return {"status": "idle", "checking": checking}
        result = await self.reseed(context, sdk)
        await notify(context, "IYUU 辅种", result)
        return {**result, "checking": checking}

    def cached(self, context, key):
        success, error, permanent = self.caches(context)
        return bool(
            success.get(key)
            or permanent.get(key)
            or (error.get(key) or {}).get("retry_at", 0) > time()
        )

    def cache(self, context, key, status):
        success, error, permanent = self.caches(context)
        scope = success if status == "success" else permanent if status == "permanent" else error
        previous = scope.get(key) or {}
        count = int(previous.get("attempts", 0)) + 1
        scope.set_cache(
            key,
            {"attempts": count, "retry_at": time() + min(3600, 60 * 2 ** min(count - 1, 6))},
            prefix="",
            max_entries=10000,
            max_bytes=4 * 1024**2,
            ttl_seconds=10 * 365 * 86400,
        )

    async def site_map(self, context, sdk, client):
        descriptors = (await sdk.sites())["items"]
        catalog = (await context.sites.supported_catalog())["items"]
        selected = set(context.config.get("sites") or [])
        result = {}

        def host(value):
            return (urlsplit(value).hostname or "").lower().removeprefix("www.")

        for remote in client.sites:
            domain = host(remote.get("base_url") or "")
            for local in descriptors:
                if not local["enabled"] or (selected and local["id"] not in selected):
                    continue
                aliases = {local["host"].lower().removeprefix("www.")}
                for resource in catalog:
                    if resource.get("site_id") == local["id"]:
                        aliases |= {
                            v.lower().removeprefix("www.") for v in resource.get("domains", [])
                        }
                if domain and domain in aliases:
                    template = str(remote.get("download_page") or "")
                    parsed = urlsplit(template)
                    if parsed.netloc:
                        template = (
                            (parsed.path + "?" + parsed.query) if host(template) in aliases else ""
                        )
                    result[str(remote["id"])] = {**local, "download_template": template.lstrip("/")}
                    break
        return result

    async def reseed(self, context, sdk):
        config = context.config
        source_ids = config.get("downloaders") or []
        target = config.get("auto_downloader") or ""
        if not isinstance(source_ids, list) or not source_ids:
            raise ValueError("请选择来源下载器")
        if target and target in source_ids:
            raise ValueError("主辅分离下载器不能同时作为来源下载器")
        client = self.client_factory(config.get("token"))
        await client.initialize()
        site_map = await self.site_map(context, sdk, client)
        result: dict[str, Any] = {
            "status": "completed",
            "added": 0,
            "skipped": 0,
            "failed": 0,
            "matched": 0,
        }
        for source_id in dict.fromkeys(source_ids):
            candidates = [
                t
                for t in await inventory(sdk, source_id)
                if complete(t)
                and not excluded(t, config)
                and float(t.get("size") or 0) >= float(config.get("size") or 0) * 1024**3
            ]
            for offset in range(0, len(candidates), 200):
                batch = candidates[offset : offset + 200]
                await self.process_batch(
                    context, sdk, client, source_id, target, batch, site_map, result
                )
        return result

    async def seed_one(self, context, sdk, source, target, site, seed, result):
        identity = str(seed["info_hash"]).lower()
        key = key_for(target, identity)
        if self.cached(context, key):
            result["skipped"] += 1
            return
        existing = await sdk.inspect(target, identity)
        if existing:
            record(context, key, "duplicate", payload_for(source), {"target_hash": identity})
            result["skipped"] += 1
            return
        try:
            exported = await self.matched_torrent(sdk, source, site, seed, identity)
            receipt = await self.submit_matched(context, sdk, source, target, site, exported)
            config = context.config
            if receipt["status"] == "already_exists":
                record(context, key, "duplicate", payload_for(source), {"receipt": receipt})
                result["skipped"] += 1
                return
            self.cache(context, key, "success")
            skip = bool(config.get("skipverify") and receipt.get("kind") == "qbittorrent")
            await queue(
                context,
                sdk,
                key,
                source,
                receipt,
                auto_start=not skip or config.get("auto_start"),
                skip_checking=skip,
            )
            result["added"] += 1
        except Exception as error:
            current = context.items.get(key)
            if not current or current["status"] not in ("submitted", "checking", "ready"):
                record(
                    context,
                    key,
                    "failed",
                    payload_for(source),
                    {"error": error_text(error), "target_hash": identity},
                )
            self.cache(
                context, key, "permanent" if re.search(r"\b(?:404|410)\b", str(error)) else "error"
            )
            result["failed"] += 1

    async def handle_api(self, request, context):
        if request.action == "statistics" and request.method == "GET":
            return await statistics(context)
        if request.action == "clear-cache" and request.method == "POST":
            return {"cleared": sum(scope.clear() for scope in self.caches(context))}
        if request.action == "check" and request.method == "POST":
            return await check_queue(context, context.sdk.require("torrents", min_version=1))
        raise KeyError("不支持的插件操作")

    async def process_batch(self, context, sdk, client, source_id, target, batch, site_map, result):
        by_hash = {t["hash"].lower(): t for t in batch}
        try:
            matches = await client.query(list(by_hash))
        except Exception as error:
            record(
                context,
                "batch-" + key_for(source_id, list(by_hash)),
                "failed",
                {"name": "IYUU 批量查询"},
                {"error": error_text(error)},
            )
            result["failed"] += len(batch)
            return
        if not isinstance(matches, dict):
            result["failed"] += len(batch)
            return
        for source_hash, group in matches.items():
            source = by_hash.get(source_hash.lower())
            if not source or not isinstance(group, dict):
                continue
            targets = group.get("torrent") or []
            targets = targets if isinstance(targets, list) else [targets]
            for seed in targets:
                if not isinstance(seed, dict):
                    continue
                site = site_map.get(str(seed.get("sid")))
                identity = str(seed.get("info_hash") or "").lower()
                if not site or not re.fullmatch(r"[a-f0-9]{40}", identity):
                    continue
                result["matched"] += 1
                await self.seed_one(context, sdk, source, target or source_id, site, seed, result)

    async def matched_torrent(self, sdk, source, site, seed, identity):
        template = str(site.get("download_template") or "").replace("{}", str(seed["torrent_id"]))
        exported = await sdk.site_torrent(
            site["id"],
            str(seed["torrent_id"]),
            expected_hash=identity,
            detail_path=f"details.php?id={seed['torrent_id']}",
            download_path=template,
        )
        # Exact relative paths and sizes are required before a paused submission.
        original = await sdk.inspect(
            source["downloader_id"],
            source["hash"],
            added_on=source["added_on"],
            include_files=True,
        )
        if not original or not complete(original):
            raise ValueError("来源任务已变化或不再完整")

        def paths(files):
            return {(f["name"], int(f["size"])) for f in files}

        if paths(original.get("files", [])) != paths(exported["files"]):
            raise ValueError("候选种子的文件路径或大小与已有数据不一致")
        return exported

    async def submit_matched(self, context, sdk, source, target, site, exported):
        config = context.config
        tags = labels(config.get("labelsafterseed") or "辅种")
        if config.get("addhosttotag"):
            tags.add(site["name"])
        category = (
            (source.get("category") if config.get("auto_category") else "")
            or config.get("categoryafterseed")
            or ""
        )
        receipt = await sdk.submit(
            target,
            exported["torrent_ref"],
            save_path=source["save_path"],
            tags=sorted(tags),
            category=category,
            skip_checking=bool(config.get("skipverify")),
            reuse_save_path=config.get("reuse_save_path", True),
        )
        return receipt
