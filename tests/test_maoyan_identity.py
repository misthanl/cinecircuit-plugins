import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from datetime import date

from cinecircuit_plugins.maoyan_rank.identity import match_identity, release_hint


def candidate(id, year):
    return dict(title="作品", media_type="movie", source_key="tmdb", source_id=id, year=year)


def run(items, row=None, dates=None, cache=None):
    media = SimpleNamespace(search=AsyncMock(return_value={"items": items}),
                            detail=AsyncMock(side_effect=dates))
    value = asyncio.run(match_identity(SimpleNamespace(media=media),
        dict(title="作品", media_type="movie", **(row or {})), cache if cache is not None else {}))
    return value, media


def test_unique_title_or_reliable_year_does_not_calculate_or_fetch_details():
    with patch('cinecircuit_plugins.maoyan_rank.identity.release_hint', side_effect=AssertionError):
        result, media = run([candidate('1', '2026')])
        assert result['source_id'] == '1'
        media.detail.assert_not_called()
        result, media = run([candidate('1', '2026'), candidate('2', '2016')], {'year': '2026'})
        assert result['source_id'] == '1'
        media.detail.assert_not_called()


def test_relative_date_uses_board_day_and_crosses_year_boundary():
    assert release_hint({'release_info': '上映26天', 'board_date': '2026-09-08'}) == date(2026, 8, 14)
    assert release_hint({'release_info': '上线3天', 'board_date': '2026-01-02'}) == date(2025, 12, 31)
    assert release_hint({'release_info': '上映0天', 'board_date': '2026-09-08'}) is None
    assert release_hint({'release_info': '重映26天', 'board_date': '2026-09-08'}) is None


def test_ambiguous_same_year_uses_date_and_caches_only_success():
    cache = {}
    row = {'release_info': '上映26天', 'board_date': '2026-09-08'}
    result, media = run([candidate('1', '2026'), candidate('2', '2026')], row,
                        [{'date': '2026-08-14'}, {'date': '2026-01-01'}], cache)
    assert result['source_id'] == '1'
    assert media.detail.await_count == 2
    result, media = run([], row, [], cache)
    assert result['source_id'] == '1'
    media.search.assert_not_called()


def test_no_exact_date_match_chooses_most_recent_exact_title():
    items = [candidate('1', '2026'), candidate('2', '2026')]
    row = {'release_info': '上映26天', 'board_date': '2026-09-08'}
    result, _media = run(items, row, [{'date': '2026-01-01'}, {'date': '2026-08-01'}])
    assert result['source_id'] == '2'


def test_regional_release_dates_disambiguate_odyssey_and_obsession():
    for elapsed, cn_date in [(26, '2026-08-14'), (47, '2026-07-24')]:
        items = [candidate('current', '2026'), candidate('older', '2026')]
        current = {'release_dates': {'results': [{
            'iso_3166_1': 'CN', 'release_dates': [{'release_date': cn_date + 'T00:00:00.000Z'}],
        }]}, 'date': '2026-05-01'}
        result, _media = run(
            items,
            {'release_info': f'上映{elapsed}天', 'board_date': '2026-09-08'},
            [current, {'date': '2026-01-01'}],
        )
        assert result['source_id'] == 'current'


def test_latest_fallback_uses_search_dates_when_detail_fails_and_keeps_exact_titles_only():
    items = [
        {**candidate('old', '2025'), 'date': '2025-01-01'},
        {**candidate('new', '2026'), 'date': '2026-05-13'},
        {**candidate('wrong', '2027'), 'title': '作品续集', 'date': '2027-01-01'},
    ]
    result, _media = run(items, {'board_date': '2026-09-08'}, [RuntimeError('offline')] * 2)
    assert result['source_id'] == 'new'


def test_no_dates_still_refuses_an_arbitrary_candidate():
    result, _media = run([candidate('1', ''), candidate('2', '')], dates=[{}, {}])
    assert result is None


def sequel_context(items=None, seasons=None):
    base = dict(title="问心", media_type="tv", source_key="tmdb", source_id="1", year="2023")
    return SimpleNamespace(media=SimpleNamespace(
        search=AsyncMock(side_effect=[{"items": items or []}, {"items": [base]}]),
        detail=AsyncMock(return_value={"seasons": seasons or []}),
    ))


def test_numeric_sequel_uses_target_season_year_and_reuses_verified_cache():
    from cinecircuit_plugins.maoyan_rank.plugin import MaoyanWatchlistPlugin
    ctx = sequel_context(seasons=[{"season_number": 2, "air_date": "2026-09-01"}])
    row = dict(title="问心2", media_type="tv", year="2026")
    cache = {}
    result = asyncio.run(match_identity(ctx, row, cache))
    payload = MaoyanWatchlistPlugin()._subscription_candidate(row, result)
    assert payload["source_id"] == "1"
    assert payload["season"] == "S02"
    assert "_maoyan_verified_season" not in payload
    assert asyncio.run(match_identity(ctx, row, cache)) == result
    assert ctx.media.search.await_count == 2
    ctx.media.detail.assert_awaited_once()
    assert ctx.media.detail.call_args.args[1]["include_credits"] is False


@pytest.mark.parametrize("seasons", [[], [{"season_number": 1, "air_date": "2026-09-01"}],
    [{"season_number": 2, "air_date": "2025-09-01"}], [{"season_number": 2}]])
def test_numeric_sequel_missing_or_conflicting_season_stays_unresolved(seasons):
    ctx = sequel_context(seasons=seasons)
    assert asyncio.run(match_identity(ctx, dict(title="问心2", media_type="tv", year="2026"), {})) is None


def test_numeric_exact_title_keeps_independent_series_and_no_extra_requests():
    item = dict(title="问心2", media_type="tv", source_key="tmdb", source_id="2")
    ctx = sequel_context(items=[item])
    assert asyncio.run(match_identity(ctx, dict(title="问心2", media_type="tv"), {})) == item
    ctx.media.search.assert_awaited_once()
    ctx.media.detail.assert_not_called()


@pytest.mark.parametrize("title,media_type,year", [
    ("问心2026", "tv", "2026"), ("问心2", "movie", "2026"), ("问心2", "tv", "")])
def test_numeric_fallback_does_not_query_without_usable_evidence(title, media_type, year):
    ctx = sequel_context()
    assert asyncio.run(match_identity(ctx, dict(title=title, media_type=media_type, year=year), {})) is None
    ctx.media.search.assert_awaited_once()
    ctx.media.detail.assert_not_called()


def test_numeric_fallback_reuses_base_candidate_from_first_search():
    base = dict(title="问心", media_type="tv", source_key="tmdb", source_id="1")
    ctx = sequel_context(items=[base], seasons=[{"season_number": 2, "air_date": "2026-09-01"}])
    row = dict(title="问心2", media_type="tv", release_info="上线3天", board_date="2026-09-03")
    assert asyncio.run(match_identity(ctx, row, {}))["_maoyan_verified_season"] == 2
    ctx.media.search.assert_awaited_once()


def test_numeric_fallback_accepts_explicit_release_year():
    ctx = sequel_context(seasons=[{"season_number": 2, "air_date": "2026-09-01"}])
    row = dict(title="问心2", media_type="tv", release_info="2026年上线")
    assert asyncio.run(match_identity(ctx, row, {}))["_maoyan_verified_season"] == 2


def test_numeric_fallback_refuses_ambiguous_base_without_detail_fanout():
    items = [dict(title="问心", media_type="tv", source_key="tmdb", source_id=str(i)) for i in (1, 2)]
    ctx = sequel_context(items=items)
    assert asyncio.run(match_identity(ctx, dict(title="问心2", media_type="tv", year="2026"), {})) is None
    ctx.media.search.assert_awaited_once()
    ctx.media.detail.assert_not_called()


@pytest.mark.parametrize("suffix,season", [("第三季", "S03"), ("第 3 季", "S03"), ("第十二季", "S12"), ("S03", "S03")])
def test_explicit_season_fallback_keeps_target_season(suffix, season):
    from cinecircuit_plugins.maoyan_rank.plugin import MaoyanWatchlistPlugin
    base = "汪汪队之小砾与工程家族"
    item = dict(title=base, media_type="tv", source_key="tmdb", source_id="214875", year="2023")
    translated = {**item, "title": base + "（中文版）", "source_id": "286277"}
    ctx = SimpleNamespace(media=SimpleNamespace(search=AsyncMock(side_effect=[
        {"items": []}, {"items": [translated, item]},
    ])))
    row = dict(title=base + " " + suffix, media_type="tv", year="2026")
    cache = {}
    result = asyncio.run(match_identity(ctx, row, cache))
    payload = MaoyanWatchlistPlugin()._subscription_candidate(row, result)
    assert payload["source_id"] == "214875"
    assert payload["season"] == season
    assert payload["rank_source"]["title"] == row["title"]
    assert ctx.media.search.call_args.args == (base,)
    assert asyncio.run(match_identity(ctx, row, cache)) == result
    assert ctx.media.search.await_count == 2


def test_season_fallback_does_not_choose_between_same_name_series():
    items = [dict(title="作品", media_type="tv", source_key="tmdb", source_id=str(i), year=str(2023+i)) for i in (1, 2)]
    ctx = SimpleNamespace(media=SimpleNamespace(search=AsyncMock(side_effect=[
        {"items": []}, {"items": items}, {"items": []}, {"items": []},
    ])))
    row = dict(title="作品 第三季", media_type="tv", year="2025")
    cache = {}
    assert asyncio.run(match_identity(ctx, row, cache)) is None
    assert not cache
    assert asyncio.run(match_identity(ctx, row, cache)) is None
    assert ctx.media.search.await_count == 4


@pytest.mark.parametrize("title,kind", [("作品 第三季", "movie"), ("第三季故事", "tv"), ("作品 第百季", "tv")])
def test_season_fallback_does_not_strip_unrelated_or_unsupported_titles(title, kind):
    ctx = SimpleNamespace(media=SimpleNamespace(search=AsyncMock(return_value={"items": []})))
    assert asyncio.run(match_identity(ctx, dict(title=title, media_type=kind), {})) is None
    ctx.media.search.assert_awaited_once()
