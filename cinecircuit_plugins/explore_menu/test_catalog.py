"""Transport contracts from the public channel websites' response shapes."""

import asyncio
import json

import httpx
import pytest

from . import catalog


@pytest.mark.parametrize("source,kind", [(s, t) for s in ("tencent", "youku", "iqiyi", "mango")
                                        for t in ("movie", "tv", "anime", "kids", "variety", "documentary")])
def test_official_catalog_filters_and_page_tokens_reach_provider(source, kind):
    calls = []

    def handle(request):
        calls.append(request)
        if source == "tencent":
            body = json.loads(request.content)
            assert body["page_params"]["channel_id"] == dict(movie="100173", tv="100113", anime="100119", kids="100150", variety="100109", documentary="100105")[kind]
            assert "sort=83" in body["page_params"]["filter_params"]
            assert body["page_context"] == {"offset": "12"}
            assert request.headers["referer"] == "https://v.qq.com/"
            data = {"data": {"modules": {"normal": {"cards": [
                {"type": "searchlist_poster_card", "params": {"cid": "qq-id", "title": "Original", "year": "2025", "new_pic_vt": "https://cover.example/poster.jpg"}}
            ]}}, "has_next_page": True, "page_context": {"offset": "24"}}}
        elif source == "youku":
            assert json.loads(request.url.params["params"])["type"] == dict(movie="电影", tv="电视剧", anime="动漫", kids="少儿", variety="综艺", documentary="纪录片")[kind]
            assert request.url.path == "/category/data"
            assert json.loads(request.url.params["params"])["sort"] == "1"
            assert request.url.params["pageNo"] == "2"
            assert json.loads(request.url.params["session"]) == {"offset": "12"}
            data = {"success": True, "data": {"filterData": {"listData": [
                {"title": "Original", "img": "//cover.example/yk.jpg", "videoLink": "//v.youku.com/v_nextstage/id_yk123.html"}
            ], "session": {"offset": "24"}, "hasMore": True}}}
        elif source == "iqiyi":
            assert request.url.params["channel_id"] == str(dict(movie=1, tv=2, anime=4, kids=15, variety=6, documentary=3)[kind])
            if "categoryinfo" in request.url.path:
                return httpx.Response(200, json={"data": [{"id": 18001, "name": "类型", "child": [{"id": 8, "name": "喜剧"}]}]})
            assert request.url.params["three_category_id"] == "8;must"
            assert request.url.params["mode"] == "4"
            assert request.url.params["page_id"] == "2"
            assert request.url.params["market_release_date_level"] == "2025"
            data = {"code": "A00000", "data": {"list": [{"albumId": 123, "name": "Original", "period": "2025-06-01", "imageUrl": "https://cover.example/iq.jpg"}], "has_next": 1, "session": "next"}}
        else:
            assert request.url.params["channelId"] == str(dict(movie=3, tv=2, anime=50, kids=10, variety=1, documentary=51)[kind])
            if "/config/" in request.url.path:
                return httpx.Response(200, json={"data": {"listItems": [{"eName": "chargeInfo", "typeName": "资费", "items": [{"tagName": "会员", "tagId": "b1"}]}]}})
            assert request.url.params["pn"] == "2"
            assert request.url.params["chargeInfo"] == "b1"
            assert request.url.params["sort"] == "c1"
            data = {"code": 200, "data": {"hitDocs": [{"clipId": "mg1", "title": "Original", "year": "2025", "img": "https://cover.example/mg.jpg"}], "hasMore": True}}
        return httpx.Response(200, json=data)

    async def fetch():
        filters = {"tencent": {"sort": "83"}, "youku": {"sort": "1"},
                   "iqiyi": {"category_18001": "8", "sort": "4", "year": "2025"},
                   "mango": {"chargeInfo": "b1", "sort": "c1"}}[source]
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await getattr(catalog, source)(client, kind, 2, filters, {"offset": "12"})

    result = asyncio.run(fetch())
    assert result["has_more"] is True
    assert result["items"][0]["title"] == "Original"
    assert result["items"][0]["platform_id"]
    assert all("hotList" not in str(request.url) for request in calls)


@pytest.mark.parametrize("source", ["tencent", "youku"])
def test_cursor_platforms_do_not_fake_second_page_when_session_expired(source):
    async def fetch():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail("must not fetch"))) as client:
            await getattr(catalog, source)(client, "movie", 2, {}, None)
    with pytest.raises(ValueError, match="第一页"):
        asyncio.run(fetch())


def test_children_age_change_discards_stale_dependent_themes():
    def handle(request):
        from urllib.parse import parse_qs
        values = parse_qs(json.loads(request.content)["page_params"]["filter_params"])
        assert values == {"iyear": ["2"], "two": ["9"], "sort": ["75"]}
        return httpx.Response(200, json={"data": {"modules": {}}})

    async def fetch():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            await catalog.tencent(client, "kids", 1, {"iyear": "2", "all": "1", "one": "3", "two": "9", "sort": "75"})

    asyncio.run(fetch())
