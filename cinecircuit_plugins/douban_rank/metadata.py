"""Supplement sparse board entries through the public media SDK."""

import logging
import re
from typing import Any
from urllib.parse import urlsplit

from .media import normalized_media

logger = logging.getLogger(__name__)


def direct_douban_poster(value: Any) -> bool:
    """Douban CDN links need the display URL supplied by the media SDK."""
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return False
    hostname = (parsed.hostname or "").casefold()
    return parsed.scheme in {"http", "https", ""} and (
        hostname == "doubanio.com" or hostname.endswith(".doubanio.com")
    )


def positive_count(value: Any) -> int:
    try:
        return max(0, int(str(value or 0)))
    except (TypeError, ValueError):
        return 0


def needs_metadata(item: dict[str, Any]) -> bool:
    return bool(normalized_media(item)) and (
        not str(item.get("overview") or "").strip()
        or not str(item.get("poster") or "").strip()
        or direct_douban_poster(item.get("poster"))
        or (item.get("media_type") == "tv" and not positive_count(item.get("total_episode")))
    )


def merge_detail(item: dict[str, Any], detail: Any) -> dict[str, Any]:
    if not isinstance(detail, dict):
        return item
    normalized = normalized_media(detail, str(item.get("media_type") or ""))
    if normalized is None or normalized["source_id"] != str(item.get("source_id")):
        return item
    result = dict(item)
    for key in ("overview", "poster"):
        replace_poster = key == "poster" and direct_douban_poster(result.get(key))
        if (not str(result.get(key) or "").strip() or replace_poster) and normalized.get(key):
            result[key] = normalized[key]
            if key == "poster" and normalized.get("original_poster"):
                result["original_poster"] = normalized["original_poster"]
    if item.get("media_type") == "tv" and not positive_count(item.get("total_episode")):
        count = episode_count(item, detail)
        if count:
            result["total_episode"] = count
    return result


def episode_count(item: dict[str, Any], detail: dict[str, Any]) -> int:
    match = re.search(r"\d+", str(item.get("season") or ""))
    season = int(match[0]) if match else 1
    rows = detail.get("seasons")
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and positive_count(row.get("season_number")) == season:
            count = positive_count(row.get("episode_count"))
            if count:
                return count
    return positive_count(detail.get("episodes_count")) if season == 1 else 0


async def supplement(media: Any, item: dict[str, Any]) -> dict[str, Any]:
    result = await _read_metadata(media, item)
    if str(result.get("overview") or "").strip():
        return result
    logger.warning("豆瓣榜单简介未补全，重新获取一次：%s", item.get("source_id"))
    result = await _read_metadata(media, result, refresh=True)
    if not str(result.get("overview") or "").strip():
        logger.warning("豆瓣榜单重试后简介仍为空，继续创建订阅：%s", item.get("source_id"))
    return result


async def _read_metadata(
    media: Any, item: dict[str, Any], *, refresh: bool = False
) -> dict[str, Any]:
    try:
        detail = await media.detail(
            "douban",
            {
                **item,
                "include_extensions": False,
                "include_library": False,
                **({"refresh": True} if refresh else {}),
            },
        )
    except Exception as error:
        logger.warning(
            "豆瓣榜单详情补全失败（%s），保留已有元数据：%s",
            type(error).__name__,
            item.get("source_id"),
        )
        return item
    result = merge_detail(item, detail)
    if result is item:
        logger.warning("豆瓣榜单详情格式或媒体身份不匹配，未合并：%s", item.get("source_id"))
    return result
