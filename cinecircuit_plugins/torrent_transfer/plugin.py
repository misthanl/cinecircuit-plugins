from typing import Any
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
from .path_mapping import mapped_save_path


class TorrentTransferPlugin(PluginBase):
    manifest = PluginManifest(
        id="torrent-transfer",
        name="转移做种",
        version="1.0.2",
        entrypoint="plugin:TorrentTransferPlugin",
        description="将已完成的种子转移到其他下载器，复用原有数据做种。",
        icon="mdi-file-move-outline",
        api_version=2,
        permissions=(
            P.DOWNLOADER_READ,
            P.DOWNLOADER_EXPORT,
            P.DOWNLOADER_ADD,
            P.DOWNLOADER_RECHECK,
            P.DOWNLOADER_RESUME,
            P.DOWNLOADER_DELETE_TASK,
            P.NOTIFICATION_SEND,
        ),
        capabilities=("scheduled_task", "statistics_page", "site_automation"),
        jobs=(PluginJobSpec(name="transfer", interval_seconds=60, timeout_seconds=3600),),
        config_schema=schema(),
        frontend_module="frontend.js",
    )

    async def run(self, context):
        sdk = context.sdk.require("torrents", min_version=1)
        scan = due(context)
        checking = await check_queue(context, sdk) if context.config.get("enabled") or scan else {}
        if not scan:
            return {"status": "idle", "checking": checking}
        result = await self.transfer(context, sdk)
        await notify(context, "转移做种", result)
        return {**result, "checking": checking}

    def selected(self, task, config):
        if not complete(task) or excluded(task, config):
            return False
        tags = labels(task.get("tags"))
        if not tags and not config.get("transferemptylabel", False):
            return False
        if not labels(config.get("includelabels")).issubset(tags):
            return False
        categories = labels(config.get("includecategory"))
        return not categories or task.get("category") in categories

    async def transfer(self, context, sdk):
        config = context.config
        source_id = str(config.get("fromdownloader") or "")
        target_id = str(config.get("todownloader") or "")
        if not source_id or not target_id or source_id == target_id:
            raise ValueError("请选择不同的源下载器和目标下载器")
        result: dict[str, Any] = {"status": "completed", "added": 0, "skipped": 0, "failed": 0}
        for source in await inventory(sdk, source_id):
            if not self.selected(source, config):
                continue
            key = key_for(source_id, source["hash"], source["added_on"], target_id)
            previous = context.items.get(key)
            if previous and previous["status"] not in ("failed", "missing"):
                result["skipped"] += 1
                continue
            await self.transfer_one(context, sdk, source, target_id, key, result)
        return result

    async def handle_api(self, request, context):
        if request.action == "statistics" and request.method == "GET":
            return await statistics(context)
        if request.action == "preview" and request.method == "POST":
            sdk = context.sdk.require("torrents", min_version=1)
            return {
                "items": [
                    payload_for(t)
                    for t in await inventory(sdk, context.config.get("fromdownloader"))
                    if self.selected(t, context.config)
                ]
            }
        if request.action == "check" and request.method == "POST":
            return await check_queue(context, context.sdk.require("torrents", min_version=1))
        raise KeyError("不支持的插件操作")

    async def transfer_one(self, context, sdk, source, target_id, key, result):
        try:
            if await self.skip_duplicate(context, sdk, source, target_id, key):
                result["skipped"] += 1
                return
            await self.submit_one(context, sdk, source, target_id, key, result)
        except Exception as error:
            # Preserve a queued receipt if submission succeeded but checking failed.
            current = context.items.get(key)
            if current and current["status"] in ("submitted", "checking", "ready"):
                record(
                    context,
                    key,
                    current["status"],
                    current["payload"],
                    {**current["result"], "error": error_text(error)},
                )
            else:
                record(context, key, "failed", payload_for(source), {"error": error_text(error)})
            result["failed"] += 1

    async def skip_duplicate(self, context, sdk, source, target_id, key):
        config = context.config
        source_id = source["downloader_id"]
        existing = await sdk.inspect(target_id, source["hash"])
        if existing:
            if config.get("deleteduplicate") and complete(existing):
                await sdk.operate(source_id, source["hash"], "remove", added_on=source["added_on"])
            record(
                context,
                key,
                "duplicate",
                payload_for(source),
                {"target_downloader": target_id},
            )
            return True
        return False

    async def submit_one(self, context, sdk, source, target_id, key, result):
        config = context.config
        source_id = source["downloader_id"]
        target_path = mapped_save_path(source["save_path"], config)
        exported = await sdk.export(
            source_id,
            source["hash"],
            added_on=source["added_on"],
            torrent_directory=config.get("fromtorrentpath") or "",
        )
        tags = labels(config.get("add_torrent_tags"))
        if config.get("remainoldtag"):
            tags |= labels(source.get("tags"))
        receipt = await sdk.submit(
            target_id,
            exported["torrent_ref"],
            save_path=target_path,
            tags=sorted(tags),
            category=source.get("category", "") if config.get("remainoldcat") else "",
            skip_checking=bool(config.get("skipverify")),
            reuse_save_path=True,
        )
        if receipt["status"] == "already_exists":
            record(context, key, "duplicate", payload_for(source), {"receipt": receipt})
            result["skipped"] += 1
            return
        await queue(
            context,
            sdk,
            key,
            source,
            receipt,
            auto_start=config.get("autostart"),
            remove_source=config.get("deletesource"),
            skip_checking=bool(config.get("skipverify") and receipt.get("kind") == "qbittorrent"),
        )
        result["added"] += 1
