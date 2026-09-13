"""Shared rank presentation, shipped inside each independent consuming ZIP."""

from datetime import datetime, timezone
from typing import Any

RETRY_STATUSES = {"unknown", "not_recognized"}
COUNT_KEYS = ("checked", "subscribed", "existing", "retry")
REASONS = {
    "identity_incomplete": "媒体身份不完整",
    "not_recognized": "未确认媒体身份",
    "identity_lookup_failed": "媒体识别查询失败",
    "season_ambiguous": "目标季不明确",
    "episode_metadata_unavailable": "季集信息不完整",
    "season_lookup_failed": "季集查询失败",
    "library_unavailable": "媒体服务器不可用或查询不完整",
    "library_lookup_failed": "媒体服务器查询失败",
    "subscription_exists": "已有对应订阅",
    "movie_present": "电影已入库",
    "season_complete": "目标季已齐全",
    "already_processed": "此前已成功添加",
    "same_run_duplicate": "本次重复作品",
    "episodes_missing": "目标季缺集",
    "not_in_library": "媒体库不存在",
}
STATUS_REASONS = {
    "subscribed": "已添加订阅",
    "duplicate": "已有对应订阅",
    "skipped": "此前已成功添加",
    "not_recognized": "未确认媒体身份",
}


def cumulative_statistics(snapshot: Any) -> dict[str, Any]:
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    saved = snapshot.get("cumulative")
    if isinstance(saved, dict):
        return dict(saved)
    return {
        **{key: int(snapshot.get(key) or 0) for key in COUNT_KEYS},
        "since": snapshot.get("updated_at"),
        "legacy_partial": bool(snapshot),
    }


def _action_row(action: dict[str, Any]) -> dict[str, Any]:
    subscription = action.get("subscription") or {}
    status = str(action.get("status") or "unknown")
    reason = str(action.get("reason") or "")
    return {
        "title": str(action.get("title") or "未命名作品")[:180],
        "board": str(action.get("board") or "")[:100],
        "season": str(action.get("season") or subscription.get("season") or "")[:20],
        "status": status,
        "retry": status in RETRY_STATUSES,
        "reason": REASONS.get(reason, STATUS_REASONS.get(status, "下次运行重新检查")),
    }


def save_run_snapshot(
    state: Any, actions: list[dict[str, Any]], status: str, *, reset: bool = False
) -> None:
    if state is None:
        return
    rows = [_action_row(action) for action in actions]
    previous = {} if reset else state.get("latest_run_statistics")
    previous = previous if isinstance(previous, dict) else {}
    totals = cumulative_statistics(previous)
    base = totals if status == "running" else previous.get("cumulative_base", totals)
    now = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "status": status,
        "updated_at": now,
        "items": rows,
        "checked": len(rows),
        "subscribed": sum(row["status"] == "subscribed" for row in rows),
        "existing": sum(
            row["status"] in {"already_subscribed", "in_library", "duplicate", "skipped"}
            for row in rows
        ),
        "retry": sum(row["retry"] for row in rows),
    }
    snapshot["cumulative_base"] = dict(base)
    snapshot["cumulative"] = {
        **base,
        "since": base.get("since") or now,
        **{
            key: int(base.get(key) or 0) + (snapshot[key] if status != "running" else 0)
            for key in COUNT_KEYS
        },
    }
    state.set("latest_run_statistics", snapshot)


def _value(payload: dict[str, Any], paths: tuple[str, ...]) -> str:
    for path in paths:
        value: Any = payload
        for part in path.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if value:
            return str(value)
    return ""


def history_page(
    items: Any, page: int, page_size: int, groups: dict[str, tuple[str, ...]]
) -> dict[str, Any]:
    read = getattr(items, "page", None)
    if callable(read):
        return read(page=page, page_size=page_size, status="subscribed", group_by=groups)
    # Older hosts lack SQL aggregation. Stream totals without retaining all
    # payloads, then request only the visible page; preserve old installations.
    counts: dict[tuple[str, ...], int] = {}
    total = 0
    while True:
        rows = items.list(500, offset=total, status="subscribed")
        for row in rows:
            values = tuple(_value(row["payload"], paths) for paths in groups.values())
            counts[values] = counts.get(values, 0) + 1
        total += len(rows)
        if len(rows) < 500:
            break
    page_size = max(1, min(100, int(page_size)))
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(pages, int(page)))
    return {
        "items": items.list(page_size, offset=(page - 1) * page_size, status="subscribed"),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "groups": [
            {"values": dict(zip(groups, values)), "count": count}
            for values, count in counts.items()
        ],
    }


def media_counts(groups: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "movie_count": sum(
            row["count"] for row in groups if row["values"]["media_type"] == "movie"
        ),
        "tv_count": sum(
            row["count"] for row in groups if row["values"]["media_type"] in {"tv", "series"}
        ),
    }


def media_label(kind: str, board: str) -> str:
    if kind == "movie":
        return "电影"
    if kind in {"tv", "series"}:
        return "综艺" if "综艺" in board else "电视剧"
    return "未知类型"
