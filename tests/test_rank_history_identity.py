import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from cinecircuit_plugins.maoyan_rank.plugin import MaoyanWatchlistPlugin
from cinecircuit_plugins.douban_rank.plugin import DoubanWatchlistPlugin


@pytest.mark.parametrize("legacy", [{"status": "subscribed"}, {
    "status": "subscribed", "payload": {
        "title": "Film", "media_type": "movie", "source_key": "tmdb", "source_id": "old", "year": "1999"
    },
}])
def test_maoyan_legacy_title_receipt_does_not_hide_new_identity(legacy):
    row = {"title": "Film", "media_type": "movie", "maoyan_id": "new", "year": "2026"}
    context = SimpleNamespace(
        items=SimpleNamespace(get=Mock(side_effect=lambda key: legacy if key == "maoyan:movie:Film" else None)),
        media=SimpleNamespace(search=AsyncMock(return_value={"items": [{
            "title": "Film", "media_type": "movie", "source_key": "tmdb", "source_id": "new", "year": "2026"
        }]})),
        subscriptions=SimpleNamespace(create_checked=AsyncMock(return_value={"status": "subscribed"})),
        logger=Mock(),
    )
    result = asyncio.run(MaoyanWatchlistPlugin()._subscribe_candidates(context, [row]))
    assert result[0]["status"] == "subscribed"
    assert context.subscriptions.create_checked.call_args.args[0] != "maoyan:movie:Film"


def test_maoyan_batch_retains_distinct_ids_and_years():
    rows = [
        {"title": "Film", "maoyan_id": "1", "year": "1999"},
        {"title": "Film", "maoyan_id": "2", "year": "2026"},
        {"title": "Film", "maoyan_id": "2", "year": "2026"},
    ]
    assert len(MaoyanWatchlistPlugin._dedupe(rows, "movie")) == 2


def test_douban_skips_ignored_before_checked_creation():
    context = SimpleNamespace(
        items=SimpleNamespace(processed=Mock(return_value=True)),
        subscriptions=SimpleNamespace(create_checked=AsyncMock(return_value={"status": "skipped"}), create=AsyncMock()),
    )
    result = asyncio.run(DoubanWatchlistPlugin._apply_candidates(context, {"ignored": {"title": "Film"}}))
    assert result[0]["status"] == "skipped"
    context.subscriptions.create_checked.assert_not_awaited()
    context.subscriptions.create.assert_not_called()


def test_maoyan_canonical_keys_separate_id_and_explicit_season():
    from cinecircuit_plugins.maoyan_rank.history_identity import item_key, processed

    first = {"media_type": "tv", "source_key": "tmdb", "source_id": "1", "season": "S01"}
    second = {**first, "season": "S02"}
    remake = {**first, "source_id": "2"}
    assert len({item_key(first), item_key(second), item_key(remake)}) == 3
    items = SimpleNamespace(get=lambda key: {"status": "subscribed"} if key == item_key(first) else None)
    assert processed(items, first, "Title")
    assert not processed(items, second, "Title")
    assert not processed(items, remake, "Title")


def test_douban_old_sdk_preserves_ignored_without_creation():
    context = SimpleNamespace(
        items=SimpleNamespace(processed=Mock(return_value=True)),
        subscriptions=SimpleNamespace(create=AsyncMock()),
    )
    result = asyncio.run(DoubanWatchlistPlugin._apply_candidates(context, {"ignored": {"title": "Film"}}))
    assert result[0]["status"] == "skipped"
    context.subscriptions.create.assert_not_called()
