"""Canonical Douban identities shared by board and RSS ingestion."""

from math import isfinite
import re
from typing import Any
import unicodedata


def rating(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("value")
    try:
        number = float(value or 0)
    except (ValueError, TypeError):
        return 0.0
    return max(0.0, min(10.0, number)) if isfinite(number) else 0.0


def subject_id(value: Any) -> str:
    value = str(value or "").removeprefix("douban:")
    if value.isdigit():
        return value
    match = re.search(r"https?://(?:movie|m|www)\.douban\.com/subject/(\d+)(?:/|\b)", value)
    return match[1] if match else ""


def title_key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(char for char in normalized if char.isalnum())


def normalized_media(raw: dict[str, Any], expected_type: str = "") -> dict[str, Any] | None:
    if raw.get("source_key") not in {None, "", "douban"}:
        return None
    identity = subject_id(
        raw.get("douban_id") or raw.get("source_id") or raw.get("id") or raw.get("url")
    )
    kind = str(raw.get("media_type") or raw.get("type") or expected_type)
    kind = "tv" if kind in {"tv", "series", "show"} else kind
    if not identity or kind not in {"tv", "movie"}:
        return None
    if expected_type and kind != expected_type:
        return None
    raw_cover, raw_pic = raw.get("cover"), raw.get("pic")
    cover = raw_cover if isinstance(raw_cover, dict) else {}
    pic = raw_pic if isinstance(raw_pic, dict) else {}
    return {
        **raw,
        "source_key": "douban",
        "source_id": identity,
        "douban_id": identity,
        "item_key": f"douban:{kind}:{identity}",
        "media_type": kind,
        "title": str(raw.get("title") or raw.get("name") or ""),
        "rating": rating(raw.get("rating") or raw.get("vote_average")),
        "poster": raw.get("poster")
        or raw.get("poster_url")
        or cover.get("url")
        or (raw_cover if isinstance(raw_cover, str) else "")
        or pic.get("large")
        or pic.get("normal")
        or "",
    }
