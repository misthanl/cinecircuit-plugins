from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.http_client import outbound_async_client
from app.modules.plugins.contracts import PluginApiRequest, PluginBase, PluginContext, PluginManifest
from app.modules.plugins.permissions import PluginPermission
from .statistics import subscription_history


PLATFORM_OPTIONS = (
    ("all", "全网", ""),
    ("tx", "腾讯视频", "3"),
    ("iqy", "爱奇艺", "2"),
    ("mg", "芒果 TV", "7"),
    ("yk", "优酷", "1"),
)


class MaoyanWatchlistPlugin(PluginBase):
    """跟踪猫眼热度榜并将符合条件的作品加入订阅。"""

    manifest = PluginManifest(
        entrypoint="plugin:MaoyanWatchlistPlugin",
        id="maoyan-rank",
        name="猫眼榜单追踪",
        version="1.0.0",
        description="监控猫眼电影票房与剧集、网剧、综艺、网络电影热度榜并自动添加订阅。",
        icon="mdi-cat",
        permissions=(PluginPermission.MEDIA_DISCOVER, PluginPermission.SUBSCRIPTION_CREATE),
        capabilities=("media_source", "scheduled_task", "rank_history", "statistics_page"),
        frontend_module="frontend.js",
        schedule_seconds=6 * 60 * 60,
        config_schema={
            "sections": [
                {
                    "key": "schedule",
                    "title": "执行设置",
                    "description": "定时刷新猫眼榜单并过滤已经处理过的条目。",
                },
                {
                    "key": "rank",
                    "title": "榜单范围",
                    "description": "选择需要跟踪的电影、电视剧、网剧、综艺和网络电影榜单。",
                },
                {
                    "key": "platform",
                    "title": "剧集平台",
                    "description": "各平台开关并行生效，重复作品会自动去重。",
                },
            ],
            "fields": [
                {
                    "key": "cron",
                    "input_type": "cron",
                    "label": "执行周期",
                    "default": "",
                    "placeholder": "5位cron表达式，留空自动",
                    "description": "留空时每 6 小时刷新一次；已处理作品自动去重。",
                    "icon": "mdi-calendar-clock",
                    "section": "schedule",
                },
                {
                    "key": "clear",
                    "input_type": "switch",
                    "label": "下次执行前清理历史记录",
                    "default": False,
                    "description": "仅下一次执行生效；清理后榜单作品会重新进入订阅判断。",
                    "icon": "mdi-history",
                    "section": "schedule",
                },
                {
                    "key": "type",
                    "input_type": "select",
                    "multiple": True,
                    "label": "订阅类型",
                    "default": ["movie"],
                    "icon": "mdi-format-list-bulleted",
                    "section": "rank",
                    "description": "电影与剧集榜可同时选择，重复作品只订阅一次。",
                    "options": [
                        {"value": "movie", "label": "电影票房榜单"},
                        {"value": "web-heat", "label": "电视剧热度榜单"},
                        {"value": "web-tv", "label": "网剧热度榜单"},
                        {"value": "zongyi", "label": "综艺热度榜单"},
                        {"value": "web-movie", "label": "网络电影榜单"},
                    ],
                },
                {
                    "key": "num",
                    "input_type": "select",
                    "label": "电影榜单条数",
                    "default": "10",
                    "description": "每次从所选电影类榜单顶部读取的作品数量。",
                    "icon": "mdi-numeric",
                    "section": "rank",
                    "options": [
                        {"value": str(value), "label": str(value)} for value in (1, 2, 3, 5, 7, 10)
                    ],
                },
                *[
                    {
                        "key": f"{key}_enabled",
                        "input_type": "switch",
                        "label": f"{label}热门订阅",
                        "default": key == "all",
                        "icon": "mdi-television",
                        "section": "platform",
                        "description": f"开启后读取{label}剧集热度榜。",
                    }
                    for key, label, _ in PLATFORM_OPTIONS
                ],
                *[
                    {
                        "key": f"{key}_num",
                        "input_type": "select",
                        "label": f"{label}榜单条数",
                        "default": "10",
                        "icon": "mdi-numeric",
                        "section": "platform",
                        "description": f"每次从{label}热度榜顶部读取的作品数量。",
                        "options": [
                            {"value": str(value), "label": str(value)}
                            for value in (1, 2, 3, 5, 7, 10)
                        ],
                    }
                    for key, label, _ in PLATFORM_OPTIONS
                ],
            ],
        },
    )

    async def handle_api(self, request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        if request.action != "statistics" or request.method != "GET":
            raise KeyError("猫眼榜单页面操作不存在")
        page = int(request.query.get("page", "1"))
        return subscription_history(context.items, page=page, page_size=8)

    async def run(self, context: PluginContext) -> dict[str, Any]:
        config = context.config
        if bool(config.get("clear")):
            context.logger.info("已按设置开始新的猫眼榜单处理批次")
        selected = self._string_list(config.get("type")) or ["movie"]
        async with outbound_async_client(None, timeout=25, follow_redirects=True) as client:
            movie_rows = await self._movie_candidates(client, config, selected)
            tv_rows = await self._television_candidates(client, config, selected)
        rows = self._dedupe(movie_rows, "movie") + self._dedupe(tv_rows, "tv")
        actions = await self._subscribe_candidates(context, rows)
        return {
            "candidate_count": len(rows),
            "updated_count": sum(1 for row in actions if row.get("status") == "subscribed"),
            "candidates": rows,
            "actions": actions,
        }

    async def _movie_candidates(
        self, client: Any, config: dict[str, Any], selected: list[str]
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if "movie" in selected:
            payload = (await client.get("https://piaofang.maoyan.com/dashboard-ajax/movie")).json()
            entries = list((payload.get("movieList") or {}).get("list") or [])
            rows.extend(
                {
                    "title": str((row.get("movieInfo") or {}).get("movieName") or ""),
                    "release_info": str((row.get("movieInfo") or {}).get("releaseInfo") or ""),
                    "rank": index + 1,
                    "board": "电影票房榜",
                }
                for index, row in enumerate(entries[: self._count(config.get("num"))])
            )
        if "web-movie" in selected:
            rows.extend(await self._web_movie_candidates(client, config))
        return rows

    async def _web_movie_candidates(
        self, client: Any, config: dict[str, Any]
    ) -> list[dict[str, Any]]:
        today = datetime.now().strftime("%Y-%m-%d")
        url = f"https://piaofang.maoyan.com/dashboard/webMaoYanHotData?seriesType=0&platform=20&date={today}&networkHot=3"
        payload = (await client.get(url)).json()
        entries = list((payload.get("data") or {}).get("list") or [])
        return [
            {
                "title": str(row.get("name") or ""),
                "release_info": "",
                "rank": index + 1,
                "board": "网络电影榜",
                "platform": str(row.get("platformDesc") or ""),
            }
            for index, row in enumerate(entries[: self._count(config.get("num"))])
        ]

    async def _television_candidates(
        self, client: Any, config: dict[str, Any], selected: list[str]
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        series_types = (
            ("web-heat", "0", "电视剧"),
            ("web-tv", "1", "网剧"),
            ("zongyi", "2", "综艺"),
        )
        for type_key, series_type, type_label in series_types:
            if type_key not in selected:
                continue
            for platform_key, platform_label, platform_value in PLATFORM_OPTIONS:
                if not bool(config.get(f"{platform_key}_enabled", platform_key == "all")):
                    continue
                url = f"https://piaofang.maoyan.com/dashboard/webHeatData?seriesType={series_type}&platformType={platform_value}&showDate=2"
                payload = (await client.get(url)).json()
                limit = self._count(config.get(f"{platform_key}_num"))
                entries = list((payload.get("dataList") or {}).get("list") or [])
                rows.extend(
                    {
                        "title": str((row.get("seriesInfo") or {}).get("name") or ""),
                        "release_info": str((row.get("seriesInfo") or {}).get("releaseInfo") or ""),
                        "rank": index + 1,
                        "board": f"{platform_label}{type_label}榜",
                        "platform": str(
                            (row.get("seriesInfo") or {}).get("platformDesc") or platform_label
                        ),
                    }
                    for index, row in enumerate(entries[:limit])
                )
        return rows

    async def _subscribe_candidates(
        self, context: PluginContext, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for row in rows:
            if not row["title"]:
                continue
            item_key = f"maoyan:{row['media_type']}:{row['title']}"
            if context.items.processed(item_key):
                actions.append({**row, "status": "skipped"})
                continue
            matches = await context.media.search(row["title"], source="tmdb", count=8)
            match = self._best_match(
                list(matches.get("items") or []), row["title"], row["media_type"]
            )
            if match is None:
                context.items.record(
                    item_key, "ignored", payload=row, result={"reason": "not_recognized"}
                )
                actions.append({**row, "status": "not_recognized"})
                continue
            result = await context.subscriptions.create(
                item_key,
                {**match, "media_type": row["media_type"], "source": "maoyan", "rank_source": row},
            )
            actions.append({**row, **result})
        return actions

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item)]
        return [
            item.strip() for item in str(value or "").replace("，", ",").split(",") if item.strip()
        ]

    @staticmethod
    def _count(value: object) -> int:
        try:
            return max(1, min(10, int(str(value or 10))))
        except (TypeError, ValueError):
            return 10

    @staticmethod
    def _dedupe(rows: list[dict[str, Any]], media_type: str) -> list[dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for row in rows:
            title = str(row.get("title") or "").strip()
            if title and title not in output:
                output[title] = {**row, "media_type": media_type}
        return list(output.values())

    @staticmethod
    def _best_match(
        items: list[dict[str, Any]], title: str, media_type: str
    ) -> dict[str, Any] | None:
        normalized = title.casefold().replace(" ", "")
        typed = [
            item
            for item in items
            if str(item.get("media_type") or "").casefold()
            in {media_type, "series" if media_type == "tv" else "movie"}
        ]
        exact = [
            item
            for item in typed
            if str(item.get("title") or "").casefold().replace(" ", "") == normalized
        ]
        candidates = exact or typed or items
        return candidates[0] if candidates else None


Plugin = MaoyanWatchlistPlugin
PLUGIN = MaoyanWatchlistPlugin
