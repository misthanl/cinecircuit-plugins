from typing import Any

from app.modules.plugins.contracts import PluginBase, PluginContext, PluginManifest
from app.modules.plugins.permissions import PluginPermission


class StorageRecycleCleanerPlugin(PluginBase):
    """Schedule permanent cleanup through a credential-isolated storage capability."""

    manifest = PluginManifest(
        id="storage-recycle-cleaner",
        name="网盘回收站清理",
        version="1.0.0",
        entrypoint="plugin:StorageRecycleCleanerPlugin",
        description="定时清空所选网盘回收站，释放存储空间。",
        icon="mdi-trash-can-outline",
        permissions=(PluginPermission.STORAGE_READ, PluginPermission.STORAGE_CLEAR_RECYCLE_BIN,
                     PluginPermission.NOTIFICATION_SEND),
        capabilities=("scheduled_task", "storage_tool"),
        schedule_seconds=86400,
        frontend_module="frontend.js",
        config_schema={
            "description_display": "hidden",
            "layout": {"columns": 2, "row_gap": 14, "column_gap": 16},
            "fields": [
                {"key": "enabled", "input_type": "switch", "label": "启用定时清理", "default": False},
                {"key": "cron", "input_type": "cron", "label": "执行周期", "default": "0 3 * * *"},
                {"key": "storage_id", "input_type": "resource_select", "resource_kind": "storage",
                 "required_capabilities": ["recycle_bin_clear"], "label": "网盘存储", "default": None,
                 "description_display": "hidden"},
                {"key": "password", "input_type": "password", "secret": True,
                 "label": "回收站安全密钥", "default": "",
                 "description_display": "hidden"},
                {"key": "confirm_permanent", "input_type": "switch",
                 "label": "确认永久清空回收站（不可恢复）", "default": False},
                {"key": "notification_enabled", "input_type": "switch", "label": "发送通知", "default": False},
            ]
        },
    )

    async def run(self, context: PluginContext) -> dict[str, Any]:
        if context.trigger == "scheduled" and not context.config.get("enabled", False):
            return {"status": "skipped", "reason": "schedule_disabled"}
        storage_id = str(context.config.get("storage_id") or "").strip()
        if not storage_id or context.config.get("confirm_permanent") is not True:
            return {"status": "skipped", "reason": "storage_or_confirmation_missing"}
        gateway = context.sdk.require("storage", min_version=1)
        result = await gateway.clear_recycle_bin(
            storage_id, password=str(context.config.get("password") or ""), confirm=True
        )
        if result.get("ok") is not True:
            raise RuntimeError("回收站清理未确认成功")
        context.logger.info("所选存储回收站清理完成")
        if context.config.get("notification_enabled", False):
            try:
                await context.notifications.send("网盘回收站清理", "所选存储的回收站已永久清空。")
            except Exception:
                context.logger.warning("回收站已清空，但通知发送失败；无需重复清理")
        return {"status": "success", "storage_id": storage_id, "cleared": True}
