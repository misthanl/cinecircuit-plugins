"""Cross-storage policy and journaling; all remote operations use the host SDK."""

from hashlib import sha256
import json
from pathlib import PurePosixPath
import time

from app.modules.plugins.contracts import PluginBase, PluginManifest, PluginJobSpec
from app.modules.plugins.permissions import PluginPermission

from .schedule import prepare_triggers
from .statistics import snapshot
from . import manual


class CloudCopyPlugin(PluginBase):
    manifest = PluginManifest(
        id="cloud-copy",
        name="跨网盘复制",
        version="1.0.0",
        api_version=2,
        entrypoint="plugin:CloudCopyPlugin",
        icon="mdi-content-copy",
        description="通过统一存储能力复制文件，支持秒传、校验后秒传及可选服务器中转。保留源文件。",
        permissions=(
            PluginPermission.STORAGE_READ,
            PluginPermission.STORAGE_COPY,
            PluginPermission.STORAGE_READ_CONTENT,
            PluginPermission.ORGANIZER_SUBMIT,
            PluginPermission.SYNC_SUBMIT,
        ),
        capabilities=("scheduled_task", "storage_tool", "plugin_page"),
        frontend_module="frontend.js",
        navigation={
            "title": "跨网盘复制",
            "icon": "mdi-content-copy",
            "section": "tools",
            "order": 66,
            "visibility_config_key": "show_sidebar_nav",
        },
        events=(),
        jobs=(PluginJobSpec(name="copy", interval_seconds=60, timeout_seconds=3600),),
        config_schema={
            "description_display": "hidden",
            "layout": {"columns": 2, "row_gap": 14, "column_gap": 16},
            "fields": [
                {
                    "key": "full_scan_enabled",
                    "input_type": "switch",
                    "label": "定时全量",
                    "default": False,
                },
                {
                    "key": "full_scan_interval_minutes",
                    "input_type": "number",
                    "label": "全量执行间隔（分钟）",
                    "default": 60,
                },
                {
                    "key": "life_events_enabled",
                    "input_type": "switch",
                    "label": "生活事件",
                    "default": False,
                },
                {
                    "key": "life_events_since",
                    "input_type": "number",
                    "label": "事件起始时间",
                    "default": 0,
                    "visible": False,
                },
                {
                    "key": "show_sidebar_nav",
                    "input_type": "switch",
                    "label": "开启侧边栏菜单",
                    "default": True,
                },
                {
                    "key": "source",
                    "input_type": "resource_select",
                    "resource_kind": "storage",
                    "label": "源网盘",
                    "required_capabilities": ["file_copy_source"],
                    "default": None,
                },
                {
                    "key": "source_root",
                    "input_type": "cloud_directory",
                    "parent_field": "source",
                    "label": "源目录",
                    "default": "0",
                },
                {
                    "key": "target",
                    "input_type": "resource_select",
                    "resource_kind": "storage",
                    "label": "目标网盘",
                    "required_capabilities": ["file_copy_target"],
                    "default": None,
                },
                {
                    "key": "target_root",
                    "input_type": "cloud_directory",
                    "parent_field": "target",
                    "label": "目标目录",
                    "default": "0",
                },
                {
                    "key": "policy",
                    "input_type": "select",
                    "label": "复制策略",
                    "default": "metadata",
                    "options": [
                        {"value": "metadata", "label": "仅使用已有校验信息"},
                        {"value": "verify", "label": "允许读取源文件验证秒传"},
                        {"value": "relay", "label": "允许服务器中转上传"},
                    ],
                },
                {
                    "key": "temporary_directory",
                    "input_type": "local_directory",
                    "label": "临时目录",
                    "default": "",
                },
                {
                    "key": "max_gib",
                    "input_type": "number",
                    "label": "单文件临时空间上限（GiB）",
                    "default": 10,
                },
                {
                    "key": "followup",
                    "input_type": "select",
                    "label": "复制完成后",
                    "default": "none",
                    "options": [
                        {"value": "none", "label": "仅复制"},
                        {"value": "organize", "label": "交接整理"},
                        {"value": "sync", "label": "同步本批文件"},
                    ],
                },
            ],
        },
    )

    @staticmethod
    def settings(context, *, validate_policy=True):
        config = context.config
        if validate_policy:
            manual.require_temporary_directory(config)
        source, target = str(config.get("source") or ""), str(config.get("target") or "")
        if not source or not target:
            raise ValueError("请选择源网盘与目标网盘")
        root, destination = (
            str(config.get("source_root") or "0"),
            str(config.get("target_root") or "0"),
        )
        if source == target and root == destination:
            raise ValueError("源目录与目标目录不能相同")
        identity = sha256(json.dumps([source, root, target, destination]).encode()).hexdigest()[:24]
        return source, root, target, destination, identity

    async def run(self, context):
        manual_result = await manual.run_one(self, context)
        if context.trigger != "manual" and (
            not context.config.get("source") or not context.config.get("target")
        ):
            return manual_result or {"status": "idle", "reason": "disabled"}
        source, root, target, destination, rule = self.settings(context)
        state = context.state.scoped("copy-" + rule)
        progress = state.get("progress") or {"folders": [], "pending": [], "last_scan": 0}
        storage = context.sdk.require("storage", min_version=2)
        await prepare_triggers(context, state, progress, storage, source, root)
        if state.get("paused", False):
            return manual_result or {"status": "idle", "reason": "paused"}
        if (
            not progress["folders"]
            and not progress["pending"]
            and not state.get("rescan_requested", False)
            and not progress.get("events_active")
        ):
            return manual_result or {"status": "idle", "reason": "no_trigger"}
        same_account = await storage.same_account(source, target)
        if same_account and root == destination:
            raise ValueError("源目录与目标目录属于同一账号且相同")
        await self.collect_changes(
            context, storage, state, progress, source, root, same_account, destination
        )
        await self.scan_page(storage, state, progress, source, target, destination, same_account)
        processed = 0
        while progress["pending"] and processed < 20 and not state.get("paused", False):
            item = progress["pending"][0]
            await self.copy_one(context, storage, state, source, target, destination, item)
            progress["pending"].pop(0)
            state.set("progress", progress)
            processed += 1
        if not progress["pending"] and not progress["folders"] and progress.get("scanning"):
            progress["last_scan"] = time.time()
            progress["scanning"] = False
            progress["manual_active"] = False
        state.set("progress", progress)
        return {
            "status": "success",
            "processed": processed,
            "pending": len(progress["pending"]),
            "directories_remaining": len(progress["folders"]),
            "results": [manual_result] if manual_result else [],
        }

    async def collect_changes(
        self, context, storage, state, progress, source, root, same_account, destination
    ):
        # Save page contents before performing remote writes; replay uses content records.
        if not progress["folders"] and not progress["pending"]:
            if state.get("rescan_requested", False):
                progress["folders"] = [{"id": root, "prefix": "", "cursor": None}]
                progress["scanning"] = True
                progress["manual_active"] = True
                state.set("progress", progress)
                state.set("rescan_requested", False)
            elif progress.get("events_active"):
                batch = await storage.changes(source)
                for event in batch.get("events", []):
                    await self.queue_event(
                        storage, progress, source, root, same_account, destination, event
                    )
                state.set("progress", progress)
                if batch.get("supported"):
                    await storage.acknowledge_changes(source)

    async def queue_event(self, storage, progress, source, root, same_account, destination, event):
        if int(event.get("event_time") or 0) < progress.get("events_since", 0):
            return
        if event.get("action") == "delete":
            return
        if event.get("file_id"):
            item = await storage.file_relative_to(source, root, str(event["file_id"]))
            if item and not (
                same_account
                and await storage.file_relative_to(source, destination, str(event["file_id"]))
            ):
                if event.get("is_dir"):
                    progress["folders"].append(
                        {
                            "id": str(event["file_id"]),
                            "prefix": item["relative_path"],
                            "cursor": None,
                        }
                    )
                else:
                    progress["pending"].append(item)

    async def scan_page(self, storage, state, progress, source, target, destination, same_account):
        if not progress["pending"] and progress["folders"]:
            folder = progress["folders"][0]
            if same_account and str(folder["id"]) == destination:
                progress["folders"].pop(0)
            else:
                page = await storage.file_page(source, folder["id"], folder["cursor"])
                children = []
                for item in page["items"]:
                    path = str(PurePosixPath(folder["prefix"]) / item["name"])
                    if item["directory"]:
                        children.append({"id": item["file_id"], "prefix": path, "cursor": None})
                    else:
                        progress["pending"].append({**item, "relative_path": path})
                if page["cursor"] is None:
                    progress["folders"].pop(0)
                else:
                    if page["cursor"] == folder["cursor"]:
                        raise ValueError("扫描分页没有前进")
                    folder["cursor"] = page["cursor"]
                # Visit children before fetching the next parent page so wide
                # directory trees do not accumulate their entire frontier in state.
                progress["folders"][0:0] = children
            state.set("progress", progress)

    @staticmethod
    def copy_version(context, item, path):
        return sha256(
            json.dumps(
                [
                    item.get("size"),
                    item.get("checksums"),
                    str(path),
                    context.config.get("policy", "metadata"),
                    context.config.get("followup", "none"),
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()

    @staticmethod
    async def submit_copy(context, storage, source, target, parent, target_name, item):
        temporary_directory = manual.require_temporary_directory(context.config)
        return await storage.copy_file(
            source,
            item["file_id"],
            target,
            parent,
            target_name,
            policy=context.config.get("policy", "metadata"),
            max_bytes=int(float(context.config.get("max_gib") or 10) * 1024**3),
            temporary_directory=temporary_directory,
            expected={"size": item.get("size"), "checksums": item.get("checksums", {})},
        )

    async def copy_one(self, context, storage, state, source, target, destination, item):
        path = PurePosixPath(item["relative_path"])
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("源文件相对路径无效")
        identity = sha256(str(item["file_id"]).encode()).hexdigest()
        key = "records-" + identity[:3]
        records = state.get(key, {})
        version = self.copy_version(context, item, path)
        previous = records.get(identity, {})
        if previous.get("version") == version and previous.get("status") == "copied":
            await self.finish_handoff(context, storage, state, key, records, identity, target)
            return
        if previous.get("version") == version and previous.get("status") in (
            "completed",
            "uncertain",
            "conflict",
            "skipped",
        ):
            return
        parent = destination
        for name in path.parts[:-1]:
            parent = await storage.ensure_directory(target, parent, name)
        # A crash after submission must not cause blind replay. Explicit retry
        # checks the target before writing again through the SDK.
        records[identity] = self.pending_record(previous, version, path, parent, item)
        state.set(key, records)
        result = await self.copy_with_conflict_name(
            context,
            storage,
            state,
            records,
            identity,
            previous,
            source,
            target,
        )
        await self.record_copy_result(
            context, storage, state, key, records, identity, target, result
        )

    @staticmethod
    def pending_record(previous, version, path, parent, item):
        recovering = previous.get("recovering") and previous.get("version") == version
        return {
            "version": version,
            "status": "uncertain",
            "path": str(path),
            "target_name": previous.get("target_name", path.name) if recovering else path.name,
            "updated_at": time.time(),
            "parent_id": parent,
            "source_item": dict(item),
        }

    async def copy_with_conflict_name(
        self,
        context,
        storage,
        state,
        records,
        identity,
        previous,
        source,
        target,
    ):
        record = records[identity]
        key = "records-" + identity[:3]
        parent, target_name, item = (
            record["parent_id"],
            record["target_name"],
            record["source_item"],
        )
        result = await self.submit_copy(context, storage, source, target, parent, target_name, item)
        if result["status"] == "conflict" and not previous.get("recovering"):
            path = PurePosixPath(record["path"])
            alternate = f"{path.stem} [{identity[:8]}-{record['version'][:8]}]{path.suffix}"
            records[identity]["target_name"] = alternate
            state.set(key, records)
            result = await self.submit_copy(
                context, storage, source, target, parent, alternate, item
            )
        return result

    async def record_copy_result(
        self, context, storage, state, key, records, identity, target, result
    ):
        records[identity] = {
            **records[identity],
            "status": result["status"],
            "file_id": result.get("file_id"),
            "method": result.get("method"),
            "reason": result.get("reason"),
            "updated_at": time.time(),
        }
        if result["status"] == "completed" and context.config.get("followup", "none") != "none":
            records[identity]["status"] = "copied"
        state.set(key, records)
        if records[identity]["status"] == "copied":
            await self.finish_handoff(context, storage, state, key, records, identity, target)

    async def finish_handoff(self, context, storage, state, key, records, identity, target):
        record = records[identity]
        if context.config.get("followup", "none") == "none":
            record["status"] = "completed"
            state.set(key, records)
            return
        result = await storage.handoff_copy(
            target,
            record["parent_id"],
            record["file_id"],
            identity + record["version"],
            context.config.get("followup", "none"),
        )
        record["handoff"] = result["status"]
        record["status"] = "completed"
        state.set(key, records)

    async def handle_api(self, request, context):
        if (
            request.action in ("record-retry", "record-delete", "batch-delete", "batch-retry")
            and request.method == "POST"
        ):
            from .record_actions import action

            return await action(self, request, context)
        if request.action in ("browse", "batches", "batch", "batch-retry", "submit"):
            return await manual.api(self, request, context)
        if request.action == "options":
            options = await context.sdk.require("storage", min_version=2).configurations()
            return {
                **options,
                "temporary_directory_configured": bool(
                    str(context.config.get("temporary_directory") or "").strip()
                ),
            }
        if request.action == "status":
            return await snapshot(self, request, context)
        _, _, _, _, rule = self.settings(context)
        state = context.state.scoped("copy-" + rule)
        if request.action == "rescan" and request.method == "POST":
            state.set("rescan_requested", True)
            state.set("paused", False)
            return {"queued": True}
        if request.action in ("pause", "resume") and request.method == "POST":
            state.set("paused", request.action == "pause")
            return {"paused": request.action == "pause"}
        if request.action == "retry" and request.method == "POST":
            identity = str(request.payload.get("identity") or "")
            if len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
                raise ValueError("复制记录标识无效")
            key = "records-" + identity[:3]
            records = state.get(key, {})
            if identity not in records:
                raise ValueError("复制记录不存在")
            records[identity]["recovering"] = records[identity]["status"] == "uncertain" or records[
                identity
            ].get("recovering", False)
            records[identity]["status"] = "retry"
            state.set(key, records)
            state.set("rescan_requested", True)
            state.set("paused", False)
            return {"queued": True}
        raise KeyError("未知操作")

    async def on_event(self, event, context):
        return {"status": "skipped", "reason": "use_configured_triggers"}
