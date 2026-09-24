from __future__ import annotations

from .release_info import release_info

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
from .requests import BoardClient, BoardRequestError, board_payload
from .settings import CONFIG_SCHEMA, normalized
from .platforms import collect
from .._shared.rank_logging import result_text


class MaoyanWatchlistPlugin(PluginBase):
    """跟踪猫眼热度榜并将符合条件的作品加入订阅。"""

    manifest = PluginManifest(
        entrypoint="plugin:MaoyanWatchlistPlugin",
        id="maoyan-rank",
        name="影视榜单订阅",
        version="1.0.3",
        description="订阅猫眼电影票房榜及腾讯、爱奇艺、芒果、优酷分类榜单。",
        icon="mdi-movie-search-outline",
        permissions=(PluginPermission.MEDIA_DISCOVER, PluginPermission.SUBSCRIPTION_CREATE,
                     PluginPermission.MEDIA_SERVER_READ),
        capabilities=("media_source", "scheduled_task", "rank_history", "statistics_page"),
        frontend_module="frontend.js",
        schedule_seconds=6 * 60 * 60,
        config_schema=CONFIG_SCHEMA,
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
        config = normalized(context.config)
        selected = ["movie"] if config["movie_enabled"] else []
        active = any(config.get(f"{key}_enabled") and any(
            key != "mg" or category != "documentary" for category in config["platform_types"]
        ) for key in ("tx", "iqy", "mg", "yk"))
        if not selected and not active:
            raise ValueError("请开启电影票房榜，或选择媒体分类及支持该分类的平台")
        if config.get("clear") is True:
            clear_once = getattr(context.items, "clear_once", None)
            if not callable(clear_once):
                raise RuntimeError("当前主程序不支持历史清理，请先更新主程序")
            cleared = clear_once("clear")
            config["clear"] = False
            context.config["clear"] = False
            if cleared is not None:
                save_run_snapshot(getattr(context, "state", None), [], "running", reset=True)
                context.logger.info("已清理 %s 条榜单处理记录，已有订阅保留", cleared)
        async with http_client(timeout=25, follow_redirects=True) as transport, BoardClient(transport) as client:
            board_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
            with stage_timing(context, "movie_boards"):
                movie_rows = await self._movie_candidates(client, config, selected)
            with stage_timing(context, "tv_boards"):
                platform_rows = await collect(client, config)
        for error in client.errors:
            context.logger.warning("%s；其余榜单继续处理，下次重试", error)
        if client.errors and not client.succeeded:
            raise BoardRequestError("所选榜单全部获取失败：" + "；".join(client.errors))
        rows = self._dedupe(movie_rows, "movie") + [row for media_type in ("movie", "tv", "mixed")
            for row in self._dedupe([item for item in platform_rows if item["media_type"] == media_type], media_type)]
        for row in rows:
            row.setdefault("board_date", board_date)
        actions = await self._subscribe_candidates(context, rows, actions=actions)
        return {
            "board_errors": client.errors,
            "partial": bool(client.errors),
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
            payload = await board_payload(client, "/dashboard-ajax/movie", "电影票房榜")
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
                context.logger.info("%s：%s", row["title"], result_text(result))
                actions.append({**row, "season": candidate.get("season", ""), **result})
        return actions

    async def _prepare_identity(self, context: Any, row: dict, cache: dict):
        with stage_timing(context, "identity", row["title"]):
            match = await match_identity(context, row, cache)
        if match is not None and row["media_type"] == "mixed":
            row["media_type"] = "tv" if match.get("media_type") in {"tv", "series"} else "movie"
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
                     "subscription_origin": "影视榜单"}
        if row["media_type"] == "tv":
            season = candidate.pop("_maoyan_verified_season", None) or self._title_season(row["title"])
            # Do not reuse a search card's implicit/default season.
            candidate.pop("season", None)
            if season is not None:
                candidate["season"] = f"S{season:02d}"
        candidate["rank_source"] = {**row, "release_info": release_info(candidate)}
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
            elif title and row.get("board") != output[identity].get("board"):
                sources = output[identity].setdefault("board_sources", [
                    {key: output[identity].get(key, "") for key in ("board", "platform", "board_date", "board_period", "rank")}
                ])
                source = {key: row.get(key, "") for key in ("board", "platform", "board_date", "board_period", "rank")}
                if source not in sources:
                    sources.append(source)
        return list(output.values())

    @staticmethod
    def _best_match(
        items: list[dict[str, Any]], title: str, media_type: str
    ) -> dict[str, Any] | None:
        exact = exact_candidates(items, title, media_type)
        return exact[0] if len(exact) == 1 else None


Plugin = MaoyanWatchlistPlugin
PLUGIN = MaoyanWatchlistPlugin
