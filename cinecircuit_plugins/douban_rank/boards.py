"""Read each named board from its own public Douban collection/page."""

import re
from typing import Any

from bs4 import BeautifulSoup

from app.modules.plugins.runtime_services import http_client
from .media import normalized_media, subject_id

COLLECTIONS = {
    "movie-real-time": "movie_real_time_hotest",
    "movie-hot-gaia": "movie_hot_gaia",
    "tv-hot": "tv_hot",
    "show-domestic": "show_domestic",
}
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://movie.douban.com/"}


async def read_board(rank: str, media_type: str, *, proxy: bool) -> list[dict[str, Any]]:
    async with http_client(
        timeout=25, follow_redirects=True, headers=HEADERS, use_application_proxy=proxy
    ) as client:
        if rank in COLLECTIONS:
            return await _collection(client, COLLECTIONS[rank], media_type)
        if rank in {"movie-top250", "movie-top250-full"}:
            return await _top_movies(client, 250 if rank.endswith("-full") else 10)
        response = await client.get("https://movie.douban.com/chart")
        response.raise_for_status()
        return chart_rows(response.content, rank)


async def _collection(client: Any, collection: str, media_type: str) -> list[dict[str, Any]]:
    response = await client.get(
        f"https://m.douban.com/rexxar/api/v2/subject_collection/{collection}/items",
        params={"start": 0, "count": 30},
    )
    response.raise_for_status()
    rows = response.json().get("subject_collection_items")
    if not isinstance(rows, list):
        raise ValueError("豆瓣榜单响应不完整")
    return [
        item
        for raw in rows[:30]
        if isinstance(raw, dict) and (item := normalized_media(raw, media_type)) is not None
    ]


def chart_rows(content: bytes, rank: str) -> list[dict[str, Any]]:
    marker = {"movie-ustop": "mv_us_week", "movie-weekly": "mv_week"}[rank]
    soup = BeautifulSoup(content, "html.parser", from_encoding="utf-8")
    try:
        output: dict[str, dict[str, Any]] = {}
        for anchor in soup.select(f'.movie_top a[onclick*="{marker}"]'):
            identity = subject_id(anchor.get("href"))
            item = normalized_media({"id": identity, "title": anchor.get_text(strip=True)}, "movie")
            if item:
                output.setdefault(identity, item)
        if not output:
            raise ValueError("豆瓣榜单暂不可用或页面结构已改变")
        return list(output.values())[:10]
    finally:
        soup.clear(decompose=True)
        soup.decompose()


async def _top_movies(client: Any, limit: int) -> list[dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for offset in range(0, limit, 25):
        response = await client.get("https://movie.douban.com/top250", params={"start": offset})
        response.raise_for_status()
        rows = top_rows(response.content)
        if not rows:
            raise ValueError("豆瓣 TOP250 页面暂不可用")
        for row in rows:
            output.setdefault(row["source_id"], row)
        if len(output) >= limit:
            break
    if len(output) < limit:
        raise ValueError("豆瓣 TOP250 分页不完整，请稍后重试")
    return list(output.values())[:limit]


def top_rows(content: bytes) -> list[dict[str, Any]]:
    soup = BeautifulSoup(content, "html.parser", from_encoding="utf-8")
    try:
        result = []
        for row in soup.select("ol.grid_view > li"):
            anchor, title = row.select_one(".hd a"), row.select_one(".title")
            if anchor is None or title is None:
                continue
            image, score, details = (
                row.select_one("img"),
                row.select_one(".rating_num"),
                row.select_one(".bd p"),
            )
            year = re.search(r"\b(?:19|20)\d{2}\b", details.get_text() if details else "")
            item = normalized_media(
                {
                    "url": anchor.get("href"),
                    "title": title.get_text(strip=True),
                    "rating": score.get_text() if score else 0,
                    "poster": image.get("src") if image else "",
                    "year": year[0] if year else "",
                },
                "movie",
            )
            if item:
                result.append(item)
        return result
    finally:
        soup.clear(decompose=True)
        soup.decompose()
