from cinecircuit_plugins.subtitle_manager.event_search import (
    event_search_plans,
    media_targets,
)
from cinecircuit_plugins.subtitle_manager.identity import MediaIdentity
from cinecircuit_plugins.subtitle_manager.search_plan import build_search_plan

EXPECTED_EPISODE = 20
EXPECTED_SEASON = 2


def test_episode_queries_all_use_same_compact_season_episode():
    identity = MediaIdentity(
        title="早春晴朗",
        english_title="Early Spring",
        aliases=("春日",),
        tmdb_id="42",
        media_type="tv",
        year=2026,
        season=1,
        episode=20,
    )
    plan = build_search_plan(identity)
    assert [query.keyword for query in plan.queries] == [
        "早春晴朗 S01E20",
        "Early Spring S01E20",
        "春日 S01E20",
    ]
    assert all(
        query.season == 1 and query.episode == EXPECTED_EPISODE
        for query in plan.queries
    )
    assert all("S01E20" in query.keyword for query in plan.queries)
    assert all(query.parameters()["tmdb_id"] == "42" for query in plan.queries)


def test_incomplete_episode_identity_never_falls_back_to_bare_title():
    plan = build_search_plan(MediaIdentity(title="Show", media_type="tv", season=1))
    assert plan.queries == ()
    assert plan.errors == ("missing_episode",)


def test_season_package_requires_explicit_switch():
    identity = MediaIdentity(title="Show", media_type="tv", season=2)
    assert build_search_plan(identity).queries == ()
    plan = build_search_plan(identity, season_pack=True)
    assert [query.keyword for query in plan.queries] == ["Show S02"]
    assert plan.queries[0].parameters()["season"] == EXPECTED_SEASON
    assert "episode" not in plan.queries[0].parameters()


def test_movie_uses_year_and_language_titles():
    plan = build_search_plan(
        MediaIdentity(title="电影", english_title="Movie", aliases=("Film",), year=2026)
    )
    assert [query.keyword for query in plan.queries] == [
        "电影 2026",
        "Movie 2026",
        "Film 2026",
    ]


def test_event_plans_never_enable_season_pack_and_legacy_targets_remain_compatible():
    data = {
        "items": [
            {
                "media_path": "/Show.mkv",
                "identity": {
                    "title": "Show",
                    "media_type": "tv",
                    "season": 1,
                    "episode": 2,
                },
            }
        ]
    }
    assert event_search_plans(data)[0].queries[0].keyword == "Show S01E02"
    assert event_search_plans(data)[0].season_pack is False
    assert media_targets(data)[0]["keyword"] == "Show S01 E02"
