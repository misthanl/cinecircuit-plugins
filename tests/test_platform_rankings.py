import asyncio
import hashlib
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from cinecircuit_plugins.maoyan_rank import platforms
from cinecircuit_plugins.maoyan_rank.requests import BoardClient, BoardRequestError
from cinecircuit_plugins.maoyan_rank.settings import normalized
from cinecircuit_plugins.maoyan_rank.identity import exact_candidates


@pytest.fixture(autouse=True)
def no_delay(monkeypatch):
    monkeypatch.setattr(platforms.asyncio, "sleep", AsyncMock())


def youku_payload():
    tabs = {}
    for label in [*platforms.CATEGORIES.values(), "热门搜索"]:
        items = [{"data": {"title": f"简称{i}", "keyword": f"{label}{i}",
                           "showId": str(i + 1), "rank": i + 1}} for i in range(15)]
        items.insert(1, {"data": {"title": "广告"}})
        tabs[label] = {"nodes": [{"nodes": items}]}
    return {"ret": ["SUCCESS::调用成功"], "data": {"nodes": [
        {"data": {"title": "推荐干扰项"}}, {"nodes": [{"data": {"tabDataMap": tabs}}]},
    ]}}


def test_youku_search_handshake_and_all_categories():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.path == "/h5/mtop.youku.soku.yksearch/2.0/"
        assert request.headers["User-Agent"].startswith("python-httpx/")
        if len(calls) == 1:
            return httpx.Response(200, json={"ret": ["FAIL_SYS_TOKEN_EMPTY::令牌为空"]},
                                  headers={"set-cookie": "_m_h5_tk=publicsession_123; Domain=.youku.com; Path=/"})
        params = request.url.params
        assert params["sign"] == hashlib.md5(f"publicsession&{params['t']}&23774304&{params['data']}".encode()).hexdigest()
        query = json.loads(params["data"])
        assert query["appScene"] == "default_page" and query["searchFrom"] == "home"
        return httpx.Response(200, json=youku_payload())
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
            client = BoardClient(transport)
            result = await platforms.collect(client, normalized({"yk_enabled": True, "platform_types": list(platforms.CATEGORIES)}))
            assert len(result) == 50 and client.succeeded == 5 and not client.errors
            for key, label in platforms.CATEGORIES.items():
                rows = [row for row in result if row["category"] == key]
                assert [row["title"] for row in rows] == [f"{label}{i}" for i in range(10)]
                assert all(row["board"] == f"优酷{label}热搜榜" for row in rows)
    asyncio.run(run())
    assert len(calls) == 2


@pytest.mark.parametrize("ret", [["FAIL_SYS::失败"], ["FAIL_SYS_TOKEN_EMPTY::令牌为空"]])
def test_youku_rejects_failed_response(ret):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"ret": ret}))) as client:
            with pytest.raises(BoardRequestError):
                await platforms.youku(client)
    asyncio.run(run())


def test_youku_missing_category_keeps_other_categories():
    payload = youku_payload()
    del payload["data"]["nodes"][1]["nodes"][0]["data"]["tabDataMap"]["电视剧"]
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as transport:
            client = BoardClient(transport)
            result = await platforms.collect(client, normalized({"yk_enabled": True, "platform_types": ["tv", "movie"], "yk_num": 3}))
            assert len(result) == 3 and result[0]["board"] == "优酷电影热搜榜"
            assert client.succeeded == 1 and len(client.errors) == 1
    asyncio.run(run())


def test_tencent_ignores_navigation_and_unrelated_rankings():
    text = '<a title="广告"></a><div class="mod_rank_figure"><h3 class="title">动漫</h3><ol class="hotlist">'
    text += ''.join(f'<li><a title="动画{n}"></a></li>' for n in range(20))
    text += '</ol></div><div class="mod_rank_figure"><h3 class="title">游戏</h3><ol class="hotlist"><li><a title="游戏"></a></li></ol></div>'
    assert platforms.parse_tencent(text) == {"动漫": [{"title": f"动画{n}"} for n in range(10)]}


def test_partial_failure_retries_once_and_preserves_other_platform():
    calls = []
    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "v.qq.com":
            return httpx.Response(403)
        return httpx.Response(200, json={"data": {"topList": [{"label": "电影", "data": [{"name": "影片"}]}]}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport, BoardClient(transport) as client:
            rows = await platforms.collect(client, normalized({"platform_types": ["movie"], "tx_enabled": True, "mg_enabled": True}))
            assert len(rows) == 1 and rows[0]["title"] == "影片"
            assert client.succeeded == 1 and len(client.errors) == 1
            assert "HTTP 403" in client.errors[0]
    asyncio.run(run())
    assert calls == ["v.qq.com", "v.qq.com", "mobileso.bz.mgtv.com"]


@pytest.mark.parametrize("cancel", [False, True])
def test_stream_closes_on_oversize_or_cancellation(cancel):
    class Stream(httpx.AsyncByteStream):
        closed = False
        async def __aiter__(self):
            if cancel:
                raise asyncio.CancelledError()
            yield b"x" * (platforms.MAX_RESPONSE_BYTES + 1)
        async def aclose(self):
            self.closed = True
    stream = Stream()
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))) as client:
            with pytest.raises(asyncio.CancelledError if cancel else BoardRequestError):
                await platforms.read_page(client, "https://example.test")
            assert stream.closed
    asyncio.run(run())


def test_iqiyi_uses_all_search_categories_in_one_request():
    seen = []
    def handler(request):
        seen.append(request)
        assert request.url.host == "mesh.if.iqiyi.com"
        assert request.url.path == "/portal/lw/search/keywords/hotList"
        groups = [{"title": label, "items": [
            {"title": f"{label}{i}", "qipuId": i} for i in range(20)
        ]} for label in platforms.CATEGORIES.values()]
        groups.append({"title": "热搜", "items": [{"title": "总榜干扰项"}]})
        return httpx.Response(200, json={"hotQuery": groups})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
            client = BoardClient(transport)
            rows = await platforms.collect(client, normalized({
                "iqy_enabled": True, "platform_types": list(platforms.CATEGORIES),
            }))
            assert client.succeeded == 5 and not client.errors
            assert len(rows) == 50
            for key, label in platforms.CATEGORIES.items():
                selected = [row for row in rows if row["category"] == key]
                assert [row["title"] for row in selected] == [f"{label}{i}" for i in range(10)]
                assert [row["platform_id"] for row in selected] == [str(i) for i in range(10)]
    asyncio.run(run())
    assert len(seen) == 1


def test_iqiyi_missing_category_does_not_fall_back_to_total_search():
    async def run():
        payload = {"hotQuery": [{"title": "热搜", "items": [{"title": "总榜"}]}]}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as transport:
            client = BoardClient(transport)
            assert await platforms.collect(client, normalized({"iqy_enabled": True, "platform_types": ["documentary"]})) == []
            assert client.succeeded == 0 and len(client.errors) == 1
    asyncio.run(run())


def test_documentary_and_anime_are_not_forced_to_television():
    items = [{"title": "作品", "source_key": "tmdb", "source_id": "1", "media_type": "movie"},
             {"title": "作品", "source_key": "tmdb", "source_id": "1", "media_type": "tv"}]
    assert len(exact_candidates(items, "作品", "mixed")) == 2
    assert exact_candidates(items[:1], "作品", "mixed")[0]["media_type"] == "movie"


def test_empty_payload_is_failure_not_success():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": {"items": []}}))) as transport:
            client = BoardClient(transport)
            assert await platforms.collect(client, normalized({"platform_types": ["movie"], "iqy_enabled": True})) == []
            assert client.succeeded == 0 and len(client.errors) == 1
    asyncio.run(run())
