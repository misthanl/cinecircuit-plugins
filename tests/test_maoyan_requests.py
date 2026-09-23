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


def test_tv_request_uses_today_omits_empty_platform_and_signs(monkeypatch):
    monkeypatch.setattr("cinecircuit_plugins.maoyan_rank.plugin.request_board_date", lambda: "20260923")
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"status": True, "dataList": {"list": []}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await MaoyanWatchlistPlugin()._television_candidates(
                client, {"all_enabled": True, "tx_enabled": True}, ["web-heat"]
            )
        assert len(calls) == 2
        assert "platformType" not in calls[0].url.params
        assert calls[1].url.params["platformType"] == "3"
        for request in calls:
            assert request.url.params["showDate"] == "20260923"
            assert request.url.params["signKey"]
            assert request.headers["User-Agent"] == requests.USER_AGENT
    asyncio.run(run())


def test_web_movie_signed_and_empty_list_is_valid():
    async def run():
        def handler(request):
            assert request.url.path == "/dashboard/webMaoYanHotData"
            assert request.url.params["signKey"]
            assert request.url.params["networkHot"] == "3"
            return httpx.Response(200, json={"success": True, "data": {"list": []}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await MaoyanWatchlistPlugin()._web_movie_candidates(client, {}) == []
    asyncio.run(run())


def test_transport_error_does_not_expose_signed_url():
    client = SimpleNamespace(get=AsyncMock(side_effect=httpx.ConnectError("secret URL")))
    with pytest.raises(requests.BoardRequestError, match="ConnectError") as caught:
        asyncio.run(requests.board_payload(client, "/dashboard/webHeatData", "电视剧榜", {}))
    assert "secret URL" not in str(caught.value)


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


def test_failed_board_does_not_discard_successful_board():
    async def run():
        def handler(request):
            if request.url.path.endswith("/movie"):
                return httpx.Response(200, json={"movieList": {"list": [{"movieInfo": {"movieName": "Movie"}}]}})
            return httpx.Response(403)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
            client = requests.BoardClient(transport)
            rows = await MaoyanWatchlistPlugin()._movie_candidates(client, {}, ["movie", "web-movie"])
            assert len(rows) == 1 and rows[0]["title"] == "Movie"
            assert client.succeeded == 1
            assert len(client.errors) == 1 and "网络电影榜" in client.errors[0]
    asyncio.run(run())


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
    assert len(calls) == 4


def test_cancellation_is_never_retried_or_swallowed():
    client = SimpleNamespace(get=AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(requests.board_payload(requests.BoardClient(client), "/dashboard/webHeatData", "test", {}))
    assert client.get.await_count == 1
