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
from .timing import stage_timing
from .boards import read_board
from .media import rating
from .metadata import merge_detail, needs_metadata, supplement
from .rss import read_rss
from .statistics import subscription_history, cumulative_statistics, save_run_snapshot


RANK_OPTIONS = (
    ("movie-ustop", "电影北美票房榜", "movie", "rank"),
    ("movie-weekly", "一周口碑电影榜", "movie", "rank"),
    ("movie-real-time", "实时热门电影", "movie", "hot"),
    ("show-domestic", "热门综艺", "tv", "hot"),
    ("movie-hot-gaia", "热门电影", "movie", "hot"),
    ("tv-hot", "热门电视剧", "tv", "hot"),
    ("movie-top250", "电影 TOP10", "movie", "rank"),
    ("movie-top250-full", "电影 TOP250", "movie", "rank"),
)


class DoubanWatchlistPlugin(PluginBase):
    """跟踪豆瓣榜单并将符合条件的作品加入订阅。"""

    manifest = PluginManifest(
        entrypoint="plugin:DoubanWatchlistPlugin",
        id="douban-hot",
        name="豆瓣榜单追踪",
        version="1.0.1",
        description="跟踪豆瓣热门榜单，筛选作品并自动添加订阅。",
        icon="mdi-movie-search-outline",
        permissions=(
            PluginPermission.MEDIA_DISCOVER,
            PluginPermission.SUBSCRIPTION_CREATE,
            PluginPermission.MEDIA_SERVER_READ,
        ),
        capabilities=("media_source", "scheduled_task", "rank_history", "statistics_page"),
        frontend_module="frontend.js",
        schedule_seconds=6 * 60 * 60,
        config_schema={
            "description_display": "hidden",
            "layout": {"columns": 2, "row_gap": 14, "column_gap": 16},
            "fields": [
                {
                    "key": "cron",
                    "input_type": "cron",
                    "label": "执行周期",
                    "default": "",
                    "placeholder": "5位cron表达式，留空自动",
                    "description": "留空时每 6 小时刷新；已处理作品不会重复订阅。",
                },
                {
                    "key": "proxy",
                    "input_type": "switch",
                    "label": "使用系统代理服务器",
                    "default": False,
                    "description": "仅在直连豆瓣或 RSSHub 失败时开启。",
                },
                {
                    "key": "clear",
                    "input_type": "switch",
                    "label": "下次执行前清理历史记录",
                    "default": False,
                    "description": "仅下一次执行生效；清理后榜单作品可能重新进入订阅判断。",
                },
                {
                    "key": "vote",
                    "input_type": "number",
                    "label": "最低评分",
                    "default": 0,
                    "placeholder": "评分大于等于该值才订阅",
                    "description": "0 表示不过滤；例如设为 7.5，只处理评分不低于 7.5 的作品。",
                    "validation": {"minimum": 0, "maximum": 10},
                },
                {
                    "key": "ranks",
                    "input_type": "select",
                    "multiple": True,
                    "chips": True,
                    "label": "热门榜单",
                    "default": ["movie-real-time", "tv-hot"],
                    "span": True,
                    "description": "可多选。相同作品出现在多个榜单时只处理一次。",
                    "options": [
                        {"value": key, "label": label} for key, label, _, _ in RANK_OPTIONS
                    ],
                },
                {
                    "key": "rsshub",
                    "input_type": "url",
                    "label": "RSSHub 地址",
                    "default": "https://rsshub.app",
                    "placeholder": "https://rsshub.app",
                    "description": "填写可访问的 RSSHub 根地址；使用完整 RSS 地址时不会用到此项。",
                },
                {
                    "key": "rss_addrs",
                    "input_type": "textarea",
                    "label": "自定义榜单地址",
                    "default": "",
                    "placeholder": "每行一个完整 RSS 地址，或 RSSHub 路由",
                    "description": "示例：/douban/movie/playing 或 https://example.com/feed.xml。",
                    "span": True,
                },
            ],
        },
    )

    async def handle_api(self, request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        if request.action != "statistics" or request.method != "GET":
            raise KeyError("豆瓣榜单页面操作不存在")
        history = subscription_history(context.items, page=int(request.query.get("page", "1")))
        state = getattr(context, "state", None)
        history["latest_run"] = state.get("latest_run_statistics") if state is not None else None
        history["cumulative"] = cumulative_statistics(history["latest_run"])
        return history

    async def run(self, context: PluginContext) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        state = getattr(context, "state", None)
        save_run_snapshot(state, actions, "running")
        try:
            with stage_timing(context, "run"):
                result = await self._run(context, actions)
        except BaseException:
            save_run_snapshot(state, actions, "failed")
            raise
        finally:
            release = getattr(context.subscriptions, "release_notification_images", None)
            if callable(release):
                release()
        save_run_snapshot(state, actions, "completed")
        return result

    async def _run(self, context: PluginContext, actions: list[dict[str, Any]]) -> dict[str, Any]:
        if context.config.get("clear") is True:
            clear_once = getattr(context.items, "clear_once", None)
            if not callable(clear_once):
                raise RuntimeError("当前主程序不支持历史清理，请先更新主程序")
            cleared = clear_once("clear")
            context.config["clear"] = False
            if cleared is not None:
                save_run_snapshot(getattr(context, "state", None), [], "running", reset=True)
        selected = self._list(context.config.get("ranks", ["movie-real-time", "tv-hot"]))
        minimum = self._rating(context.config.get("vote"))
        candidates: dict[str, dict[str, Any]] = {}
        rank_map = {key: (label, media_type, sort) for key, label, media_type, sort in RANK_OPTIONS}
        for rank in selected:
            if rank not in rank_map:
                continue
            await self._collect_rank(context, rank, rank_map[rank], minimum, candidates)
        for item in await self._rss_candidates(context):
            if rating(item.get("rating") or item.get("vote_average")) >= minimum:
                candidates.setdefault(str(item["item_key"]), item)
        await self._apply_candidates(context, candidates, actions)
        return {
            "candidate_count": len(candidates),
            "updated_count": sum(1 for item in actions if item.get("status") == "subscribed"),
            "candidates": list(candidates.values()),
            "actions": actions,
        }

    async def _collect_rank(
        self,
        context: PluginContext,
        rank: str,
        settings: tuple[str, str, str],
        minimum: float,
        candidates: dict[str, dict[str, Any]],
    ) -> None:
        label, media_type, _sort = settings
        with stage_timing(context, "board_fetch", rank):
            rows = await read_board(rank, media_type, proxy=bool(context.config.get("proxy")))
        for position, item in enumerate(rows, 1):
            if minimum and not item.get("rating"):
                with stage_timing(context, "rating_identity", str(item["source_id"])):
                    resolved = await context.media.resolve_identity(
                        source="douban", source_id=item["source_id"], media_type=media_type
                    )
                if resolved and str(resolved.get("source_id")) == item["source_id"]:
                    item = {
                        **merge_detail(item, resolved),
                        "rating": rating(resolved.get("rating") or resolved.get("vote_average")),
                        "_detail_checked": True,
                    }
            if rating(item.get("rating")) >= minimum:
                candidates.setdefault(item["item_key"], {**item, "rank": position, "board": label})

    @staticmethod
    async def _apply_candidates(
        context: PluginContext,
        candidates: dict[str, dict[str, Any]],
        actions: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if actions is None:
            actions = []
        entries = list(candidates.items())
        pending: dict[int, asyncio.Task[Any]] = {}
        try:
            for index, (key, candidate) in enumerate(entries):
                for offset in range(index, min(index + 2, len(entries))):
                    if offset not in pending:
                        next_key, item = entries[offset]
                        pending[offset] = asyncio.create_task(
                            DoubanWatchlistPlugin._prepare_candidate(context, next_key, item)
                        )
                prepared = await pending[index]
                result = await DoubanWatchlistPlugin._create_candidate(context, key, prepared)
                del pending[index]
                actions.append({**candidate, "item_key": key, **result})
        finally:
            for task in pending.values():
                task.cancel()
            await asyncio.gather(*pending.values(), return_exceptions=True)
        return actions

    @staticmethod
    async def _prepare_candidate(
        context: PluginContext, key: str, candidate: dict[str, Any]
    ) -> dict[str, Any]:
        item = dict(candidate)
        if (
            not context.items.processed(key)
            and not item.get("_detail_checked")
            and needs_metadata(item)
        ):
            with stage_timing(context, "metadata", key):
                item = await supplement(context.media, item)
            item["_detail_checked"] = True
        prepare_image = getattr(context.subscriptions, "prepare_notification_image", None)
        if not context.items.processed(key) and callable(prepare_image):
            with stage_timing(context, "notification_image", key):
                await prepare_image(item)
        return item

    @staticmethod
    async def _create_candidate(
        context: PluginContext, key: str, candidate: dict[str, Any]
    ) -> dict[str, Any]:
        candidate = dict(candidate)
        detail_checked = candidate.pop("_detail_checked", False)
        if context.items.processed(key):
            return {"status": "skipped"}
        create_checked = getattr(context.subscriptions, "create_checked", None)
        if not callable(create_checked):
            raise RuntimeError("当前主程序不支持订阅前入库检查，请先更新主程序")
        if needs_metadata(candidate) and not detail_checked:
            with stage_timing(context, "metadata", key):
                candidate = await supplement(context.media, candidate)
        with stage_timing(context, "create_checked", key):
            return await create_checked(
                key, {**candidate, "source": "douban", "subscription_origin": "豆瓣榜单"}
            )

    async def _rss_candidates(self, context: PluginContext) -> list[dict[str, Any]]:
        with stage_timing(context, "rss_fetch"):
            return await read_rss(context, self._list(context.config.get("rss_addrs")))

    @staticmethod
    def _list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [item.strip() for item in re.split(r"[\n,，]+", str(value or "")) if item.strip()]

    @staticmethod
    def _rating(value: object) -> float:
        return rating(value)


Plugin = DoubanWatchlistPlugin
PLUGIN = DoubanWatchlistPlugin
