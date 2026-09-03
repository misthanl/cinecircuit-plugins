from math import isfinite
from typing import Any


def _rating(value: object) -> float | None:
    try:
        rating = float(str(value))
    except (TypeError, ValueError):
        return None
    return round(rating, 1) if isfinite(rating) and 0 < rating <= 10 else None


def subscription_history(items: Any, page: int = 1) -> dict[str, Any]:
    """Present this plugin's successful subscriptions, including saved board and rating."""
    records = []
    boards: set[str] = set()
    movie_count = 0
    tv_count = 0
    offset = 0
    while True:
        rows = items.list(500, offset=offset, status="subscribed")
        for row in rows:
            media = row["payload"]
            media_type = str(media.get("media_type") or "")
            board = str(media.get("board") or "").strip()
            if board and board != "未知榜单":
                boards.add(board)
            if media_type == "movie":
                movie_count += 1
                media_label = "电影"
            elif media_type in {"tv", "series"}:
                tv_count += 1
                media_label = "综艺" if "综艺" in board else "电视剧"
            else:
                media_label = "未知类型"
            records.append({
                "id": row["id"],
                "title": str(media.get("title") or "未命名作品"),
                "poster": str(media.get("poster") or media.get("poster_url") or ""),
                "media_type": media_type,
                "media_label": media_label,
                "board": board or "未知榜单",
                "rating": _rating(media.get("rating") or media.get("vote_average")),
                "subscribed_at": row["updated_at"],
            })
        if len(rows) < 500:
            break
        offset += len(rows)
    total = len(records)
    page_size = 8
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(pages, int(page)))
    start = (page - 1) * page_size
    return {
        "items": records[start:start + page_size],
        "total": total,
        "movie_count": movie_count,
        "tv_count": tv_count,
        "board_count": len(boards),
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }
