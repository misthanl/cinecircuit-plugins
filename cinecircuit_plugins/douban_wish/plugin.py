"""Synchronize public Douban wish entries through the plugin SDK."""
from typing import Any

from app.modules.plugins.contracts import PluginApiRequest, PluginBase, PluginContext, PluginManifest
from app.modules.plugins.permissions import PluginPermission
from .._shared.rank_statistics import cumulative_statistics, save_run_snapshot
from .feed import read_user, resolve_wish, user_ids
from .schema import FIELDS
from .statistics import subscription_history


class DoubanWishPlugin(PluginBase):
    disabled_read_actions = ("statistics",)
    manifest = PluginManifest(
        id="douban-wish", name="豆瓣想看", version="1.0.0",
        entrypoint="plugin:DoubanWishPlugin", description="同步豆瓣用户的公开想看记录，检查入库情况后自动添加订阅。",
        icon="mdi-movie-search-outline", frontend_module="frontend.js", schedule_seconds=1800,
        permissions=(PluginPermission.MEDIA_DISCOVER, PluginPermission.SUBSCRIPTION_CREATE,
                     PluginPermission.MEDIA_SERVER_READ, PluginPermission.NOTIFICATION_SEND),
        capabilities=("scheduled_task", "statistics_page"),
        config_schema={"description_display": "hidden", "layout": {"columns": 2, "row_gap": 14, "column_gap": 16}, "fields": FIELDS},
    )

    async def handle_api(self, request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        if request.action != "statistics" or request.method != "GET":
            raise KeyError("豆瓣想看页面操作不存在")
        history = subscription_history(context.items, int(request.query.get("page", "1")))
        history["latest_run"] = context.state.get("latest_run_statistics")
        history["cumulative"] = cumulative_statistics(history["latest_run"])
        return history

    async def run(self, context: PluginContext) -> dict[str, Any]:
        users = user_ids(context.config.get("users"))
        days = int(context.config.get("days", 7))
        if not 1 <= days <= 3650:
            raise ValueError("同步天数必须为1至3650")
        if context.config.get("clear") is True:
            context.items.clear_once("clear")
            context.config["clear"] = False
        actions: list[dict[str, Any]] = []
        save_run_snapshot(context.state, actions, "running")
        try:
            result = await self._sync(context, users, days, actions)
        except BaseException:
            save_run_snapshot(context.state, actions, "failed")
            raise
        save_run_snapshot(context.state, actions, "failed" if result["failed_users"] else "completed")
        if context.config.get("notification_enabled") and result["updated_count"]:
            await context.notifications.send("豆瓣想看同步完成", f"新增订阅 {result['updated_count']} 项", notification_type="plugin")
        return result

    async def _sync(self, context: PluginContext, users: list[str], days: int, actions: list[dict[str, Any]]) -> dict[str, Any]:
        seen: set[str] = set()
        failed = []
        for user in users:
            try:
                entries = await read_user(user, days, proxy=bool(context.config.get("proxy")))
            except Exception:
                failed.append(user)
                actions.append({"title": f"用户 {user}", "board": user, "status": "unknown", "reason": "feed_unavailable"})
                continue
            for entry in entries:
                key = f"wish:{entry['source_id']}"
                if key in seen:
                    continue
                seen.add(key)
                action = await self._admit(context, key, entry)
                actions.append({**entry, "board": user, **action})
        return {"candidate_count": len(seen), "updated_count": sum(row.get("status") == "subscribed" for row in actions), "failed_users": failed, "actions": actions}

    @staticmethod
    async def _admit(context: PluginContext, key: str, entry: dict[str, Any]) -> dict[str, Any]:
        if context.items.processed(key):
            return {"status": "skipped", "reason": "already_processed"}
        try:
            media = await resolve_wish(context.media, entry)
            if media is None:
                return {"status": "not_recognized", "reason": "not_recognized"}
            result = await context.subscriptions.create_checked(key, {**media, "subscription_origin": "豆瓣想看"})
            return {**media, **result}
        except Exception:
            return {"status": "unknown", "reason": "identity_lookup_failed"}


Plugin = DoubanWishPlugin
PLUGIN = DoubanWishPlugin
