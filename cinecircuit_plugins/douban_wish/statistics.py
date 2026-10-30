"""Paginated subscription cards and shared execution counters."""
from math import isfinite
from typing import Any
from .._shared.rank_statistics import history_page, media_counts, media_label


def subscription_history(items: Any, page: int) -> dict[str, Any]:
    result = history_page(items, page, 8, {"media_type": ("media_type",), "board": ("account", "board")})
    groups = result.pop("groups")
    rows = []
    for row in result["items"]:
        value = row["payload"]
        rows.append({"id": row["id"], "title": str(value.get("title") or "未命名作品"), "poster": value.get("poster") or value.get("poster_url") or "", "media_label": media_label(str(value.get("media_type") or ""), ""), "board": str(value.get("account") or value.get("board") or ""), "rating": score(value.get("rating") or value.get("vote_average")), "subscribed_at": row["updated_at"]})
    return {**result, **media_counts(groups), "board_count": len({row["values"]["board"] for row in groups}), "items": rows}


def score(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("value")
    try:
        number = float(str(value))
    except (ValueError, TypeError):
        return None
    return round(number, 1) if isfinite(number) and 0 < number <= 10 else None
