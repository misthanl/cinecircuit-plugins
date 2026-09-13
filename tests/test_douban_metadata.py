import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from cinecircuit_plugins.douban_rank.metadata import merge_detail
from cinecircuit_plugins.douban_rank.plugin import DoubanWatchlistPlugin


def card(**fields):
    return dict(source_key="douban", source_id="42", media_type="tv", **fields)


def context(detail=None, processed=False):
    return SimpleNamespace(
        media=SimpleNamespace(detail=AsyncMock(return_value=detail)),
        items=SimpleNamespace(processed=Mock(return_value=processed)),
        subscriptions=SimpleNamespace(
            create_checked=AsyncMock(return_value={"status": "subscribed"})
        ),
    )


def test_new_subscription_gets_details_once_before_create():
    ctx = context(card(overview="简介", poster="url", episodes_count=24))
    asyncio.run(DoubanWatchlistPlugin._create_candidate(ctx, "key", card()))
    payload = ctx.subscriptions.create_checked.call_args.args[1]
    assert (payload["overview"], payload["poster"], payload["total_episode"]) == ("简介", "url", 24)
    assert payload["subscription_origin"] == "豆瓣榜单"
    ctx.media.detail.assert_awaited_once()
    requested = ctx.media.detail.call_args.args[1]
    assert requested["include_extensions"] is False
    assert requested["include_library"] is False


def test_processed_subscription_is_not_enriched_or_written():
    ctx = context(processed=True)
    assert asyncio.run(DoubanWatchlistPlugin._create_candidate(ctx, "key", card())) == {
        "status": "skipped"
    }
    ctx.media.detail.assert_not_awaited()
    ctx.subscriptions.create_checked.assert_not_awaited()


def test_failed_details_still_create_original_subscription():
    ctx = context()
    ctx.media.detail.side_effect = RuntimeError("offline")
    asyncio.run(DoubanWatchlistPlugin._create_candidate(ctx, "key", card()))
    assert "total_episode" not in ctx.subscriptions.create_checked.call_args.args[1]


def test_rating_details_are_reused_even_when_source_has_no_episode_count():
    ctx = context()
    asyncio.run(DoubanWatchlistPlugin._create_candidate(ctx, "key", card(_detail_checked=True)))
    ctx.media.detail.assert_not_awaited()
    assert "_detail_checked" not in ctx.subscriptions.create_checked.call_args.args[1]


@pytest.mark.parametrize(
    "detail",
    [
        None,
        {"source_key": "tmdb", "source_id": "42", "media_type": "tv"},
        card() | {"source_id": "43"},
    ],
)
def test_wrong_identity_is_not_merged(detail):
    assert merge_detail(card(), detail) == card()


def test_known_metadata_and_progress_are_preserved():
    item = card(overview="known", poster="known.jpg", total_episode=1, completed_episode=1)
    assert merge_detail(item, card(overview="new", poster="new.jpg", episodes_count=24)) == item


def test_second_season_never_uses_first_season_count():
    item = card(season="S02")
    assert "total_episode" not in merge_detail(item, card(episodes_count=24))
    detail = card(seasons=[{"season_number": 2, "episode_count": 8}])
    assert merge_detail(item, detail)["total_episode"] == 8


@pytest.mark.parametrize("status", ["unknown", "in_library", "already_subscribed", "duplicate"])
def test_preflight_outcomes_are_returned_and_retried_without_history_writes(status):
    ctx = context()
    ctx.items.record = Mock()
    ctx.subscriptions.create_checked.return_value = {"status": status}
    item = card(overview="intro", poster="url", total_episode=24, season="S02")
    for _ in range(2):
        assert (
            asyncio.run(DoubanWatchlistPlugin._create_candidate(ctx, "key", item))["status"]
            == status
        )
    assert ctx.subscriptions.create_checked.await_count == 2
    assert ctx.subscriptions.create_checked.call_args.args[1]["season"] == "S02"
    ctx.items.record.assert_not_called()


def test_no_unchecked_fallback_on_older_host():
    ctx = context()
    ctx.subscriptions = SimpleNamespace(create=AsyncMock(), create_unprocessed=AsyncMock())
    with pytest.raises(RuntimeError, match="先更新主程序"):
        asyncio.run(DoubanWatchlistPlugin._create_candidate(ctx, "key", card()))
    ctx.subscriptions.create.assert_not_awaited()
    ctx.subscriptions.create_unprocessed.assert_not_awaited()


def test_preflight_permission_declared_without_version_change():
    from app.modules.plugins.permissions import PluginPermission

    assert PluginPermission.MEDIA_SERVER_READ in DoubanWatchlistPlugin.manifest.permissions
    assert DoubanWatchlistPlugin.manifest.version == "1.0.0"


@pytest.mark.parametrize(
    "poster",
    [
        "https://img3.doubanio.com/view/photo/m_ratio_poster/public/p2933112343.jpg",
        "//img1.doubanio.com/view/photo/public/example.jpg",
    ],
)
def test_direct_douban_poster_is_replaced_by_sdk_display_url_even_with_complete_metadata(poster):
    display = "/explore/image-proxy?source_key=douban&url=fixture"
    item = card(overview="existing overview", poster=poster, total_episode=24)
    ctx = context(card(overview="different overview", poster=display, original_poster=poster))
    asyncio.run(DoubanWatchlistPlugin._create_candidate(ctx, "key", item))
    ctx.media.detail.assert_awaited_once()
    payload = ctx.subscriptions.create_checked.call_args.args[1]
    assert payload["poster"] == display
    assert payload["original_poster"] == poster
    assert payload["overview"] == "existing overview"
    assert payload["total_episode"] == 24
    assert item["poster"] == poster


def test_rating_detail_also_normalizes_direct_poster_without_second_detail_fetch():
    poster = "https://img3.doubanio.com/view/photo/public/example.jpg"
    display = "/explore/image-proxy?source_key=douban&url=fixture"
    item = merge_detail(card(poster=poster), card(poster=display, original_poster=poster))
    ctx = context()
    asyncio.run(
        DoubanWatchlistPlugin._create_candidate(ctx, "key", {**item, "_detail_checked": True})
    )
    ctx.media.detail.assert_not_awaited()
    assert ctx.subscriptions.create_checked.call_args.args[1]["poster"] == display


@pytest.mark.parametrize(
    "poster",
    [
        "/explore/image-proxy?source_key=douban&url=fixture",
        "https://image.tmdb.org/t/p/w500/example.jpg",
        "https://doubanio.com.example.org/example.jpg",
    ],
)
def test_usable_existing_poster_does_not_trigger_extra_details(poster):
    item = card(overview="existing overview", poster=poster, total_episode=24)
    ctx = context()
    asyncio.run(DoubanWatchlistPlugin._create_candidate(ctx, "key", item))
    ctx.media.detail.assert_not_awaited()
    assert ctx.subscriptions.create_checked.call_args.args[1]["poster"] == poster


def test_details_prefetch_two_at_a_time_and_creates_remain_ordered():
    async def run():
        ctx = context()
        active = 0
        peak = 0
        entered = 0
        first_pair = asyncio.Event()
        saved = []

        async def detail(source, item):
            nonlocal active, peak, entered
            active += 1
            entered += 1
            peak = max(peak, active)
            if entered == 2:
                first_pair.set()
            if entered <= 2:
                await first_pair.wait()
            await asyncio.sleep(0)
            active -= 1
            return {**item, "overview": "intro", "poster": "url", "episodes_count": 8}

        async def create(key, item):
            saved.append(key)
            await asyncio.sleep(0)
            return {"status": "subscribed"}

        ctx.media.detail.side_effect = detail
        ctx.subscriptions.create_checked.side_effect = create
        items = {str(i): {**card(), "source_id": str(i)} for i in range(5)}
        result = await DoubanWatchlistPlugin._apply_candidates(ctx, items)
        assert peak == 2
        assert ctx.media.detail.await_count == 5
        assert saved == list(items)
        assert len(result) == 5

    asyncio.run(run())


def test_next_detail_can_finish_while_previous_subscription_is_created():
    async def run():
        ctx = context()
        creating = asyncio.Event()
        prepared = asyncio.Event()

        async def detail(source, item):
            if item["source_id"] == "2":
                await creating.wait()
                prepared.set()
            return {**item, "overview": "intro", "poster": "url", "episodes_count": 8}

        async def create(key, item):
            if key == "1":
                creating.set()
                await asyncio.wait_for(prepared.wait(), 1)
            return {"status": "subscribed"}

        ctx.media.detail.side_effect = detail
        ctx.subscriptions.create_checked.side_effect = create
        items = {key: {**card(), "source_id": key} for key in ("1", "2")}
        await DoubanWatchlistPlugin._apply_candidates(ctx, items)

    asyncio.run(run())


def test_cancelled_prefetch_does_not_create_subscriptions():
    async def run():
        ctx = context()
        started = asyncio.Event()
        active = 0

        async def detail(*args):
            nonlocal active
            active += 1
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                active -= 1

        ctx.media.detail.side_effect = detail
        task = asyncio.create_task(
            DoubanWatchlistPlugin._apply_candidates(ctx, {"1": card(), "2": card()})
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert active == 0
        ctx.subscriptions.create_checked.assert_not_awaited()

    asyncio.run(run())


def test_movie_preserves_detail_lookup_for_missing_overview():
    from cinecircuit_plugins.douban_rank.metadata import needs_metadata

    item = {
        "source_key": "douban",
        "source_id": "42",
        "media_type": "movie",
        "title": "Movie",
        "year": "2026",
        "poster": "/explore/image-proxy?image=known",
    }
    assert needs_metadata(item)
    assert not needs_metadata({**item, "overview": "Movie synopsis"})
    assert needs_metadata({**item, "media_type": "tv"})
    assert needs_metadata({**item, "poster": ""})
