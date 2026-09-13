from __future__ import annotations

from .history_identity import item_key as history_item_key, processed as history_processed

from datetime import datetime
from zoneinfo import ZoneInfo
import re
from typing import Any

from app.modules.plugins.runtime_services import http_client
from app.modules.plugins.contracts import PluginApiRequest, PluginBase, PluginContext, PluginManifest
from app.modules.plugins.permissions import PluginPermission
from .statistics import subscription_history, save_run_snapshot, cumulative_statistics
from .identity import match_identity, exact_candidates
from .prefetch import identity_prefetch
from .timing import stage_timing


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
        description="跟踪猫眼影视榜单，筛选作品并自动添加订阅。",
        icon="mdi-movie-search-outline",
        permissions=(PluginPermission.MEDIA_DISCOVER, PluginPermission.SUBSCRIPTION_CREATE,
                     PluginPermission.MEDIA_SERVER_READ),
        capabilities=("media_source", "scheduled_task", "rank_history", "statistics_page"),
        frontend_module="frontend.js",
        schedule_seconds=6 * 60 * 60,
        config_schema={
            "description_display": "hidden",
            "layout": {"columns": 2, "row_gap": 14, "column_gap": 16},
            "fields": [
                {
                    "key": "clear",
                    "input_type": "switch",
                    "label": "清理历史记录",
                    "default": False,
                },
                {
                    "key": "cron",
                    "input_type": "cron",
                    "label": "执行周期",
                    "default": "",
                    "placeholder": "5位cron表达式，留空自动",
                    "description": "留空时每 6 小时刷新一次；已处理作品自动去重。",
                },
                {
                    "key": "type",
                    "input_type": "select",
                    "multiple": True,
                    "label": "订阅类型",
                    "default": ["movie"],
                    "required": True,
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
                    "label": "电影票房榜条数",
                    "default": "10",
                    "description": "每次从所选电影类榜单顶部读取的作品数量。",
                    "options": [
                        {"value": str(value), "label": str(value)} for value in (1, 2, 3, 5, 7, 10)
                    ],
                },
                {
                    "key": "web_movie_num",
                    "input_type": "select",
                    "label": "网络电影榜条数",
                    "default": "10",
                    "options": [
                        {"value": str(value), "label": str(value)} for value in (1, 2, 3, 5, 7, 10)
                    ],
                },
                *[
                    field
                    for key, label, _ in PLATFORM_OPTIONS
                    for field in (
                        {
                            "key": f"{key}_enabled",
                            "input_type": "switch",
                            "label": f"{label}热门订阅",
                            "default": False,
                            "description": f"开启后读取{label}的电视剧、网剧和综艺热度榜。",
                        },
                        {
                            "key": f"{key}_num",
                            "input_type": "select",
                            "label": f"{label}榜单条数",
                            "default": "10",
                            "description": f"每次从{label}热度榜顶部读取的作品数量。",
                            "options": [
                                {"value": str(value), "label": str(value)}
                                for value in (1, 2, 3, 5, 7, 10)
                            ],
                        },
                    )
                ],
            ],
        },
    )

    async def handle_api(self, request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        if request.action != "statistics" or request.method != "GET":
            raise KeyError("猫眼榜单页面操作不存在")
        page = int(request.query.get("page", "1"))
        history = subscription_history(context.items, page=page, page_size=8)
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
        save_run_snapshot(state, actions, "completed")
        return result

    async def _run(self, context: PluginContext, actions: list[dict[str, Any]]) -> dict[str, Any]:
        config = context.config
        selected = self._string_list(config.get("type", ["movie"]))
        if not selected:
            raise ValueError("请至少选择一个榜单")
        if config.get("clear") is True:
            clear_once = getattr(context.items, "clear_once", None)
            if not callable(clear_once):
                raise RuntimeError("当前主程序不支持历史清理，请先更新主程序")
            cleared = clear_once("clear")
            config["clear"] = False
            if cleared is not None:
                save_run_snapshot(getattr(context, "state", None), [], "running", reset=True)
                context.logger.info("已清理 %s 条榜单处理记录，已有订阅保留", cleared)
        async with http_client(timeout=25, follow_redirects=True) as client:
            board_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
            with stage_timing(context, "movie_boards"):
                movie_rows = await self._movie_candidates(client, config, selected)
            with stage_timing(context, "tv_boards"):
                tv_rows = await self._television_candidates(client, config, selected)
        rows = self._dedupe(movie_rows, "movie") + self._dedupe(tv_rows, "tv")
        for row in rows:
            row.setdefault("board_date", board_date)
        actions = await self._subscribe_candidates(context, rows, actions=actions)
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
                    "maoyan_id": str((row.get("movieInfo") or {}).get("movieId") or ""),
                    "year": str((row.get("movieInfo") or {}).get("year") or ""),
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
            for index, row in enumerate(entries[: self._count(config.get("web_movie_num") or config.get("num"))])
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
                if not bool(config.get(f"{platform_key}_enabled", False)):
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
        self, context: PluginContext, rows: list[dict[str, Any]], *, actions: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        actions = actions if actions is not None else []
        checked: dict[str, dict[str, Any]] = {}
        identity_cache: dict = {}
        create_checked = getattr(context.subscriptions, "create_checked", None)
        if not callable(create_checked):
            raise RuntimeError("当前主程序不支持订阅前入库检查，请先更新主程序")
        async with identity_prefetch(context, rows, self._prepare_identity, identity_cache) as prepared:
            async for row, task in prepared:
                if not row["title"]:
                    continue
                try:
                    match = await task
                except Exception:
                    actions.append({**row, "status": "unknown", "reason": "identity_lookup_failed"})
                    context.logger.info("%s：媒体识别查询失败，下次重试", row["title"])
                    continue
                if match is None:
                    actions.append({**row, "status": "not_recognized"})
                    context.logger.info("%s：未确认媒体身份，下次重试", row["title"])
                    continue
                candidate = self._subscription_candidate(row, match)
                identity = ":".join(str(candidate.get(key) or "") for key in ("media_type", "source_key", "source_id", "season"))
                if identity in checked:
                    actions.append({**row, "status": "skipped", "reason": "same_run_duplicate"})
                    continue
                if history_processed(context.items, candidate, row["title"]):
                    actions.append({**row, "status": "skipped"})
                    continue
                item_key = history_item_key(candidate)
                with stage_timing(context, "create_checked", str(row["title"])):
                    result = await create_checked(item_key, candidate)
                checked[identity] = result
                labels = {"already_subscribed": "已订阅，跳过", "in_library": "已入库，跳过",
                          "unknown": "无法确认，暂缓并在下次重试", "subscribed": "已添加订阅",
                          "duplicate": "已被其他任务订阅，跳过", "skipped": "已处理，跳过"}
                context.logger.info("%s：%s（%s）", row["title"], labels.get(result["status"], result["status"]), result.get("reason", ""))
                actions.append({**row, "season": candidate.get("season", ""), **result})
        return actions

    async def _prepare_identity(self, context: Any, row: dict, cache: dict):
        with stage_timing(context, "identity", row["title"]):
            match = await match_identity(context, row, cache)
        prepare = getattr(context.subscriptions, "prepare_season", None)
        if match is not None and row["media_type"] == "tv" and callable(prepare):
            try:
                with stage_timing(context, "season_prefetch", row["title"]):
                    await prepare(self._subscription_candidate(row, match))
            except Exception:
                context.logger.debug("Season prefetch failed; admission will retry", exc_info=True)
        return match

    def _subscription_candidate(self, row: dict, match: dict) -> dict:
        candidate = {**match, "media_type": row["media_type"], "source": "maoyan", "rank_source": row,
                     "subscription_origin": "猫眼榜单"}
        if row["media_type"] == "tv":
            season = candidate.pop("_maoyan_verified_season", None) or self._title_season(row["title"])
            # Do not reuse a search card's implicit/default season.
            candidate.pop("season", None)
            if season is not None:
                candidate["season"] = f"S{season:02d}"
        return candidate

    @staticmethod
    def _title_season(title: str) -> int | None:
        match = re.search(r"(?:\bS(\d{1,3})\b|第\s*([一二三四五六七八九十百\d]+)\s*季)", title, re.I)
        if not match:
            return None
        value = match[1] or match[2]
        if value.isdigit():
            return int(value)
        digits = {char: number for number, char in enumerate("零一二三四五六七八九", 0)}
        if "百" in value:
            return -1
        if "十" in value:
            left, right = value.split("十", 1)
            return digits.get(left, 1) * 10 + digits.get(right, 0)
        return digits.get(value)

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
        output: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            title = str(row.get("title") or "").strip()
            identity = (str(row.get("maoyan_id") or ""), title, str(row.get("year") or ""))
            if title and identity not in output:
                output[identity] = {**row, "media_type": media_type}
        return list(output.values())

    @staticmethod
    def _best_match(
        items: list[dict[str, Any]], title: str, media_type: str
    ) -> dict[str, Any] | None:
        exact = exact_candidates(items, title, media_type)
        return exact[0] if len(exact) == 1 else None


Plugin = MaoyanWatchlistPlugin
PLUGIN = MaoyanWatchlistPlugin
