"""Bounded, run-scoped access to the platforms' public web rankings."""

import asyncio
import json
from html.parser import HTMLParser
from typing import Any

import httpx

from .requests import BoardRequestError, USER_AGENT
from .settings import CATEGORIES, PLATFORMS
from .youku_search import fetch as fetch_youku_search

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


async def read_page(client, url, **kwargs):
    # Always close streams, including oversized responses and task cancellation.
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    async with client.stream("GET", url, headers=headers, **kwargs) as response:
        if response.status_code != 200:
            raise BoardRequestError(f"HTTP {response.status_code}")
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                raise BoardRequestError("榜单响应超过大小限制")
            body.extend(chunk)
        return body.decode("utf-8")


async def read_json(client, url, **kwargs):
    return json.loads(await read_page(client, url, **kwargs))


class TencentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.output = {}
        self.heading = ""
        self.in_heading = False
        self.in_list = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if "mod_rank_figure" in classes:
            self.heading = ""
        if tag == "h3" and "title" in classes:
            self.in_heading = True
        if tag == "ol" and "hotlist" in classes:
            self.in_list = True
        if (
            tag == "a"
            and self.in_list
            and self.heading in CATEGORIES.values()
            and attrs.get("title")
        ):
            rows = self.output.setdefault(self.heading, [])
            if len(rows) < 10:
                rows.append({"title": attrs["title"]})

    def handle_data(self, data):
        if self.in_heading:
            self.heading += data.strip()

    def handle_endtag(self, tag):
        if tag == "h3":
            self.in_heading = False
        if tag == "ol":
            self.in_list = False


def parse_tencent(text):
    parser = TencentParser()
    parser.feed(text)
    parser.close()
    return parser.output


async def tencent(client):
    return parse_tencent(await read_page(client, "https://v.qq.com/biu/ranks"))


async def mango(client):
    data = await read_json(
        client,
        "https://mobileso.bz.mgtv.com/pc/suggest/v1",
        params={"src": "mgtv", "q": "", "pc": "1"},
    )
    return {
        group["label"]: [{"title": row.get("name", "")} for row in group.get("data", [])[:10]]
        for group in data.get("data", {}).get("topList", [])
        if group.get("label") in CATEGORIES.values()
    }


async def iqiyi(client):
    # The current website search menu shares these category boards with the app.
    data = await read_json(
        client,
        "https://mesh.if.iqiyi.com/portal/lw/search/keywords/hotList",
        params={"v": "17.094.26512", "appMode": "", "src": ""},
    )
    return {
        group["title"]: [
            {"title": row.get("title", ""), "platform_id": str(row.get("qipuId", ""))}
            for row in group.get("items", [])[:10]
        ]
        for group in data.get("hotQuery", [])
        if group.get("title") in CATEGORIES.values()
    }


async def youku(client):
    return await fetch_youku_search(client, read_json)

async def retry(operation):
    for attempt in range(2):
        try:
            return await operation()
        except (
            httpx.HTTPError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
            AttributeError,
            BoardRequestError,
        ) as error:
            message = str(error) if isinstance(error, BoardRequestError) else type(error).__name__
            if attempt:
                raise BoardRequestError(message) from None
        await asyncio.sleep(1)


async def collect(client, config):
    """Each response is discarded after extraction; no global data or session cache."""
    rows: list[dict[str, Any]] = []
    for platform, label in PLATFORMS.items():
        if not config.get(f"{platform}_enabled"):
            continue
        categories = [
            key
            for key in config["platform_types"]
            if not (platform == "mg" and key == "documentary")
        ]
        if not categories:
            continue
        try:
            limit = max(1, min(10, int(config.get(f"{platform}_num") or 10)))
        except (ValueError, TypeError):
            limit = 10
        groups = {}
        try:
            fetch = {"tx": tencent, "iqy": iqiyi, "mg": mango, "yk": youku}[platform]
            groups = await retry(lambda: fetch(client.client))
            for category in categories:
                board = f"{label}{CATEGORIES[category]}热搜榜"
                try:
                    entries = groups.get(CATEGORIES[category], [])
                    rows.extend(board_rows(entries, limit, board, label, category))
                    client.succeeded += 1
                except BoardRequestError as error:
                    client.errors.append(f"{board}：{error}")
        except BoardRequestError as error:
            client.errors.append(f"{label}榜单：{error}")
        finally:
            if groups is not None:
                groups.clear()
    return rows


def board_rows(entries, limit, board, label, category):
    if not entries or not all(str(entry.get("title", "")).strip() for entry in entries):
        raise BoardRequestError("未返回有效榜单条目")
    media_type = (
        "movie"
        if category == "movie"
        else "mixed"
        if category in {"anime", "documentary"}
        else "tv"
    )
    return [
        {
            **entry,
            "rank": index + 1,
            "board": board,
            "platform": label,
            "category": category,
            "media_type": media_type,
        }
        for index, entry in enumerate(entries[:limit])
    ]
