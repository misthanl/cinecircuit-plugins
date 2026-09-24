"""Requests compatible with Maoyan's public dashboard web client."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import random
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

BASE_URL = "https://piaofang.maoyan.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/130.0.0.0 Safari/537.36"
)
# Public web-client protocol constant, not a user credential.
WEB_QUERY_KEY = "A013F70DB97834C0A5492378BD76C53A"


class BoardRequestError(RuntimeError):
    pass


def board_date(pattern: str = "%Y%m%d") -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime(pattern)


def signed_query(query: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "method": "GET",
        "timeStamp": int(time.time() * 1000),
        "User-Agent": base64.b64encode(USER_AGENT.encode()).decode(),
        "index": random.randint(1, 1000),
        "channelId": 40009,
        "sVersion": 2,
        "key": WEB_QUERY_KEY,
    }
    canonical = "&".join(f"{key}={value}" for key, value in fields.items())
    signature = hashlib.md5(canonical.encode(), usedforsecurity=False).hexdigest()
    fields.pop("method")
    fields.pop("key")
    return {**query, **fields, "signKey": signature}


async def _board_payload(
    client: Any, path: str, board: str, query: dict[str, Any] | None = None
) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT, "Referer": BASE_URL + "/dashboard/web-heat"}
    response = await _get_response(client, path, board, query, headers)
    if response.status_code != 200:
        raise BoardRequestError(f"{board}返回 HTTP {response.status_code}，猫眼接口拒绝或未能完成请求")
    try:
        payload = response.json()
    except ValueError:
        raise BoardRequestError(f"{board}返回非 JSON 内容，可能是错误页或验证页") from None
    if not isinstance(payload, dict):
        raise BoardRequestError(f"{board}响应格式异常")
    if payload.get("status") is False or payload.get("success") is False:
        raise BoardRequestError(f"{board}未返回有效榜单，请稍后重试")
    expected = "movieList" if path.endswith("/movie") else "data" if path.endswith("webMaoYanHotData") else "dataList"
    data = payload.get(expected)
    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
        raise BoardRequestError(f"{board}响应缺少榜单数据，请稍后重试")
    return payload


async def _get_response(client, path, board, query, headers):
    for attempt in range(2):
        try:
            response = await client.get(
                BASE_URL + path,
                params=signed_query(query) if query is not None else None,
                headers=headers,
            )
        except httpx.HTTPError as error:
            if attempt == 1:
                raise BoardRequestError(f"{board}请求失败（{type(error).__name__}），请稍后重试") from None
        else:
            if response.status_code not in {403, 429, 502, 503, 504} or attempt == 1:
                return response
        await asyncio.sleep(attempt + 1)
    raise AssertionError("unreachable")


class BoardClient:
    """Keep successful boards when one upstream board remains unavailable."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.errors: list[str] = []
        self.succeeded = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        # The outer http_client context owns and closes the HTTP transport.
        cookies = getattr(self.client, "cookies", None)
        if cookies is not None:
            cookies.clear()

    def transport_for(self, path):
        return self.client


async def board_payload(client, path, board, query=None):
    if not isinstance(client, BoardClient):
        return await _board_payload(client, path, board, query)
    try:
        payload = await _board_payload(client.transport_for(path), path, board, query)
    except BoardRequestError as error:
        client.errors.append(str(error))
        return {}
    client.succeeded += 1
    return payload
