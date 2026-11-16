import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from .identity import canonical, resolve
from .plugin import ExploreMenuPlugin
from .test_plugin import request


def entry(**changes):
    return {"source_key": "tmdb", "source_id": "318349", "title": "宝珠", "year": "2026", "media_type": "tv", **changes}


def context(candidates, detail=None, assisted=None):
    return SimpleNamespace(config={}, media=SimpleNamespace(
        search=AsyncMock(return_value={"items": candidates}),
        detail=AsyncMock(return_value=detail or entry()),
        assist_identity=AsyncMock(return_value=assisted),
    ))


@pytest.mark.parametrize("source", ["tencent", "youku", "iqiyi", "mango"])
def test_missing_search_year_is_verified_in_detail_before_ai(source):
    ctx = context([entry(year="")])
    item = {"source_key": f"plugin:explore-menu:{source}", "title": "宝珠", "year": "2026", "poster": "platform.jpg"}
    result = asyncio.run(ExploreMenuPlugin().handle_api(request(source, operation="resolve", item=item, media_type="tv"), ctx))
    assert result["items"][0]["source_id"] == "318349"
    assert result["items"][0]["poster"] == "platform.jpg"
    assert result["items"][0]["resolution_method"] == "catalog_metadata_match"
    assert "year" not in ctx.media.detail.call_args.args[1]
    ctx.media.assist_identity.assert_not_awaited()


def test_real_year_conflict_is_not_accepted():
    ctx = context([entry(year="")], detail=entry(year="1990"))
    assert asyncio.run(canonical(ctx, entry(), "tv")) is None


def test_unique_verified_title_without_year_is_selected_with_warning():
    ctx = context([entry(year="")], detail=entry(year=""))
    result = asyncio.run(canonical(ctx, entry(), "tv"))
    assert result["source_id"] == "318349" and result["identity_warnings"]
    ctx.media.assist_identity.assert_not_awaited()


def test_missing_year_does_not_resolve_multiple_candidates():
    ctx = context([entry(year=""), entry(source_id="42", year="")], detail=entry(year=""))
    assert asyncio.run(canonical(ctx, entry(), "tv")) is None


def test_compact_detail_options_do_not_escape_into_viewer_requests():
    ctx = context([entry(year="")], detail=entry(include_library=False, include_extensions=False, include_seasons=False))
    item = {"source_key": "plugin:explore-menu:mango", "title": "宝珠", "year": "2026"}
    result = asyncio.run(ExploreMenuPlugin().handle_api(request("mango", operation="resolve", item=item, media_type="tv"), ctx))
    assert result["items"]
    assert not any(key.startswith(("include_", "_include_")) for key in result["items"][0])


def test_known_year_matching_does_not_require_detail_or_ai():
    ctx = context([entry()])
    assert asyncio.run(resolve(ctx, entry(), "tv"))["source_id"] == "318349"
    ctx.media.detail.assert_not_awaited()
    ctx.media.assist_identity.assert_not_awaited()


@pytest.mark.parametrize("category", ["anime", "kids", "documentary"])
@pytest.mark.parametrize("kind", ["movie", "tv"])
def test_mixed_catalogs_resolve_the_actual_metadata_type(category, kind):
    ctx = context([entry(media_type=kind)])
    result = asyncio.run(resolve(ctx, entry(), category))
    assert result["media_type"] == kind
    ctx.media.assist_identity.assert_not_awaited()


def test_same_numeric_id_in_movie_and_tv_remains_ambiguous():
    ctx = context([entry(media_type="movie"), entry(media_type="tv")])
    assert asyncio.run(resolve(ctx, entry(), "documentary")) is None


@pytest.mark.parametrize("source", ["tencent", "youku", "iqiyi", "mango"])
def test_four_platforms_use_assistance_only_after_regular_matching_fails(source):
    ctx = context([], assisted=entry(title="正式名称", resolution_method="ai_assisted_search"))
    item = {"source_key": f"plugin:explore-menu:{source}", "title": "平台别名", "year": "2026", "overview": "剧情线索"}
    result = asyncio.run(ExploreMenuPlugin().handle_api(request(source, operation="resolve", item=item, media_type="tv"), ctx))
    assert result["items"][0]["source_id"] == "318349"
    assert result["items"][0]["resolution_method"] == "ai_assisted_search"
    ctx.media.assist_identity.assert_awaited_once_with(source="tmdb", title="平台别名", media_type="tv", year="2026", overview="剧情线索", allow_single_candidate=True)


@pytest.mark.parametrize("changes", [{"source_key": "other"}, {"year": "1990"}, {"media_type": "movie"}, {"source_id": ""}])
def test_assistance_cannot_override_source_type_or_year(changes):
    ctx = context([], assisted=entry(**changes))
    assert asyncio.run(resolve(ctx, entry(), "tv")) is None


def test_ambiguous_results_are_not_silently_picked():
    ctx = context([entry(), entry(source_id="other")])
    assert asyncio.run(resolve(ctx, entry(), "tv")) is None
    ctx.media.assist_identity.assert_awaited_once()


def test_search_and_detail_failures_have_a_bounded_fallback():
    ctx = context([entry(year="")])
    ctx.media.detail.side_effect = TimeoutError
    assert asyncio.run(resolve(ctx, entry(), "tv")) is None
    ctx.media.assist_identity.assert_awaited_once()
