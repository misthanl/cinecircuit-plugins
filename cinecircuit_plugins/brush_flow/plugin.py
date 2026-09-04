from __future__ import annotations

import hashlib
import re
from typing import Any

from app.modules.plugins.contracts import (
    PluginApiRequest,
    PluginBase,
    PluginContext,
    PluginManifest,
)
from app.modules.plugins.permissions import PluginPermission


class SiteTrafficPlugin(PluginBase):
    """集中管理站点流量任务、选种规则与下载器调度。"""

    manifest = PluginManifest(
        entrypoint="plugin:SiteTrafficPlugin",
        id="brush-flow",
        name="站点刷流",
        version="1.0.0",
        description="按站点、下载器、选种规则和删种规则执行自动刷流，并记录任务统计。",
        icon="mdi-water-sync",
        permissions=(
            PluginPermission.SITE_READ,
            PluginPermission.DOWNLOADER_READ,
            PluginPermission.DOWNLOADER_ADD,
            PluginPermission.DOWNLOADER_PAUSE,
            PluginPermission.DOWNLOADER_DELETE_TASK,
            PluginPermission.DOWNLOADER_DELETE_FILES,
            PluginPermission.NOTIFICATION_SEND,
        ),
        capabilities=("plugin_page", "scheduled_task", "site_rss", "download_controller"),
        schedule_seconds=5 * 60,
        frontend_module="frontend.js",
        navigation={"title": "站点刷流", "icon": "mdi-water-sync", "section": "tools", "order": 74},
        config_schema={
            "sections": [
                {
                    "key": "runtime",
                    "title": "运行设置",
                    "description": "任务在各自周期到期后按顺序执行。",
                },
                {
                    "key": "safety",
                    "title": "安全限制",
                    "description": "限制全局任务数和删种行为，避免刷流失控。",
                },
            ],
            "fields": [
                {
                    "key": "enabled",
                    "input_type": "switch",
                    "label": "启用刷流任务",
                    "default": True,
                    "section": "runtime",
                },
                {
                    "key": "notification_enabled",
                    "input_type": "switch",
                    "label": "发送通知",
                    "default": False,
                    "description": "开启后发送每次刷流任务的执行结果。",
                    "section": "runtime",
                },
                {
                    "key": "cron",
                    "input_type": "cron",
                    "label": "执行周期",
                    "default": "",
                    "placeholder": "5位cron表达式，留空自动",
                    "description": "留空使用默认的每 5 分钟执行一次。",
                    "section": "runtime",
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
                    "required_capabilities": ["feed"],
                    "label": "默认 PT 站点",
                    "description": "自定义任务未指定站点时使用，不覆盖任务自己的站点。",
                    "section": "runtime",
                },
                {
                    "key": "default_downloader_id",
                    "input_type": "resource_select",
                    "resource_kind": "downloader",
                    "required_capabilities": ["add"],
                    "label": "默认下载器",
                    "description": "自定义任务未指定下载器时使用，不覆盖任务自己的下载器。",
                    "section": "runtime",
                },
                {
                    "key": "max_tasks",
                    "input_type": "number",
                    "label": "全局最大下载任务数",
                    "default": 30,
                    "validation": {"minimum": 1, "maximum": 500},
                    "section": "safety",
                },
                {
                    "key": "allow_delete_files",
                    "input_type": "switch",
                    "label": "允许删种时同时删除文件",
                    "default": False,
                    "section": "safety",
                },
            ],
        },
    )

    async def run(self, context: PluginContext) -> dict[str, Any]:
        if not bool(context.config.get("enabled", True)):
            return {"status": "disabled", "added": 0, "tasks": 0}
        return await self._run_tasks(context, self._tasks(context.config))

    async def handle_api(self, request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
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
            task = self._task(request.payload)
            sites = self._site_actions(context)
            feed = await sites.feed(str(task.get("site_id") or ""), limit=100)
            matches = [item for item in feed.get("items", []) if self._matches(item, task)]
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
        existing = await context.downloads.list_tasks()
        existing_items = list(existing.get("items") or [])
        remaining = max(0, int(context.config.get("max_tasks") or 30) - len(existing_items))
        added = 0
        results: list[dict[str, Any]] = []
        for task in tasks:
            if not task.get("enabled", True) or remaining <= 0:
                continue
            sites = self._site_actions(context)
            site_id = str(task.get("site_id") or "")
            feed = await sites.feed(site_id, limit=200)
            candidates = [item for item in feed.get("items", []) if self._matches(item, task)]
            task_added = 0
            for item in candidates[: min(remaining, int(task.get("max_add") or 3))]:
                key = self._item_key(task, item)
                if context.items.get(key):
                    continue
                if not await self._add_candidate(context, sites, site_id, task, item, key):
                    continue
                task_added += 1
                added += 1
                remaining -= 1
                if remaining <= 0:
                    break
            results.append(
                {
                    "task_id": task["id"],
                    "name": task["name"],
                    "matched": len(candidates),
                    "added": task_added,
                }
            )
        summary = {"status": "completed", "tasks": len(tasks), "added": added, "results": results}
        if bool(context.config.get("notification_enabled")):
            await context.notifications.send(
                "站点刷流任务完成",
                f"执行任务 {len(tasks)} 个，新增下载 {added} 个。",
                notification_type="plugin",
            )
        return summary

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
                )
            else:
                result = await context.downloads.add(
                    {
                        "downloader_id": str(task.get("downloader_id") or "") or None,
                        "save_path": str(task.get("save_path") or "") or None,
                        "item": item,
                    }
                )
        except Exception as error:
            context.items.record(key, "failed", payload=item, result={"error": str(error)})
            return False
        context.items.record(key, "added", payload=item, result=dict(result))
        return True

    async def _check_downloads(self, context: PluginContext) -> dict[str, Any]:
        listing = await context.downloads.list_tasks()
        tasks = list(listing.get("items") or [])
        paused = 0
        deleted = 0
        for rule in self._tasks(context.config):
            ratio_limit = float(rule.get("delete_ratio") or 0)
            seed_hours = float(rule.get("delete_seed_hours") or 0)
            if not ratio_limit and not seed_hours:
                continue
            for item in tasks:
                site_id = str(item.get("site_id") or item.get("source_id") or "")
                if site_id and site_id != str(rule.get("site_id") or ""):
                    continue
                ratio = float(item.get("ratio") or item.get("share_ratio") or 0)
                hours = float(item.get("seeding_time") or item.get("seed_hours") or 0)
                if (ratio_limit and ratio >= ratio_limit) or (seed_hours and hours >= seed_hours):
                    downloader_id = str(
                        item.get("downloader_id") or rule.get("downloader_id") or ""
                    )
                    task_id = str(item.get("id") or item.get("hash") or "")
                    if not downloader_id or not task_id:
                        continue
                    if bool(rule.get("delete_task", False)):
                        await context.downloads.delete(
                            downloader_id,
                            task_id,
                            delete_files=bool(context.config.get("allow_delete_files", False)),
                        )
                        deleted += 1
                    else:
                        await context.downloads.pause(downloader_id, task_id)
                        paused += 1
        return {"status": "completed", "checked": len(tasks), "paused": paused, "deleted": deleted}

    @staticmethod
    def _tasks(config: dict[str, Any]) -> list[dict[str, Any]]:
        values = config.get("tasks")
        if not isinstance(values, list):
            return []
        result: list[dict[str, Any]] = []
        for value in values:
            if not isinstance(value, dict):
                continue
            task = SiteTrafficPlugin._task(value)
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
    def _matches(item: dict[str, Any], task: dict[str, Any]) -> bool:
        title = str(item.get("title") or "")
        include = str(task.get("include") or "").strip()
        exclude = str(task.get("exclude") or "").strip()
        if include and not re.search(include, title, re.I):
            return False
        if exclude and re.search(exclude, title, re.I):
            return False
        size_gib = float(item.get("size") or 0) / 1024**3
        minimum = float(task.get("min_size") or 0)
        maximum = float(task.get("max_size") or 0)
        return not ((minimum and size_gib < minimum) or (maximum and size_gib > maximum))

    @staticmethod
    def _item_key(task: dict[str, Any], item: dict[str, Any]) -> str:
        raw = f"{task.get('id')}:{item.get('id') or item.get('download_url') or item.get('title')}"
        return f"brush:{hashlib.sha256(raw.encode()).hexdigest()}"


Plugin = SiteTrafficPlugin
PLUGIN = SiteTrafficPlugin
