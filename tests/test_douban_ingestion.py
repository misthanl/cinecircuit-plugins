import asyncio
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from cinecircuit_plugins.douban_rank import boards, plugin, rss


def test_named_charts_are_distinct_and_ignore_sidebar_duplicates():
    page = b"""<div class="movie_top"><a onclick="mv_week" href="https://movie.douban.com/subject/1/">Weekly</a></div>
    <div class="movie_top"><a onclick="mv_us_week" href="https://movie.douban.com/subject/2/">US</a></div>
    <div class="movie_top"><a onclick="mv_week" href="https://movie.douban.com/subject/1/">Weekly</a></div>"""
    assert [row["source_id"] for row in boards.chart_rows(page, "movie-weekly")] == ["1"]
    assert [row["source_id"] for row in boards.chart_rows(page, "movie-ustop")] == ["2"]


class TopClient:
    def __init__(self, repeat=False):
        self.offsets = []
        self.repeat = repeat

    async def get(self, url, *, params):
        self.offsets.append(params["start"])
        start = 0 if self.repeat else params["start"]
        rows = [
            f'<li><div class="hd"><a href="https://movie.douban.com/subject/{i + 1}/"><span class="title">Film {i}</span></a></div><div class="bd"><p>2020</p><span class="rating_num">8.8</span></div></li>'
            for i in range(start, start + 25)
        ]
        return SimpleNamespace(
            content=("<ol class='grid_view'>" + "".join(rows) + "</ol>").encode(),
            raise_for_status=lambda: None,
        )


@pytest.mark.parametrize("limit, requests", [(10, 1), (250, 10)])
def test_top_board_honors_exact_limit_and_reads_every_page(limit, requests):
    client = TopClient()
    rows = asyncio.run(boards._top_movies(client, limit))
    assert len(rows) == len({row["source_id"] for row in rows}) == limit
    assert client.offsets == list(range(0, requests * 25, 25))
    assert rows[-1]["source_id"] == str(limit)


def test_top_board_rejects_repeated_or_captcha_pages():
    with pytest.raises(ValueError, match="分页不完整"):
        asyncio.run(boards._top_movies(TopClient(repeat=True), 250))
    with pytest.raises(ValueError, match="暂不可用"):
        boards.chart_rows(b"<html>Please login</html>", "movie-weekly")


def test_collections_and_proxy_use_the_selected_board(monkeypatch):
    calls = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            calls.append(url)
            kind = "tv" if "tv_hot" in url or "show_domestic" in url else "movie"
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {
                    "subject_collection_items": [
                        {"id": "123", "type": kind, "title": "Item", "rating": {"value": 8.6}}
                    ]
                },
            )

    def client(**kwargs):
        assert kwargs["use_application_proxy"] is True
        return Client()

    monkeypatch.setattr(boards, "http_client", client)
    for name, collection in boards.COLLECTIONS.items():
        kind = "movie" if name.startswith("movie-") else "tv"
        rows = asyncio.run(boards.read_board(name, kind, proxy=True))
        assert rows[0]["media_type"] == kind
        assert rows[0]["rating"] == 8.6
        assert f"/{collection}/items" in calls[-1]
    assert len(set(calls)) == 4


def search_media(rows):
    async def search(*args, **kwargs):
        return {"items": rows}

    return SimpleNamespace(search=search)


def test_rss_rejects_unrelated_title_and_ambiguous_identity():
    entry = ET.fromstring("<item><title>Requested (2024)</title></item>")
    wrong = {"id": "1", "title": "Unrelated", "media_type": "tv", "year": "1999"}
    assert asyncio.run(rss.resolve_entry(search_media([wrong]), entry)) is None
    match = {"id": "2", "title": "Requested", "media_type": "tv", "year": "2024"}
    assert (
        asyncio.run(rss.resolve_entry(search_media([match, {**match, "id": "3"}]), entry)) is None
    )
    result = asyncio.run(rss.resolve_entry(search_media([wrong, match]), entry))
    assert result["media_type"] == "tv" and result["year"] == "2024"


def test_rss_subject_link_uses_verified_id_and_keeps_resolved_type():
    entry = ET.fromstring(
        '<entry xmlns="http://www.w3.org/2005/Atom"><title>A title</title><link href="https://movie.douban.com/subject/42/"/></entry>'
    )

    async def resolve_identity(**kwargs):
        assert kwargs["source_id"] == "42"
        assert kwargs["media_type"] == "tv"
        return {"source_id": "42", "media_type": "tv", "title": "Resolved", "year": "2020"}

    media = search_media([
        {"id": "99", "media_type": "movie", "title": "A title"},
        {"id": "42", "media_type": "tv", "title": "Canonical title"},
    ])
    media.resolve_identity = resolve_identity
    result = asyncio.run(
        rss.resolve_entry(media, entry)
    )
    assert result["media_type"] == "tv" and result["year"] == "2020"


def test_rss_untyped_subject_never_defaults_to_movie_or_another_id():
    entry = ET.fromstring('<item><title>Series</title><link>https://movie.douban.com/subject/42/</link></item>')
    media = search_media([{"id": "99", "media_type": "movie", "title": "Series"}])
    assert asyncio.run(rss.resolve_entry(media, entry)) is None


@pytest.mark.parametrize("overrides", [{"year": "1999"}, {"media_type": "movie"}])
def test_rss_rejects_wrong_year_or_explicit_type(overrides):
    entry = ET.fromstring("<item><title>电视剧 Requested (2024)</title></item>")
    wrong = {"id": "1", "title": "Requested", "year": "2024", "media_type": "tv", **overrides}
    assert asyncio.run(rss.resolve_entry(search_media([wrong]), entry)) is None


def test_rss_minimum_is_applied_before_subscription(monkeypatch):
    async def candidates(self, context):
        return [{"item_key": "low", "rating": 2}, {"item_key": "high", "rating": 9.5}]

    received = []

    async def create(key, payload):
        received.append(payload)
        return {"status": "subscribed"}

    monkeypatch.setattr(plugin.DoubanWatchlistPlugin, "_rss_candidates", candidates)
    context = SimpleNamespace(
        config={"ranks": [], "vote": 9},
        items=SimpleNamespace(processed=lambda _: False),
        subscriptions=SimpleNamespace(create_checked=create),
    )
    result = asyncio.run(plugin.DoubanWatchlistPlugin()._run(context, []))
    assert result["updated_count"] == 1
    assert received[0]["item_key"] == "high"
    assert received[0]["subscription_origin"] == "豆瓣榜单"


def test_rss_client_forwards_proxy_selection(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            return SimpleNamespace(content=b"<rss><channel/></rss>", raise_for_status=lambda: None)

    def client(**kwargs):
        assert kwargs["use_application_proxy"] is True
        return Client()

    monkeypatch.setattr(rss, "http_client", client)
    assert asyncio.run(rss.read_rss(SimpleNamespace(config={"proxy": True}), ["/feed"])) == []
