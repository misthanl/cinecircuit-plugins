from typing import Any

from .._shared.rank_statistics import (
    cumulative_statistics as cumulative_statistics,
    save_run_snapshot as _save_run_snapshot,
    history_page,
    media_counts,
    media_label,
)


def _record(row: dict[str, Any]) -> dict[str, Any]:
    media = row["payload"]
    raw_source = media.get("rank_source")
    source = raw_source if isinstance(raw_source, dict) else {}
    kind = str(media.get("media_type") or source.get("media_type") or "")
    platform = str(source.get("platform") or "").strip()
    return {
        "id": row["id"],
        "title": str(media.get("title") or source.get("title") or "未命名作品"),
        "poster": str(media.get("poster") or media.get("poster_url") or ""),
        "media_type": kind,
        "media_label": media_label(kind, str(source.get("board") or "")),
        "platform": platform or "未知",
        "release_info": str(source.get("release_info") or ""),
        "subscribed_at": row["updated_at"],
    }


def subscription_history(items: Any, page: int = 1, page_size: int = 8) -> dict[str, Any]:
    result = history_page(
        items,
        page,
        page_size,
        {
            "media_type": ("media_type", "rank_source.media_type"),
            "platform": ("rank_source.platform",),
        },
    )
    groups = result.pop("groups")
    platforms = {str(row["values"]["platform"]).strip() for row in groups} - {
        "",
        "未知",
        "全网",
        "多平台播放",
    }
    return {
        **result,
        **media_counts(groups),
        "platform_count": len(platforms),
        "items": [_record(row) for row in result["items"]],
    }


def save_run_snapshot(state, actions, status, *, reset=False):
    _save_run_snapshot(state, actions, status, reset=reset)
    snapshot = state.get("latest_run_statistics") if state is not None else None
    if snapshot:
        for row, action in zip(snapshot["items"], actions):
            reason = str(action.get("reason") or "")
            if any("\u4e00" <= char <= "\u9fff" for char in reason):
                row["reason"] = reason
        state.set("latest_run_statistics", snapshot)
