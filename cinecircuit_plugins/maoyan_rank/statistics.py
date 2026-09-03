from typing import Any


def subscription_history(items: Any, page: int = 1, page_size: int = 8) -> dict[str, Any]:
    """Project this plugin's successful subscriptions into its statistics page."""
    records = []
    platforms: set[str] = set()
    movie_count = 0
    tv_count = 0
    offset = 0
    while True:
        rows = items.list(500, offset=offset, status="subscribed")
        for row in rows:
            media = row["payload"]
            source = media.get("rank_source")
            source = source if isinstance(source, dict) else {}
            media_type = str(media.get("media_type") or source.get("media_type") or "")
            platform = str(source.get("platform") or "").strip()
            if platform and platform not in {"未知", "全网", "多平台播放"}:
                platforms.add(platform)
            if media_type == "movie":
                movie_count += 1
                media_label = "电影"
            elif media_type in {"tv", "series"}:
                tv_count += 1
                media_label = "综艺" if "综艺" in str(source.get("board") or "") else "电视剧"
            else:
                media_label = "未知类型"
            records.append({
                "id": row["id"],
                "title": str(media.get("title") or source.get("title") or "未命名作品"),
                "poster": str(media.get("poster") or media.get("poster_url") or ""),
                "media_type": media_type,
                "media_label": media_label,
                "platform": platform or "未知",
                "release_info": str(source.get("release_info") or ""),
                "subscribed_at": row["updated_at"],
            })
        if len(rows) < 500:
            break
        offset += len(rows)
    total = len(records)
    page_size = max(1, min(100, int(page_size)))
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(pages, int(page)))
    start = (page - 1) * page_size
    return {
        "items": records[start:start + page_size],
        "total": total,
        "movie_count": movie_count,
        "tv_count": tv_count,
        "platform_count": len(platforms),
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }
