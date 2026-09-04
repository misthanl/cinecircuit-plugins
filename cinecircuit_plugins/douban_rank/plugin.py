from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from app.core.http_client import outbound_async_client
from app.modules.plugins.contracts import PluginApiRequest, PluginBase, PluginContext, PluginManifest
from app.modules.plugins.permissions import PluginPermission
from .statistics import subscription_history


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
        description="监控豆瓣热门榜单和自定义 RSS 榜单，按评分过滤后自动添加订阅。",
        icon="mdi-movie-star-outline",
        permissions=(PluginPermission.MEDIA_DISCOVER, PluginPermission.SUBSCRIPTION_CREATE),
        capabilities=("media_source", "scheduled_task", "rank_history", "statistics_page"),
        frontend_module="frontend.js",
        schedule_seconds=6 * 60 * 60,
        config_schema={
            "sections": [
                {
                    "key": "schedule",
                    "title": "执行设置",
                    "description": "设置刷新周期、网络访问和历史记录清理策略。",
                },
                {
                    "key": "rank",
                    "title": "热门榜单",
                    "description": "可同时选择多个豆瓣榜单，重复作品只处理一次。",
                },
                {
                    "key": "rss",
                    "title": "自定义榜单",
                    "description": "通过 RSSHub 或完整 RSS 地址补充其他豆瓣榜单。",
                },
            ],
            "fields": [
                {
                    "key": "cron",
                    "input_type": "cron",
                    "label": "执行周期",
                    "default": "",
                    "placeholder": "5位cron表达式，留空自动",
                    "icon": "mdi-calendar-clock",
                    "section": "schedule",
                },
                {
                    "key": "proxy",
                    "input_type": "switch",
                    "label": "使用系统代理服务器",
                    "default": False,
                    "icon": "mdi-server-network",
                    "section": "schedule",
                },
                {
                    "key": "clear",
                    "input_type": "switch",
                    "label": "下次执行前清理历史记录",
                    "default": False,
                    "icon": "mdi-history",
                    "section": "schedule",
                },
                {
                    "key": "vote",
                    "input_type": "number",
                    "label": "最低评分",
                    "default": 0,
                    "placeholder": "评分大于等于该值才订阅",
                    "icon": "mdi-star-outline",
                    "validation": {"minimum": 0, "maximum": 10},
                    "section": "rank",
                },
                {
                    "key": "ranks",
                    "input_type": "select",
                    "multiple": True,
                    "chips": True,
                    "label": "热门榜单",
                    "default": ["movie-real-time", "tv-hot"],
                    "icon": "mdi-trophy-outline",
                    "section": "rank",
                    "span": True,
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
                    "icon": "mdi-rss",
                    "section": "rss",
                },
                {
                    "key": "rss_addrs",
                    "input_type": "textarea",
                    "label": "自定义榜单地址",
                    "default": "",
                    "placeholder": "每行一个完整 RSS 地址，或 RSSHub 路由",
                    "icon": "mdi-link-variant",
                    "section": "rss",
                    "span": True,
                },
            ],
        },
    )

    async def handle_api(self, request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        if request.action != "statistics" or request.method != "GET":
            raise KeyError("豆瓣榜单页面操作不存在")
        return subscription_history(context.items, page=int(request.query.get("page", "1")))

    async def run(self, context: PluginContext) -> dict[str, Any]:
        selected = self._list(context.config.get("ranks")) or ["movie-real-time", "tv-hot"]
        minimum = self._rating(context.config.get("vote"))
        candidates: dict[str, dict[str, Any]] = {}
        rank_map = {key: (label, media_type, sort) for key, label, media_type, sort in RANK_OPTIONS}
        for rank in selected:
            if rank not in rank_map:
                continue
            await self._collect_rank(context, rank, rank_map[rank], minimum, candidates)
        for item in await self._rss_candidates(context):
            candidates.setdefault(str(item["item_key"]), item)
        actions = await self._apply_candidates(context, candidates)
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
        label, media_type, sort = settings
        count = 250 if rank == "movie-top250-full" else 10 if rank == "movie-top250" else 30
        result = await context.media.discover(
            {"source": "douban", "media_type": media_type, "sort": sort, "page": 1, "count": count}
        )
        for position, item in enumerate(list(result.get("items") or []), 1):
            rating = self._rating(item.get("rating") or item.get("vote_average"))
            if minimum and rating < minimum:
                continue
            source_id = str(
                item.get("douban_id") or item.get("source_id") or item.get("id") or ""
            ).replace("douban:", "")
            key = f"douban:{media_type}:{source_id or item.get('title', '')}"
            candidates.setdefault(
                key,
                {
                    **item,
                    "item_key": key,
                    "media_type": media_type,
                    "douban_id": source_id,
                    "rating": rating,
                    "rank": position,
                    "board": label,
                },
            )

    @staticmethod
    async def _apply_candidates(
        context: PluginContext, candidates: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for key, candidate in candidates.items():
            if context.items.processed(key):
                actions.append({"item_key": key, "status": "skipped"})
                continue
            result = await context.subscriptions.create(key, {**candidate, "source": "douban"})
            actions.append({"item_key": key, **result})
        return actions

    async def _rss_candidates(self, context: PluginContext) -> list[dict[str, Any]]:
        addresses = self._list(context.config.get("rss_addrs"))
        if not addresses:
            return []
        rsshub = str(context.config.get("rsshub") or "https://rsshub.app").rstrip("/")
        output: list[dict[str, Any]] = []
        async with outbound_async_client(None, timeout=25, follow_redirects=True) as client:
            for address in addresses:
                url = (
                    address
                    if address.startswith(("http://", "https://"))
                    else f"{rsshub}/{address.lstrip('/')}"
                )
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    root = ET.fromstring(response.content)
                except Exception as error:
                    context.logger.warning("豆瓣自定义榜单读取失败：%s - %s", url, error)
                    continue
                for entry in list(root.findall(".//item")) + list(root.findall(".//{*}entry")):
                    title = str(entry.findtext("title") or entry.findtext("{*}title") or "").strip()
                    if not title:
                        continue
                    year_match = re.search(r"(?:19|20)\d{2}", title)
                    media_type = "tv" if re.search(r"电视剧|剧集|综艺|TV", title, re.I) else "movie"
                    match = await context.media.search(
                        re.sub(r"\s*\((?:19|20)\d{2}\).*", "", title), source="douban", count=5
                    )
                    media = next(iter(list(match.get("items") or [])), None)
                    if not media:
                        continue
                    source_id = str(
                        media.get("douban_id") or media.get("source_id") or media.get("id") or ""
                    ).replace("douban:", "")
                    key = f"douban:{media_type}:{source_id or title}"
                    output.append(
                        {
                            **media,
                            "item_key": key,
                            "media_type": media_type,
                            "douban_id": source_id,
                            "year": year_match.group(0) if year_match else media.get("year"),
                            "board": "自定义 RSS 榜单",
                        }
                    )
        return output

    @staticmethod
    def _list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [item.strip() for item in re.split(r"[\n,，]+", str(value or "")) if item.strip()]

    @staticmethod
    def _rating(value: object) -> float:
        try:
            return max(0.0, min(10.0, float(str(value or 0))))
        except (TypeError, ValueError):
            return 0.0


Plugin = DoubanWatchlistPlugin
PLUGIN = DoubanWatchlistPlugin
