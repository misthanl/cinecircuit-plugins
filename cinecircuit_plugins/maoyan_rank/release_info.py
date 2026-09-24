"""Display source release text or explicitly labelled media premiere dates."""

from datetime import date
from typing import Any


def release_info(media: dict[str, Any]) -> str:
    source = media.get("rank_source")
    source = source if isinstance(source, dict) else {}
    original = str(source.get("release_info") or "").strip()
    if original:
        return original
    kind = str(media.get("media_type") or source.get("media_type") or "")
    label = "上映" if kind == "movie" else "剧集首播" if kind in {"tv", "series"} else "首播／上映"
    keys = ("release_date", "date") if kind == "movie" else ("first_air_date", "date")
    for key in keys:
        value = str(media.get(key) or "").strip()
        try:
            parsed = date.fromisoformat(value[:10])
        except ValueError:
            continue
        return f"{label}：{parsed.isoformat()}"
    return ""
