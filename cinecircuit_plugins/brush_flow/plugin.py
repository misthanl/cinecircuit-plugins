from __future__ import annotations

import hashlib
import inspect
from typing import Any

from app.modules.plugins.contracts import (
    PluginApiRequest,
    PluginBase,
    PluginContext,
    PluginManifest,
    PluginJobSpec,
)
from app.modules.plugins.permissions import PluginPermission
from .statistics import build_statistics, record_execution
from .cleanup import check_downloads
from .selection import matches
from .subscription_matching import load_index
from .task_settings import task_defaults, due_tasks, task_capacity, intake_allowed
from .task_limits import transfer_limits, volume_remaining, size_bytes, owned_downloads


class SiteTrafficPlugin(PluginBase):
    """集中管理站点流量任务、选种规则与下载器调度。"""

    manifest = PluginManifest(
        entrypoint="plugin:SiteTrafficPlugin",
        id="brush-flow",
        name="站点刷流",
        version="1.0.0",
        description="按站点和规则自动选种、下载与删种。",
        icon="mdi-swap-vertical",
        permissions=(
            PluginPermission.SITE_READ,
            PluginPermission.SUBSCRIPTION_READ,
            PluginPermission.DOWNLOADER_READ,
            PluginPermission.DOWNLOADER_ADD,
            PluginPermission.DOWNLOADER_PAUSE,
            PluginPermission.DOWNLOADER_DELETE_TASK,
            PluginPermission.DOWNLOADER_DELETE_FILES,
            PluginPermission.NOTIFICATION_SEND,
        ),
        capabilities=("scheduled_task", "site_rss", "download_controller"),
        api_version=2,
        jobs=(PluginJobSpec(name="tasks", interval_seconds=60),),
        frontend_module="frontend.js",
        config_schema={
            "editor_width": 920,
            "editor_height": 640,
            "description_display": "hidden",
            "layout": {"columns": 2, "row_gap": 14, "column_gap": 16},
            "fields": [
                {
                    "key": "enabled",
                    "input_type": "switch",
                    "label": "启用刷流任务",
                    "default": True,
                    "description": "开启后按任务周期自动选种；关闭后不会新增下载。",
                    "section": "general",
                },
                {
                    "key": "notification_enabled",
                    "input_type": "switch",
                    "label": "发送通知",
                    "default": False,
                    "description": "开启后发送每次刷流任务的执行结果。",
                    "section": "general",
                },
                {
                    "key": "cron",
                    "input_type": "cron",
                    "label": "执行周期",
                    "default": "",
                    "placeholder": "5位cron表达式，留空自动",
                    "description": "留空使用默认的每 10 分钟执行一次。",
                    "section": "general",
                },
                {
                    "key": "cleanup_enabled",
                    "input_type": "switch",
                    "label": "自动检查删种规则",
                    "default": False,
                    "description": "按执行周期检查本插件新增且已确认归属的已完成任务；旧的无归属记录和其他下载不会处理。",
                    "section": "general",
                },
                {
                    "key": "tasks",
                    "input_type": "textarea",
                    "label": "刷流任务",
                    "default": [],
                    "visible": False,
                },
                {
                    "key": "default_site_id",
                    "input_type": "resource_select",
                    "resource_kind": "site",
                    "required_capabilities": ["latest"],
                    "label": "默认 PT 站点",
                    "description": "自定义任务未指定站点时使用，不覆盖任务自己的站点。",
                    "section": "general",
                },
                {
                    "key": "default_downloader_id",
                    "input_type": "resource_select",
                    "resource_kind": "downloader",
                    "required_capabilities": ["add"],
                    "label": "默认下载器",
                    "description": "自定义任务未指定下载器时使用，不覆盖任务自己的下载器。",
                    "section": "general",
                },
                {
                    "key": "max_tasks",
                    "input_type": "number",
                    "label": "全局最大下载任务数",
                    "default": 30,
                    "description": "所有刷流任务合计不能超过此数量，达到上限后停止添加。",
                    "validation": {"minimum": 1, "maximum": 500},
                    "section": "general",
                },
                {
                    "key": "allow_delete_files",
                    "input_type": "switch",
                    "label": "允许删种时同时删除文件",
                    "default": False,
                    "description": "高风险选项。开启后，命中删种规则时会同时删除已下载文件。",
                    "section": "general",
                },
            ],
        },
    )

    async def run(self, context: PluginContext) -> dict[str, Any]:
        if not bool(context.config.get("enabled", True)):
            return {"status": "disabled", "added": 0, "tasks": 0}
        configured = self._tasks(context.config)
        cleanup = await check_downloads(context, due_tasks(context, configured, check=True))
        tasks = due_tasks(context, configured)
        result = await self._run_tasks(context, tasks)
        return {**result, "cleanup": cleanup}

    async def handle_api(self, request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        if request.action == "statistics" and request.method == "GET":
            return await build_statistics(context, self._tasks(context.config))
        if request.action == "inventory" and request.method == "GET":
            sites, downloaders = (
                await context.sites.configurations(),
                await context.downloads.configurations(),
            )
            return {
                "sites": sites.get("items", []),
                "downloaders": downloaders.get("items", []),
                "active_downloader_id": downloaders.get("active_id", ""),
                "config": context.config,
                "tasks": self._tasks(context.config),
                "history": context.items.list(100),
            }
        if request.action == "preview" and request.method == "POST":
            task = self._tasks({**context.config, "tasks": [request.payload]})[0]
            sites = self._site_actions(context)
            site_id = str(task.get("site_id") or "")
            feed = await sites.feed(site_id, limit=100) if task.get("use_rss") else await self._latest(sites, site_id, limit=100)
            index = await load_index(context, [task])
            matches = [item for item in feed.get("items", []) if self._matches(item, task)
                       and not (index and index.matches(item))]
            return {"items": matches[:50], "count": len(matches)}
        if request.action == "run" and request.method == "POST":
            task_id = str(request.payload.get("task_id") or "")
            selected = [
                task for task in self._tasks(context.config) if not task_id or task["id"] == task_id
            ]
            return await self._run_tasks(context, selected)
        if request.action == "check" and request.method == "POST":
            return await self._check_downloads(context)
        raise KeyError("刷流插件页面操作不存在")

    async def _run_tasks(
        self, context: PluginContext, tasks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        tasks = [task for task in tasks if intake_allowed(task)]
        if not tasks:
            return {"status": "completed", "tasks": 0, "added": 0, "results": []}
        index = await load_index(context, tasks)
        existing_items = await owned_downloads(context)
        remaining = max(0, int(context.config.get("max_tasks") or 30) - len(existing_items))
        added = 0
        results: list[dict[str, Any]] = []
        for task in tasks:
            if not task.get("enabled", True):
                continue
            if remaining <= 0:
                record_execution(context, task, reason="达到全局数量上限")
                continue
            capacity = task_capacity(context, task, existing_items)
            volume = await volume_remaining(context, task, existing_items, complete=True)
            if capacity <= 0 or volume == 0:
                record_execution(context, task, reason="达到体积上限" if volume == 0 else "达到任务数量上限")
                continue
            sites = self._site_actions(context)
            site_id = str(task.get("site_id") or "")
            feed = await self._task_feed(context, task, sites, site_id)
            candidates = [item for item in feed.get("items", []) if self._matches(item, task)
                          and not (task.get("exclude_subscriptions") and index and index.matches(item))]
            task_added, task_failed = await self._submit_candidates(
                context, sites, site_id, task, candidates,
                min(remaining, capacity, int(task.get("max_add") or 3)), volume,
            )
            added += task_added
            remaining -= task_added
            record_execution(context, task, added=task_added, matched=len(candidates),
                             skipped=max(0, len(feed.get("items", [])) - task_added - task_failed),
                             failed=task_failed, reason="部分失败" if task_failed else "成功")
            results.append(
                {
                    "task_id": task["id"],
                    "name": task["name"],
                    "matched": len(candidates),
                    "added": task_added,
                }
            )
        summary = {"status": "completed", "tasks": len(tasks), "added": added, "results": results}
        await self._notify_tasks(context, tasks, results)
        return summary

    async def _task_feed(self, context, task, sites, site_id):
        try:
            return await sites.feed(site_id, limit=200) if task.get("use_rss") else await self._latest(sites, site_id, limit=200)
        except Exception:
            record_execution(context, task, failed=1, reason="站点读取失败")
            raise

    async def _submit_candidates(self, context, sites, site_id, task, candidates, capacity, volume):
        task_added = 0
        task_failed = 0
        for item in candidates:
            if not intake_allowed(task):
                break
            if task_added >= capacity:
                break
            size = size_bytes(item)
            if volume is not None and (size is None or size > volume):
                continue
            key = self._item_key(task, item)
            if context.items.get(key):
                continue
            if not await self._add_candidate(context, sites, site_id, task, item, key):
                recorded = context.items.get(key) or {}
                task_failed += int(recorded.get("status") == "failed")
                continue
            if volume is not None:
                volume -= size
            task_added += 1
        return task_added, task_failed

    @staticmethod
    async def _notify_tasks(context: PluginContext, tasks: list[dict[str, Any]], results: list[dict[str, Any]]) -> None:
        configured = {task["id"]: task for task in tasks}
        for outcome in results:
            task = configured[outcome["task_id"]]
            if task.get("notification_enabled", context.config.get("notification_enabled", False)):
                await context.notifications.send(
                    f"刷流任务：{task['name']}",
                    f"匹配 {outcome['matched']} 个，新增下载 {outcome['added']} 个。",
                    notification_type="plugin",
                )

    @staticmethod
    async def _add_candidate(
        context: PluginContext,
        sites: Any,
        site_id: str,
        task: dict[str, Any],
        item: dict[str, Any],
        key: str,
    ) -> bool:
        try:
            if hasattr(sites, "dispatch"):
                result = await sites.dispatch(
                    site_id,
                    str(item.get("id") or ""),
                    str(task.get("downloader_id") or ""),
                    save_path=str(task.get("save_path") or ""),
                    tags=["刷流"],
                    include_default_tag=False,
                    **transfer_limits(task),
                    **(
                        {"track_ownership": True}
                        if "track_ownership" in inspect.signature(sites.dispatch).parameters
                        else {}
                    ),
                )
            else:
                result = await context.downloads.add(
                    {
                        "downloader_id": str(task.get("downloader_id") or "") or None,
                        "save_path": str(task.get("save_path") or "") or None,
                        "item": item,
                        "tags": ["刷流"],
                        "include_default_tag": False,
                        "track_ownership": True,
                        **transfer_limits(task),
                    }
                )
        except Exception as error:
            context.items.record(key, "failed", payload=item, result={"error": str(error)})
            return False
        if result.get("status") == "already_exists":
            context.items.record(key, "duplicate", payload=item, result=dict(result))
            return False
        context.items.record(
            key, "added", payload=item, result={**result, "brush_task_id": str(task["id"]), "brush_task_name": task.get("name") or "未命名刷流任务", "brush_site_id": task.get("site_id", "")}
        )
        return True

    async def _check_downloads(self, context: PluginContext) -> dict[str, Any]:
        return await check_downloads(context, self._tasks(context.config))

    @staticmethod
    def _tasks(config: dict[str, Any]) -> list[dict[str, Any]]:
        values = config.get("tasks")
        if not isinstance(values, list):
            return []
        result: list[dict[str, Any]] = []
        for value in values:
            if not isinstance(value, dict):
                continue
            task = SiteTrafficPlugin._task(task_defaults(value, config))
            task["site_id"] = str(task.get("site_id") or config.get("default_site_id") or "")
            task["downloader_id"] = str(
                task.get("downloader_id") or config.get("default_downloader_id") or ""
            )
            result.append(task)
        return result

    @staticmethod
    def _task(value: dict[str, Any]) -> dict[str, Any]:
        task = dict(value)
        task["id"] = str(task.get("id") or hashlib.sha1(str(task).encode()).hexdigest()[:12])
        task["name"] = str(task.get("name") or "未命名刷流任务")
        return task

    @staticmethod
    def _site_actions(context: PluginContext) -> Any:
        sdk = getattr(context, "sdk", None)
        return sdk.require("sites", min_version=2) if sdk is not None else context.sites

    @staticmethod
    async def _latest(sites: Any, site_id: str, *, limit: int) -> dict[str, Any]:
        # Older hosts retain their RSS path; newer hosts expose bounded latest lists.
        action = getattr(sites, "latest", None) or sites.feed
        return await action(site_id, limit=limit)

    @staticmethod
    def _matches(item: dict[str, Any], task: dict[str, Any]) -> bool:
        return matches(item, task)

    @staticmethod
    def _item_key(task: dict[str, Any], item: dict[str, Any]) -> str:
        raw = f"{task.get('id')}:{item.get('id') or item.get('download_url') or item.get('title')}"
        return f"brush:{hashlib.sha256(raw.encode()).hexdigest()}"


Plugin = SiteTrafficPlugin
PLUGIN = SiteTrafficPlugin
