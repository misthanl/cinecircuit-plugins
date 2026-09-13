import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from cinecircuit_plugins.brush_flow.subscription_matching import SubscriptionIndex, load_index


def test_titles_seasons_and_nonmatches():
    index = SubscriptionIndex([
        {"title": "问心", "original_title": "The Heart", "media_type": "tv", "season": "S02"},
        {"title": "Example Film", "media_type": "movie"},
    ])
    for title in ("问心 第二季 1080p", "The.Heart.S02E03.1080p.WEB-DL", "[Group] The_Heart_S02_1080p"):
        assert index.matches({"title": title})
    assert index.matches({"title": "Example.Film.2026.1080p"})
    for title in ("问心 S01", "问心", "问心2", "The Heart Other S02", "The Heart S01-S02", "Other Film 2026"):
        assert not index.matches({"title": title})


def test_disabled_has_no_read_and_multiple_tasks_share_one_read():
    catalog = SimpleNamespace(list_summaries=AsyncMock(return_value=[]))
    context = SimpleNamespace(sdk=SimpleNamespace(require=Mock(return_value=catalog)))
    assert asyncio.run(load_index(context, [{}])) is None
    context.sdk.require.assert_not_called()
    asyncio.run(load_index(context, [{"exclude_subscriptions": True}] * 5))
    catalog.list_summaries.assert_awaited_once()
