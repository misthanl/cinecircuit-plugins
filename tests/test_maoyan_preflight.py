import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from cinecircuit_plugins.maoyan_rank.plugin import MaoyanWatchlistPlugin


def context(status="unknown", previous=None):
    return SimpleNamespace(
        items=SimpleNamespace(get=Mock(return_value=previous), record=Mock()),
        subscriptions=SimpleNamespace(create_checked=AsyncMock(return_value={"status": status})),
        media=SimpleNamespace(search=AsyncMock(return_value={"items": [{
            "title": "作品", "media_type": "tv", "source_key": "tmdb", "source_id": "1",
        }]})), logger=Mock(),
    )


@pytest.mark.parametrize("status", ["unknown", "already_subscribed", "in_library", "duplicate"])
def test_temporary_results_and_legacy_ignored_history_are_retried(status):
    ctx = context(status, {"status": "ignored"})
    row = {"title": "作品 第二季", "media_type": "tv"}
    for _ in range(2):
        actions = asyncio.run(MaoyanWatchlistPlugin()._subscribe_candidates(ctx, [row]))
        assert actions[0]["status"] == status
    assert ctx.subscriptions.create_checked.await_count == 2
    assert ctx.subscriptions.create_checked.call_args.args[1]["season"] == "S02"
    assert ctx.subscriptions.create_checked.call_args.args[1]["subscription_origin"] == "猫眼榜单"
    ctx.items.record.assert_not_called()


def test_success_history_stays_processed():
    ctx = context()
    ctx.items.get.side_effect = lambda key: {
        "status": "subscribed",
        "payload": {"media_type": "tv", "source_key": "tmdb", "source_id": "1"},
    } if key == "maoyan:tv:作品" else None
    asyncio.run(MaoyanWatchlistPlugin()._subscribe_candidates(ctx, [{"title": "作品", "media_type": "tv"}]))
    ctx.media.search.assert_awaited_once()
    ctx.subscriptions.create_checked.assert_not_called()


def test_same_identity_checked_once_per_run():
    ctx = context()
    actions = asyncio.run(MaoyanWatchlistPlugin()._subscribe_candidates(ctx, [
        {"title": "作品", "media_type": "tv"}, {"title": "作 品", "media_type": "tv"},
    ]))
    ctx.subscriptions.create_checked.assert_awaited_once()
    assert actions[1]["reason"] == "same_run_duplicate"


def test_no_arbitrary_first_search_result_or_ambiguous_remake():
    plugin = MaoyanWatchlistPlugin()
    assert plugin._best_match([{"title": "其他作品", "media_type": "tv"}], "作品", "tv") is None
    assert plugin._best_match([
        {"title": "作品", "media_type": "tv", "source_id": "1"},
        {"title": "作品", "media_type": "tv", "source_id": "2"},
    ], "作品", "tv") is None


@pytest.mark.parametrize("title,expected", [("作品 第二季", 2), ("作品 S03", 3), ("作品 第十一季", 11), ("作品", None)])
def test_explicit_season(title, expected):
    assert MaoyanWatchlistPlugin._title_season(title) == expected


def test_missing_sdk_never_falls_back_to_unchecked_create():
    ctx = context()
    ctx.subscriptions = SimpleNamespace(create=AsyncMock())
    with pytest.raises(RuntimeError, match="先更新主程序"):
        asyncio.run(MaoyanWatchlistPlugin()._subscribe_candidates(ctx, []))
    ctx.subscriptions.create.assert_not_called()
