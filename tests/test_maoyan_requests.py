import asyncio
import base64
import hashlib
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace

import httpx
import pytest

from cinecircuit_plugins.maoyan_rank import requests
from cinecircuit_plugins.maoyan_rank.plugin import MaoyanWatchlistPlugin


def test_signature_matches_web_protocol(monkeypatch):
    monkeypatch.setattr(requests.time, "time", lambda: 1700000000)
    monkeypatch.setattr(requests.random, "randint", lambda *args: 23)
    query = {"showDate": "20260923", "seriesType": "0"}
    actual = requests.signed_query(query)
    ua = base64.b64encode(requests.USER_AGENT.encode()).decode()
    text = f"method=GET&timeStamp=1700000000000&User-Agent={ua}&index=23&channelId=40009&sVersion=2&key={requests.WEB_QUERY_KEY}"
    assert actual["signKey"] == hashlib.md5(text.encode()).hexdigest()
    assert actual["User-Agent"] == ua
    assert "key" not in actual and "method" not in actual
    assert query == {"showDate": "20260923", "seriesType": "0"}


@pytest.mark.parametrize("status,body,message", [
    (403, "<html>blocked</html>", "HTTP 403"),
    (200, "<html>blocked</html>", "非 JSON"),
    (200, "[]", "响应格式"),
    (200, '{"status":false}', "未返回有效榜单"),
    (200, '{}', "缺少榜单数据"),
])
def test_error_names_board_without_leaking_response(status, body, message):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(status, text=body)
        )) as client:
            with pytest.raises(requests.BoardRequestError, match=message) as caught:
                await requests.board_payload(client, "/dashboard/webHeatData", "全网电视剧榜", {})
            assert "全网电视剧榜" in str(caught.value)
            assert body not in str(caught.value)
    asyncio.run(run())


def test_transport_error_does_not_expose_signed_url():
    client = SimpleNamespace(get=AsyncMock(side_effect=httpx.ConnectError("secret URL")))
    with pytest.raises(requests.BoardRequestError, match="ConnectError") as caught:
        asyncio.run(requests.board_payload(client, "/dashboard/webHeatData", "电视剧榜", {}))
    assert "secret URL" not in str(caught.value)
    assert client.get.await_count == 2


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(requests.asyncio, "sleep", AsyncMock())


def test_transient_failure_retries_with_fresh_signature(monkeypatch):
    monkeypatch.setattr(requests.random, "randint", Mock(side_effect=[1, 2]))
    seen = []
    async def run():
        def handler(request):
            seen.append(request.url.params["signKey"])
            return httpx.Response(403) if len(seen) == 1 else httpx.Response(200, json={"dataList": {"list": []}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await requests.board_payload(client, "/dashboard/webHeatData", "test", {})
    asyncio.run(run())
    assert len(seen) == 2 and seen[0] != seen[1]


def test_all_boards_failed_is_not_reported_as_success(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(403)
    monkeypatch.setattr(
        "cinecircuit_plugins.maoyan_rank.plugin.http_client",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    context = SimpleNamespace(config={"type": ["movie"]}, logger=Mock())
    with pytest.raises(requests.BoardRequestError, match="全部获取失败"):
        asyncio.run(MaoyanWatchlistPlugin().run(context))
    assert len(calls) == 2


def test_cancellation_is_never_retried_or_swallowed():
    client = SimpleNamespace(get=AsyncMock(side_effect=asyncio.CancelledError()))
    boards = requests.BoardClient(client)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(requests.board_payload(boards, "/dashboard/webHeatData", "test", {}))
    assert client.get.await_count == 1
