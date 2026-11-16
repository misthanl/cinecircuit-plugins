import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from .identity import resolve
from .plugin import ExploreMenuPlugin
from .titles import annotate, title_context
from .test_plugin import request


@pytest.mark.parametrize("title,clean,base,season", [
    ("玫瑰战争[普通话版]", "玫瑰战争", "玫瑰战争", 0),
    ("庆余年第二季", "庆余年第二季", "庆余年", 2),
    ("小猪佩奇 第12季（国语版）", "小猪佩奇 第12季", "小猪佩奇", 12),
    ("蓝色星球 第3季", "蓝色星球 第3季", "蓝色星球", 3),
    ("蓝色星球3", "蓝色星球3", "蓝色星球3", 0),
])
def test_only_explicit_editions_and_season_suffixes_are_split(title, clean, base, season):
    value = title_context({"title": title})
    assert (value["title"], value["series_title"], value["season"]) == (clean, base, season)
    assert annotate({"title": title})["catalog_title"] == title


def context(search, lookup=None, orders=None):
    return SimpleNamespace(config={}, media=SimpleNamespace(search=AsyncMock(return_value={"items": search}),
        search_source_identity=AsyncMock(side_effect=lookup), series_orders=AsyncMock(return_value=orders or []),
        assist_identity=AsyncMock(return_value=None)))


def media(title, identity, year="2026", **extra):
    return {"title": title, "source_id": identity, "source_key": "tmdb", "media_type": "tv", "year": year, **extra}


def test_parent_season_is_preferred_over_an_independent_duplicate_and_keeps_canonical_year():
    canonical = media("庆余年", "95842", "2019", requested_season=2,
                      season_identity={"season": 2, "year": "2024", "episode_count": 36})
    ctx = context([media("庆余年第二季", "274493", "2024")], lookup=lambda **kwargs: canonical)
    item = {"source_key": "plugin:explore-menu:tencent", "title": "庆余年第二季", "year": "2024"}
    result = asyncio.run(ExploreMenuPlugin().handle_api(request("tencent", operation="resolve", item=item, media_type="tv"), ctx))["items"][0]
    assert (result["title"], result["source_id"], result["year"], result["requested_season"]) == ("庆余年", "95842", "2019", 2)
    assert result["catalog_year"] == "2024" and result["season_year"] == "2024"
    ctx.media.assist_identity.assert_not_awaited()


def test_real_independent_sequel_is_preserved():
    ctx = context([media("蓝色星球3", "208929")], lookup=lambda **kwargs: None)
    result = asyncio.run(resolve(ctx, {"title": "蓝色星球 第3季", "year": "2026"}, "documentary"))
    assert result["source_id"] == "208929" and result["requested_season"] == 1


def test_alternate_order_with_missing_dates_is_kept_as_selected_target():
    group = "a" * 24
    canonical = media("小猪佩奇", "12225", "2004", requested_season=12, episode_group_id=group,
        season_identity={"season": 12, "year": "", "episode_count": 26, "episode_group_id": group})
    ctx = context([media("小猪佩奇", "12225", "2004")],
        lookup=lambda **kwargs: canonical if kwargs["episode_evidence"].get("episode_group_id") else None,
        orders=[{"id": group, "name": "Domestic order", "seasons": [{"season_number": 12, "episode_count": 26}]}])
    item = {"source_key": "plugin:explore-menu:tencent", "title": "小猪佩奇 第12季", "year": "2026"}
    result = asyncio.run(ExploreMenuPlugin().handle_api(request("tencent", operation="resolve", item=item, media_type="kids"), ctx))["items"][0]
    assert result["source_id"] == "12225" and result["episode_group_id"] == group and result["requested_season"] == 12
    assert result["identity_warnings"] and result["episode_order_name"] == "Domestic order"


def test_unique_ai_target_with_source_verified_warning_is_not_discarded():
    ctx = context([], lookup=lambda **kwargs: None)
    ctx.media.assist_identity.return_value = media("Canonical", "42", "2004", identity_warnings=["Season date unavailable"])
    result = asyncio.run(resolve(ctx, {"title": "Provider alias", "year": "2026"}, "tv"))
    assert result["source_id"] == "42" and result["identity_warnings"]
