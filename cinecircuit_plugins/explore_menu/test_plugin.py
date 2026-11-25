import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.plugins.contracts import PluginApiRequest, PluginManifest
from .plugin import ExploreMenuPlugin, canonical


class State(dict):
    def set(self, key, value):
        self[key] = value


def context(**config):
    async def search(title, **kwargs):
        return {
            "items": [
                {
                    "title": title,
                    "media_type": "movie",
                    "source_key": "tmdb",
                    "source_id": "123",
                    "poster": "poster",
                }
            ]
        }

    return SimpleNamespace(
        config=config, state=State(), media=SimpleNamespace(search=AsyncMock(side_effect=search), assist_identity=AsyncMock(return_value=None))
    )


@pytest.mark.parametrize("source", ["iqiyi", "mango"])
def test_channel_configuration_is_shared_by_pages_and_filters_but_not_channels(monkeypatch, source):
    from . import catalog
    from . import plugin as implementation
    clock = [100.0]
    monkeypatch.setattr(implementation.time, "time", lambda: clock[0])
    loader = AsyncMock(return_value={"data": []})
    monkeypatch.setattr(catalog, source + "_config", loader)
    ctx = context()
    plugin = ExploreMenuPlugin()

    async def run():
        assert await plugin._channel_options(ctx, None, source, "tv") == {"config": {"data": []}}
        await plugin._channel_options(ctx, None, source, "tv")
        assert loader.await_count == 1
        await plugin._channel_options(ctx, None, source, "kids")
        assert loader.await_count == 2
        clock[0] += 3601
        await plugin._channel_options(ctx, None, source, "tv")
        assert loader.await_count == 3

    asyncio.run(run())


def request(source="tencent", **payload):
    return PluginApiRequest(
        action="explore",
        method="POST",
        payload={"source": source, "media_type": "movie", **payload},
    )


def test_standard_schema_has_four_independent_switches_and_no_custom_frontend():
    manifest = PluginManifest.from_dict(ExploreMenuPlugin.manifest.to_dict())
    assert manifest.name == "探索菜单扩展"
    assert len(manifest.configuration_fields()) == 8
    assert len(manifest.explore_sources) == 4
    assert not manifest.frontend_module and not manifest.navigation
    switches = [field for field in manifest.configuration_fields() if field.input_type == "switch"]
    assert [field.label for field in switches] == ["腾讯视频", "优酷", "爱奇艺", "芒果 TV"]
    assert "configuration_only" in manifest.capabilities


def test_children_channel_follows_animation_for_every_platform():
    manifest = PluginManifest.from_dict(ExploreMenuPlugin.manifest.to_dict())
    for source in manifest.explore_sources:
        assert source["catalog_types"] == [
            {"value": "movie", "label": "电影"}, {"value": "tv", "label": "电视剧"},
            {"value": "anime", "label": "动漫"}, {"value": "kids", "label": "少儿"},
            {"value": "variety", "label": "综艺"}, {"value": "documentary", "label": "纪录片"},
        ]


@pytest.mark.parametrize("source", ["tencent", "youku", "iqiyi", "mango"])
def test_hidden_source_never_makes_requests(source, monkeypatch):
    read = AsyncMock()
    monkeypatch.setattr("cinecircuit_plugins.explore_menu.plugin.catalog." + source, read)
    with pytest.raises(ValueError):
        asyncio.run(
            ExploreMenuPlugin().handle_api(request(source), context(**{source + "_visible": False}))
        )
    read.assert_not_called()


def test_catalog_retains_platform_cards_and_scopes_cache_by_filter_and_page(monkeypatch):
    read = AsyncMock(return_value={"items": [{"title": "Example", "platform_id": "abc", "poster": "platform.jpg", "year": "2025"}],
                                  "filters": {"sort": {"options": [{"label": "最新", "value": "new"}]}},
                                  "has_more": True, "cursor": {"next": "cursor"}})
    monkeypatch.setattr("cinecircuit_plugins.explore_menu.plugin.catalog.tencent", read)
    plugin, ctx = ExploreMenuPlugin(), context()
    first = asyncio.run(plugin.handle_api(request(), ctx))
    again = asyncio.run(plugin.handle_api(request(), ctx))
    assert first == again
    assert first["items"][0]["source_key"] == "plugin:explore-menu:tencent"
    assert first["items"][0]["poster"] == "platform.jpg"
    assert first["items"][0]["identity_pending"] is True
    assert first["has_more"] is True
    read.assert_awaited_once()
    ctx.media.search.assert_not_called()
    asyncio.run(plugin.handle_api(request(page=2), ctx))
    assert read.call_args.args[-1] == {"next": "cursor"}
    asyncio.run(plugin.handle_api(request(filters={"sort": "new"}), ctx))
    assert read.await_count == 3
    assert read.call_args.args[-1] is None


def test_resolution_requires_unique_title_and_year_and_preserves_platform_presentation():
    ctx = context()
    ctx.media.search = AsyncMock(return_value={"items": [
        {"title": "Example", "year": year, "source_key": "tmdb", "source_id": year,
         "media_type": "movie", "poster": "tmdb.jpg"} for year in [1990, 2025]
    ]})
    item = {"source_key": "plugin:explore-menu:tencent", "title": "Example", "year": "2025", "poster": "platform.jpg"}
    result = asyncio.run(ExploreMenuPlugin().handle_api(request(operation="resolve", item=item), ctx))
    assert result["items"][0]["source_id"] == 2025
    assert result["items"][0]["poster"] == "platform.jpg"
    assert result["items"][0]["identity_pending"] is False
    item["year"] = "2024"
    result = asyncio.run(ExploreMenuPlugin().handle_api(request(operation="resolve", item=item), ctx))
    assert result["items"] == []
    assert result["source_status"]["mode"] == "unmatched"


def test_ambiguous_matches_are_not_turned_into_wrong_subscriptions():
    ctx = context()
    ctx.media.search = AsyncMock(
        return_value={
            "items": [
                {
                    "title": "Example",
                    "media_type": "movie",
                    "source_key": "tmdb",
                    "source_id": value,
                }
                for value in (1, 2)
            ]
        }
    )
    assert asyncio.run(canonical(ctx, {"title": "Example"}, "movie")) is None


def test_failure_returns_clear_status_without_fabricated_cards(monkeypatch):
    monkeypatch.setattr(
        "cinecircuit_plugins.explore_menu.plugin.catalog.tencent",
        AsyncMock(side_effect=ValueError("offline")),
    )
    result = asyncio.run(ExploreMenuPlugin().handle_api(request(), context()))
    assert result["source_status"]["mode"] == "error"
    assert result["items"] == []
