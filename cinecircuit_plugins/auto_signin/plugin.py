from __future__ import annotations

import asyncio
import re
from typing import Any

from app.modules.plugins.contracts import (
    PluginApiRequest,
    PluginBase,
    PluginContext,
    PluginManifest,
)
from app.modules.plugins.permissions import PluginPermission


class SiteCheckinPlugin(PluginBase):
    """管理站点签到、登录保持与结果记录。"""

    manifest = PluginManifest(
        entrypoint="plugin:SiteCheckinPlugin",
        id="auto-signin",
        name="站点签到助手",
        version="1.0.0",
        description="自动模拟登录并签到所选 PT 站点，保留每日结果、失败原因和重试筛选。",
        icon="mdi-calendar-check-outline",
        permissions=(
            PluginPermission.SITE_READ,
            PluginPermission.SITE_SIGN_IN,
            PluginPermission.NOTIFICATION_SEND,
        ),
        capabilities=("scheduled_task", "plugin_page", "site_automation"),
        schedule_seconds=24 * 60 * 60,
        frontend_module="frontend.js",
        navigation={
            "title": "自动签到",
            "icon": "mdi-calendar-check-outline",
            "section": "tools",
            "order": 72,
        },
        config_schema={
            "sections": [
                {
                    "key": "schedule",
                    "title": "执行设置",
                    "description": "站点选择请在插件的“自动签到”页面中勾选。",
                },
                {
                    "key": "retry",
                    "title": "失败重试",
                    "description": "只有错误信息命中关键词时才进入本次重试队列。",
                },
            ],
            "fields": [
                {
                    "key": "enabled",
                    "input_type": "switch",
                    "label": "启用自动签到",
                    "default": True,
                    "description": "按下方周期自动执行；关闭后仍可在插件页面手动运行。",
                    "icon": "mdi-toggle-switch-outline",
                    "section": "schedule",
                },
                {
                    "key": "cron",
                    "input_type": "cron",
                    "label": "执行周期",
                    "default": "",
                    "placeholder": "5位cron表达式，留空自动",
                    "description": "留空时每天执行一次；也可以用可视化周期选择器调整。",
                    "icon": "mdi-calendar-clock",
                    "section": "schedule",
                },
                {
                    "key": "notification_enabled",
                    "input_type": "switch",
                    "label": "发送通知",
                    "default": False,
                    "description": "开启后发送每次签到任务的执行结果。",
                    "icon": "mdi-bell-outline",
                    "section": "schedule",
                },
                {
                    "key": "queue_cnt",
                    "input_type": "number",
                    "label": "并发队列数量",
                    "default": 5,
                    "description": "同时签到的站点数；网络不稳定时建议设为 2～5。",
                    "icon": "mdi-format-list-numbered",
                    "validation": {"minimum": 1, "maximum": 20},
                    "section": "schedule",
                },
                {
                    "key": "clean",
                    "input_type": "switch",
                    "label": "下次执行前清理本日缓存",
                    "default": False,
                    "description": "仅下一次运行生效，用于重新签到今天已成功的站点。",
                    "icon": "mdi-broom",
                    "section": "schedule",
                },
                {
                    "key": "retry_keyword",
                    "input_type": "text",
                    "label": "重试关键词",
                    "default": "超时|timeout|连接|connection|503|502",
                    "placeholder": "支持正则表达式，命中才重签",
                    "description": "用“|”分隔多个错误词；只有失败原因命中时才自动重试。",
                    "icon": "mdi-text-search",
                    "section": "retry",
                },
                {
                    "key": "auto_cf",
                    "input_type": "number",
                    "label": "自动优选触发次数",
                    "default": 0,
                    "description": "命中重试关键词达到此次数后触发站点优选；0 表示关闭。",
                    "icon": "mdi-cloud-refresh-outline",
                    "validation": {"minimum": 0, "maximum": 20},
                    "section": "retry",
                },
                {
                    "key": "sign_sites",
                    "input_type": "resource_multi_select",
                    "resource_kind": "site",
                    "required_capabilities": ["sign_in"],
                    "label": "签到站点",
                    "default": [],
                    "description": "选择需要每日自动签到的 PT 站点。",
                },
                {
                    "key": "login_sites",
                    "input_type": "resource_multi_select",
                    "resource_kind": "site",
                    "required_capabilities": ["check"],
                    "label": "保持登录站点",
                    "default": [],
                    "description": "选择仅检测并保持登录状态的 PT 站点。",
                },
            ],
        },
    )

    async def run(self, context: PluginContext) -> dict[str, Any]:
        if not bool(context.config.get("enabled", True)):
            return {"status": "disabled", "site_count": 0, "updated_count": 0, "results": []}
        site_ids = self._list(context.config.get("sign_sites"))
        login_ids = [
            value
            for value in self._list(context.config.get("login_sites"))
            if value not in site_ids
        ]
        semaphore = asyncio.Semaphore(min(20, max(1, int(context.config.get("queue_cnt") or 5))))
        results = list(
            await asyncio.gather(
                *(self._execute_site(context, semaphore, site_id, "sign") for site_id in site_ids),
                *(
                    self._execute_site(context, semaphore, site_id, "login")
                    for site_id in login_ids
                ),
            )
        )
        results = await self._retry_failed_sites(context, semaphore, results)
        for row in results:
            row.setdefault("status", "checked" if row.get("ok") else "failed")
        for row in results:
            context.items.record(
                f"{row['mode']}:{row['site_id']}",
                "signed" if row.get("ok") else "failed",
                payload={"site_id": row["site_id"], "mode": row["mode"]},
                result=row,
            )
        await self._notify_site_results(context, results)
        return {
            "site_count": len(results),
            "updated_count": sum(1 for row in results if row.get("ok")),
            "results": results,
        }

    @staticmethod
    async def _execute_site(
        context: PluginContext,
        semaphore: asyncio.Semaphore,
        site_id: str,
        mode: str,
    ) -> dict[str, Any]:
        async with semaphore:
            try:
                result = await (
                    context.sites.check(site_id)
                    if mode == "login"
                    else context.sites.sign_in(site_id)
                )
            except Exception as error:
                result = {"ok": False, "status": "failed", "message": str(error)}
            return {"site_id": site_id, "mode": mode, **result}

    async def _retry_failed_sites(
        self,
        context: PluginContext,
        semaphore: asyncio.Semaphore,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        retry_pattern = str(context.config.get("retry_keyword") or "").strip()
        retry_rows = [
            row
            for row in results
            if not row.get("ok")
            and retry_pattern
            and re.search(retry_pattern, str(row.get("message") or ""), re.I)
        ]
        if retry_rows:
            replacements = await asyncio.gather(
                *(
                    self._execute_site(
                        context,
                        semaphore,
                        str(row["site_id"]),
                        str(row["mode"]),
                    )
                    for row in retry_rows
                )
            )
            by_key = {(str(row["site_id"]), str(row["mode"])): row for row in replacements}
            results = [by_key.get((str(row["site_id"]), str(row["mode"])), row) for row in results]
        return results

    @staticmethod
    async def _notify_site_results(context: PluginContext, results: list[dict[str, Any]]) -> None:
        if bool(context.config.get("notification_enabled")) and results:
            success = sum(1 for row in results if row.get("ok"))
            details = "\n".join(
                f"{row['site_id']}：{row.get('message') or row.get('status')}" for row in results
            )
            await context.notifications.send(
                f"站点签到完成：成功 {success}/{len(results)}",
                details,
                notification_type="plugin",
            )

    async def handle_api(self, request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        if request.action == "inventory" and request.method == "GET":
            sites = await context.sites.configurations()
            return {
                **sites,
                "config": dict(context.config),
                "selected": {
                    "sign_sites": self._list(context.config.get("sign_sites")),
                    "login_sites": self._list(context.config.get("login_sites")),
                },
            }
        if request.action == "site" and request.method == "POST":
            site_id = str(request.payload.get("site_id") or "")
            mode = str(request.payload.get("mode") or "sign")
            if not site_id:
                raise ValueError("未选择站点")
            return await (
                context.sites.check(site_id) if mode == "login" else context.sites.sign_in(site_id)
            )
        raise KeyError("自动签到页面操作不存在")

    @staticmethod
    def _list(value: object) -> list[str]:
        if isinstance(value, list):
            return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))
        return list(dict.fromkeys(item for item in re.split(r"[\s,，]+", str(value or "")) if item))


Plugin = SiteCheckinPlugin
PLUGIN = SiteCheckinPlugin
