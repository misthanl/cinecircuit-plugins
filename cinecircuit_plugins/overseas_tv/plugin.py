"""Overseas TV discovery and subscription, executed only in the extension worker."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.modules.plugins.contracts import (
    PluginApiRequest,
    PluginBase,
    PluginContext,
    PluginManifest,
)
from app.modules.plugins.permissions import PluginPermission
from .config import SCHEMA, normalized
from .discovery import candidates, discover
from .statistics import subscription_history, save_run_snapshot, cumulative_statistics
from .._shared.rank_logging import result_text


class OverseasTVPlugin(PluginBase):
    manifest = PluginManifest(
        entrypoint="plugin:OverseasTVPlugin",
        id="overseas-tv",
        name="TMDB 剧集追踪",
        version="1.0.0",
        description="按播出平台追踪近期新剧与新季，自动创建订阅。",
        icon="mdi-television-classic",
        permissions=(
            PluginPermission.MEDIA_DISCOVER,
            PluginPermission.SUBSCRIPTION_CREATE,
            PluginPermission.MEDIA_SERVER_READ,
        ),
        capabilities=("media_source", "scheduled_task", "rank_history", "statistics_page"),
        frontend_module="frontend.js",
        schedule_seconds=21600,
        config_schema=SCHEMA,
    )

    async def handle_api(self, request: PluginApiRequest, context: PluginContext):
        if request.action != "statistics" or request.method != "GET":
            raise KeyError("页面操作不存在")
        history = subscription_history(
            context.items, page=int(request.query.get("page", "1")), page_size=8
        )
        history["latest_run"] = context.state.get("latest_run_statistics")
        history["cumulative"] = cumulative_statistics(history["latest_run"])
        return history

    async def run(self, context: PluginContext):
        if not getattr(context.media, "supports_catalog_filters", False):
            raise RuntimeError("请更新主程序以支持平台和播出日期筛选")
        config = normalized(context.config)
        actions: list[dict[str, Any]] = []
        save_run_snapshot(context.state, actions, "running")
        try:
            if config["clear"]:
                if context.items.clear_once("clear") is not None:
                    save_run_snapshot(context.state, [], "running", reset=True)
            result = await self._run(context, config, actions)
        except BaseException:
            save_run_snapshot(context.state, actions, "failed")
            raise
        save_run_snapshot(context.state, actions, "completed")
        return result

    async def _run(self, context, config, actions):
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        added = 0
        seen = set()
        async for card, source_id, label in discover(context, config, today, actions):
            try:
                detail = await self._season_detail(context, source_id)
                rows, reason = candidates(detail, config, today, label)
            except Exception:
                actions.append(
                    {
                        "title": card.get("title"),
                        "board": label,
                        "status": "unknown",
                        "reason": "identity_lookup_failed",
                    }
                )
                continue
            if not rows:
                actions.append(
                    {
                        "title": detail.get("title"),
                        "board": label,
                        "status": "skipped",
                        "reason": reason,
                    }
                )
            for media in rows:
                item_key = f"tmdb:tv:{media['source_id']}:{media['season']}"
                if item_key in seen:
                    continue
                seen.add(item_key)
                result = await self._admit(context, config, media, item_key, added)
                added += result.get("status") == "subscribed"
                actions.append(
                    {"title": media["title"], "season": media["season"], "board": label, **result}
                )
                context.logger.info(
                    "%s %s：%s", media["title"], media["season"], result_text(result)
                )
        return {
            "candidate_count": len(actions),
            "updated_count": added,
            "actions": actions,
        }

    @staticmethod
    async def _season_detail(context, source_id):
        return await context.media.detail(
            "tmdb",
            {
                "source_id": source_id,
                "media_type": "tv",
                "include_extensions": False,
                "include_library": False,
                "include_credits": False,
                "include_recommendations": False,
                "include_seasons": True,
            },
        )

    async def _admit(self, context, config, media, item_key, added):
        if added >= int(config["max_new"]):
            return {"status": "skipped", "reason": "达到每轮新增上限，下次重试"}
        try:
            result = await context.subscriptions.create_checked(item_key, media)
            return {key: result[key] for key in ("status", "reason") if key in result}
        except Exception:
            return {"status": "unknown", "reason": "订阅检查失败，下次重试"}
