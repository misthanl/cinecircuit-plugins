from math import isfinite
from typing import Any

from .._shared.rank_statistics import (
    cumulative_statistics as cumulative_statistics,
    save_run_snapshot as save_run_snapshot,
    history_page,
    media_counts,
    media_label,
)


def _rating(value: object) -> float | None:
    try:
        rating = float(str(value))
    except (TypeError, ValueError):
        return None
    return round(rating, 1) if isfinite(rating) and 0 < rating <= 10 else None


def _record(row: dict[str, Any]) -> dict[str, Any]:
    media = row["payload"]
    kind = str(media.get("media_type") or "")
    board = str(media.get("board") or "").strip()
    return {
        "id": row["id"],
        "title": str(media.get("title") or "未命名作品"),
        "poster": str(media.get("poster") or media.get("poster_url") or ""),
        "media_type": kind,
        "media_label": media_label(kind, board),
        "board": board or "未知榜单",
        "rating": _rating(media.get("rating") or media.get("vote_average")),
        "subscribed_at": row["updated_at"],
    }


def subscription_history(items: Any, page: int = 1) -> dict[str, Any]:
    result = history_page(items, page, 8, {"media_type": ("media_type",), "board": ("board",)})
    groups = result.pop("groups")
    boards = {str(row["values"]["board"]).strip() for row in groups} - {"", "未知榜单"}
    return {
        **result,
        **media_counts(groups),
        "board_count": len(boards),
        "items": [_record(row) for row in result["items"]],
    }
