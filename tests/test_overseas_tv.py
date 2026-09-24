import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cinecircuit_plugins.overseas_tv.config import normalized, PLATFORMS
from cinecircuit_plugins.overseas_tv.discovery import candidates, query_filters, discover
from cinecircuit_plugins.overseas_tv.plugin import OverseasTVPlugin

TODAY = date(2026, 9, 24)


def detail(**overrides):
    return {
        "tmdb_id": "42",
        "title": "Example",
        "year": "2015",
        "rating": 8,
        "vote_count": 100,
        "seasons": [
            {"season_number": 1, "air_date": "2015-01-01", "episode_count": 10},
            {"season_number": 2, "air_date": "2026-09-24", "episode_count": 8},
        ],
        **overrides,
    }


def test_old_series_new_season_is_selected_without_resubscribing_old_season():
    rows, _ = candidates(detail(), normalized({}), TODAY, "Netflix")
    assert [row["season"] for row in rows] == ["S02"]
    assert rows[0]["total_episode"] == 8
    filters = query_filters(normalized({}), "213", TODAY)
    assert filters["air_date.gte"] == "2026-08-25"
    assert "first_air_date.gte" not in filters
    assert filters["vote_count.gte"] == 0


@pytest.mark.parametrize(
    "config,changes,expected",
    [
        ({"modes": ["new"]}, {}, 0),
        ({"modes": ["popular"]}, {}, 1),
        ({"exclude_ids": "42,99"}, {}, 1),
        ({}, {"rating": 1}, 0),
        ({}, {"vote_count": 0, "rating": 0}, 1),
        ({"allow_unrated": False}, {"vote_count": 0}, 0),
        ({}, {"seasons": [{"season_number": 0, "air_date": "2026-09-24"}]}, 0),
        ({}, {"seasons": [{"season_number": 2, "air_date": "invalid"}]}, 0),
        ({}, {"seasons": [{"season_number": 2, "air_date": "2027-01-01"}]}, 0),
    ],
)
def test_selection_filters(config, changes, expected):
    assert len(candidates(detail(**changes), normalized(config), TODAY, "HBO")[0]) == expected


@pytest.mark.parametrize(
    "config",
    [
        {"max_new": "999999"},
        {"modes": []},
        {"netflix_enabled": "false"},
        {f"{key}_enabled": False for key, _, _ in PLATFORMS},
    ],
)
def test_invalid_settings_fail_closed(config):
    with pytest.raises(ValueError):
        normalized(config)


def context():
    state = {}
    return SimpleNamespace(
        config={},
        state=SimpleNamespace(get=state.get, set=state.__setitem__),
        items=SimpleNamespace(clear_once=Mock()),
        logger=Mock(),
        media=SimpleNamespace(
            supports_catalog_filters=True,
            detail=AsyncMock(return_value=detail()),
            discover=AsyncMock(),
        ),
        subscriptions=SimpleNamespace(
            create_checked=AsyncMock(return_value={"status": "subscribed"}),
            preflight=AsyncMock(return_value={"status": "missing"}),
        ),
    )


def test_removed_preview_is_ignored_and_limit_does_not_mark_processed():
    ctx = context()
    plugin = OverseasTVPlugin()
    media = candidates(detail(), normalized({}), TODAY, "HBO")[0][0]
    result = asyncio.run(plugin._admit(ctx, normalized({"preview": True}), media, "42:S02", 0))
    assert result["status"] == "subscribed"
    ctx.subscriptions.create_checked.reset_mock()
    result = asyncio.run(plugin._admit(ctx, normalized({}), media, "42:S02", 10))
    assert result["status"] == "skipped"
    ctx.subscriptions.create_checked.assert_not_awaited()


def test_catalog_pagination_is_bounded_and_multi_platform_identity_is_deduplicated():
    ctx = context()
    ctx.media.discover.return_value = {
        "items": [{"source_id": str(i)} for i in range(20)],
        "has_more": True,
    }

    async def run():
        return [item async for item in discover(ctx, normalized({}), TODAY)]

    assert len(asyncio.run(run())) == 10
    assert ctx.media.discover.await_count == 6


def test_missing_metadata_configuration_is_not_success():
    ctx = context()
    ctx.media.discover.return_value = {"source_status": {"mode": "missing_config"}}
    with pytest.raises(RuntimeError):
        asyncio.run(OverseasTVPlugin().run(ctx))
    assert ctx.state.get("latest_run_statistics")["status"] == "failed"


def test_old_host_is_rejected_before_unfiltered_search():
    ctx = context()
    ctx.media.supports_catalog_filters = False
    with pytest.raises(RuntimeError):
        asyncio.run(OverseasTVPlugin().run(ctx))
    ctx.media.discover.assert_not_awaited()


def test_cancellation_propagates_and_marks_failed():
    ctx = context()
    ctx.media.discover.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(OverseasTVPlugin().run(ctx))
    assert ctx.state.get("latest_run_statistics")["status"] == "failed"


def test_full_run_merges_platform_duplicates_and_keeps_distinct_seasons(monkeypatch):
    import cinecircuit_plugins.overseas_tv.plugin as module

    ctx = context()
    monkeypatch.setattr(
        module, "datetime", SimpleNamespace(now=lambda zone: SimpleNamespace(date=lambda: TODAY))
    )
    ctx.media.discover.return_value = {
        "items": [{"source_id": "42", "title": "Example"}],
        "has_more": False,
    }
    result = asyncio.run(OverseasTVPlugin().run(ctx))
    assert result["updated_count"] == 1
    call = ctx.subscriptions.create_checked.call_args
    assert call.args[0] == "tmdb:tv:42:S02"
    assert call.args[1]["season"] == "S02"
    assert ctx.state.get("latest_run_statistics")["subscribed"] == 1


def test_one_platform_failure_does_not_prevent_others():
    ctx = context()
    ctx.media.discover.side_effect = [
        RuntimeError("offline"),
        {"items": [{"source_id": "42"}]},
        {"items": []},
    ]
    errors = []

    async def run():
        return [item async for item in discover(ctx, normalized({}), TODAY, errors)]

    assert len(asyncio.run(run())) == 1
    assert errors[0]["status"] == "unknown"
    assert ctx.media.discover.await_count == 6


def test_types_migrate_and_removed_settings_cannot_affect_execution():
    config = normalized({"animation": True, "preview": True, "exclude_ids": "42"})
    assert config["include_types"] == ["animation"]
    assert "preview" not in config and "exclude_ids" not in config
    assert query_filters(config, "2552", TODAY)["without_genres"] == "99,10764,10767"
    config = normalized({"animation": True, "include_types": []})
    assert config["include_types"] == []
    assert all(config[f"{key}_num"] == "10" for key, _, _ in PLATFORMS)


def test_full_subscription_response_is_not_retained_in_actions():
    ctx = context()
    ctx.subscriptions.create_checked.return_value = {
        "status": "subscribed",
        "reason": "created",
        "media": {"huge": "x" * 1000000},
        "subscription": {"payload": "x" * 1000000},
    }
    result = asyncio.run(OverseasTVPlugin()._admit(ctx, normalized({}), {}, "42:S02", 0))
    assert result == {"status": "subscribed", "reason": "created"}


def test_repeated_runs_do_not_retain_discovery_or_detail_payloads(monkeypatch):
    import weakref
    import cinecircuit_plugins.overseas_tv.plugin as module

    class Payload(dict):
        pass

    references = []

    async def lookup(*args, **kwargs):
        payload = Payload(detail())
        payload["temporary"] = bytearray(1024 * 1024)
        references.append(weakref.ref(payload))
        return payload

    async def search(*args, **kwargs):
        payload = Payload(items=[{"source_id": "42"}], has_more=False)
        references.append(weakref.ref(payload))
        return payload

    ctx = context()
    ctx.media.detail = lookup
    ctx.media.discover = search
    monkeypatch.setattr(
        module, "datetime", SimpleNamespace(now=lambda zone: SimpleNamespace(date=lambda: TODAY))
    )

    async def repeat():
        plugin = OverseasTVPlugin()
        for _ in range(30):
            await plugin.run(ctx)
            assert all(ref() is None for ref in references)
            assert len(ctx.state.get("latest_run_statistics")["items"]) == 1

    asyncio.run(repeat())
