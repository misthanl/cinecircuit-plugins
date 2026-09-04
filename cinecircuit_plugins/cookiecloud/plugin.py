from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

from .snapshot import load_snapshot
from app.modules.plugins.contracts import (
    PluginApiRequest,
    PluginBase,
    PluginContext,
    PluginHttpResponse,
    PluginManifest,
)
from app.modules.plugins.permissions import PluginPermission


class CookieCloudPlugin(PluginBase):
    """Periodically validate and synchronize supported PT site Cookies."""

    manifest = PluginManifest(
        entrypoint="plugin:CookieCloudPlugin",
        id="cookiecloud",
        name="CookieCloud 站点同步",
        version="1.0.1",
        description="接收浏览器 CookieCloud 快照，定时验证并更新或添加受支持的 PT 站点。",
        icon="mdi-cloud-sync-outline",
        api_version=2,
        permissions=(
            PluginPermission.PUBLIC_HTTP,
            PluginPermission.SITE_READ,
            PluginPermission.SITE_SIGN_IN,
            PluginPermission.SITE_CREDENTIALS_WRITE,
            PluginPermission.NOTIFICATION_SEND,
        ),
        capabilities=("scheduled_task", "plugin_page", "site_automation", "statistics_page"),
        schedule_seconds=24 * 60 * 60,
        frontend_module="frontend.js",
        config_schema={
            "description": "KEY 和密码保存后可查看；点击小眼睛显示或隐藏密码",
            "sections": [
                {
                    "key": "connection",
                    "title": "CookieCloud 设置",
                    "description": "浏览器扩展服务地址填写 http://127.0.0.1:8000/plugin-public/cookiecloud。",
                },
                {
                    "key": "schedule",
                    "title": "检查计划",
                    "description": "上传只保存快照，站点检查始终由插件定时或手动触发。",
                },
            ],
            "fields": [
                {
                    "key": "enabled",
                    "input_type": "switch",
                    "label": "启用站点 Cookie 同步",
                    "default": True,
                    "section": "connection",
                },
                {
                    "key": "user_key",
                    "input_type": "text",
                    "label": "用户 KEY",
                    "default": "",
                    "placeholder": "与浏览器 CookieCloud 扩展保持一致",
                    "icon": "mdi-key-outline",
                    "section": "connection",
                },
                {
                    "key": "password",
                    "input_type": "password",
                    "label": "端对端加密密码",
                    "default": "",
                    "secret": True,
                    "encrypted": False,
                    "icon": "mdi-lock-outline",
                    "section": "connection",
                },
                {
                    "key": "run_once",
                    "input_type": "switch",
                    "label": "保存后立即运行一次",
                    "default": False,
                    "description": "保存后加入一次手动检查任务，随后自动关闭此开关。",
                    "section": "schedule",
                },
                {
                    "key": "notification_enabled",
                    "input_type": "switch",
                    "label": "发送通知",
                    "default": False,
                    "description": "开启后发送每次站点同步的执行结果。",
                    "section": "schedule",
                },
                {
                    "key": "cron",
                    "input_type": "select",
                    "label": "定时检查周期",
                    "default": "",
                    "icon": "mdi-calendar-clock",
                    "section": "schedule",
                    "options": [
                        {"value": "0 */6 * * *", "label": "每 6 小时"},
                        {"value": "0 */12 * * *", "label": "每 12 小时"},
                        {"value": "", "label": "每天"},
                        {"value": "0 0 * * 1", "label": "每周"},
                        {"value": "0 0 1 * *", "label": "每月"},
                    ],
                    "description": "每周在周一 00:00、每月在 1 日 00:00 执行。",
                },
            ],
        },
    )

    async def run(self, context: PluginContext) -> dict[str, Any]:
        started = time.perf_counter()
        summary = {"checked": 0, "valid": 0, "updated": 0, "added": 0, "ignored": 0, "failed": 0}
        if not bool(context.config.get("enabled", True)):
            return {"status": "disabled", **summary, "duration_ms": 0}
        user_key = str(context.config.get("user_key") or "").strip()
        if not user_key:
            summary["failed"] = 1
            return await self._finish(context, summary, started, status="missing_user_key")
        snapshot = load_snapshot(context.state, uuid=user_key)
        if snapshot is None:
            summary["failed"] = 1
            return await self._finish(context, summary, started, status="missing_snapshot")
        try:
            cookies = self._decrypt_cookies(context, user_key, snapshot)
        except ValueError as error:
            context.logger.warning("CookieCloud 快照解密失败：%s", error)
            summary["failed"] = 1
            return await self._finish(context, summary, started, status="decrypt_failed")
        catalog = await context.sites.supported_catalog()
        await self._sync_supported_sites(context, catalog, cookies, summary)
        return await self._finish(context, summary, started, status="completed")

    @staticmethod
    def _decrypt_cookies(
        context: PluginContext,
        user_key: str,
        snapshot: dict[str, Any],
    ) -> list[dict[str, Any]]:
        from .crypto import decrypt_snapshot

        decrypted = decrypt_snapshot(
            user_key,
            str(context.config.get("password") or ""),
            str(snapshot["encrypted"]),
            str(snapshot["crypto_type"]),
        )
        return _cookies_by_domain(decrypted.get("cookie_data"))

    async def _sync_supported_sites(
        self,
        context: PluginContext,
        catalog: dict[str, Any],
        cookies: list[dict[str, Any]],
        summary: dict[str, int],
    ) -> None:
        for resource in catalog.get("items", []):
            if "cookie" not in resource.get("credential_imports", ()):
                continue
            cookie = _cookie_header(cookies, resource.get("domains") or [])
            if not cookie:
                summary["ignored"] += 1
                context.logger.info(
                    "CookieCloud 忽略站点 %s：快照中没有匹配 Cookie", resource.get("name")
                )
                continue
            summary["checked"] += 1
            try:
                await self._sync_site(context, resource, cookie, summary)
            except Exception as error:
                summary["failed"] += 1
                context.logger.warning(
                    "CookieCloud 站点 %s 检查失败：%s", resource.get("name"), error
                )

    @staticmethod
    async def _sync_site(
        context: PluginContext,
        resource: dict[str, Any],
        cookie: str,
        summary: dict[str, int],
    ) -> None:
        site_name = str(resource.get("name") or resource.get("id") or "未知站点")
        site_id = str(resource.get("site_id") or "")
        if site_id:
            current = await context.sites.check(site_id)
            if current.get("ok"):
                summary["valid"] += 1
                context.logger.info("CookieCloud 站点 Cookie 保持有效：%s", site_name)
                return
        result = await context.sites.apply_cookie(
            str(resource.get("id") or ""),
            cookie,
            site_id=site_id,
        )
        if result.get("applied"):
            created = bool(result.get("created"))
            summary["added" if created else "updated"] += 1
            context.logger.info(
                "CookieCloud 已%s站点%s：%s",
                "添加" if created else "更新",
                site_name,
                result.get("message") or "成功",
            )
            return
        summary["ignored"] += 1
        context.logger.warning(
            "CookieCloud 未采用站点 %s 的候选 Cookie：%s",
            site_name,
            result.get("message") or "验证未通过",
        )

    async def handle_public_api(self, request: PluginApiRequest, context: PluginContext) -> PluginHttpResponse:
        from .http_api import handle
        return await handle(request, context)

    async def handle_api(self, request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        if request.action != "status" or request.method != "GET":
            raise KeyError("CookieCloud 页面操作不存在")
        user_key = str(context.config.get("user_key") or "").strip()
        snapshot = load_snapshot(context.state, uuid=user_key) if user_key else None
        return {
            "config": {
                "enabled": bool(context.config.get("enabled", True)),
                "user_key": user_key,
                "password": "",
                "password_configured": bool(context.config.get("password")),
                "cron": str(context.config.get("cron") or ""),
                "run_once": False,
            },
            "endpoint": "/plugin-public/cookiecloud",
            "snapshot": {
                "available": snapshot is not None,
                "uploaded_at": str((snapshot or {}).get("uploaded_at") or ""),
            },
        }

    @staticmethod
    async def _finish(
        context: PluginContext,
        summary: dict[str, int],
        started: float,
        *,
        status: str,
    ) -> dict[str, Any]:
        duration_ms = int((time.perf_counter() - started) * 1000)
        context.logger.info(
            "CookieCloud 站点检查完成：检查 %s，有效 %s，更新 %s，新增 %s，忽略 %s，失败 %s，耗时 %s ms",
            summary["checked"],
            summary["valid"],
            summary["updated"],
            summary["added"],
            summary["ignored"],
            summary["failed"],
            duration_ms,
        )
        result = {"status": status, **summary, "duration_ms": duration_ms}
        if bool(context.config.get("notification_enabled")):
            await context.notifications.send(
                "CookieCloud 站点同步完成",
                (
                    f"检查 {summary['checked']} 个，有效 {summary['valid']} 个，"
                    f"更新 {summary['updated']} 个，新增 {summary['added']} 个，"
                    f"失败 {summary['failed']} 个。"
                ),
                notification_type="plugin",
            )
        return result


def _cookies_by_domain(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    result: list[dict[str, Any]] = []
    now = time.time()
    for rows in value.values():
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            expires = item.get("expirationDate")
            if isinstance(expires, (int, float)) and expires > 0 and expires <= now:
                continue
            result.append(dict(item))
    return result


def _cookie_header(cookies: Iterable[dict[str, Any]], domains: Iterable[object]) -> str:
    supported = {
        str(value).strip().casefold().lstrip(".") for value in domains if str(value).strip()
    }
    candidates: dict[str, tuple[int, str]] = {}
    for cookie in cookies:
        domain = str(cookie.get("domain") or "").strip().casefold().lstrip(".")
        if not domain or not any(
            value == domain or value.endswith(f".{domain}") for value in supported
        ):
            continue
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        score = len(domain) * 1000 + len(str(cookie.get("path") or "/"))
        if name and (name not in candidates or score > candidates[name][0]):
            candidates[name] = (score, value)
    return "; ".join(f"{name}={value[1]}" for name, value in candidates.items())
