from cinecircuit_plugins.subtitle_manager.event_search import (
    catalog_identity,
    event_identities,
)
from cinecircuit_plugins.subtitle_manager.identity import (
    parse_nfo,
    resolve_identity,
    supplement_identity,
)

EXPECTED_YEAR = 2026


def test_event_identity_is_authoritative_and_conflicts_are_visible():
    identity = resolve_identity(
        {
            "media_path": "/Shows/File.Name.2025.S02E09.strm",
            "identity": {
                "title": "Event Title",
                "year": 2026,
                "media_type": "tv",
                "season": 1,
                "episode": 3,
                "tmdb_id": 42,
                "original_language": "ZH-CN",
            },
        },
        event_authoritative=True,
        nfo={"title": "NFO Title", "imdb_id": "tt123", "season": 2},
    )

    assert (identity.title, identity.year, identity.season, identity.episode) == (
        "Event Title",
        2026,
        1,
        3,
    )
    assert identity.imdb_id == "tt123"
    assert identity.tmdb_id == "42"
    assert identity.original_language == "zh-cn"
    assert {"identity_conflict:title", "identity_conflict:season"} <= set(
        identity.warnings
    )


def test_event_missing_fields_are_completed_from_nfo_before_path():
    identity = resolve_identity(
        {
            "media_path": "/Shows/Wrong.Name.2024.S02E08.mkv",
            "identity": {"title": "Authoritative", "episode": 8},
        },
        event_authoritative=True,
        nfo="""<episodedetails><year>2025</year><season>2</season>
               <uniqueid type="imdb">tt99</uniqueid></episodedetails>""",
    )

    assert identity.title == "Authoritative"
    assert (identity.year, identity.season, identity.episode) == (2025, 2, 8)
    assert identity.imdb_id == "tt99"


def test_host_path_inferences_are_not_treated_as_event_authority():
    identity = resolve_identity(
        {
            "media_path": "/Shows/Wrong.File.Name.2024.S02E08.strm",
            "identity": {
                "title": "Wrong File Name",
                "year": "2024",
                "season": "2",
                "episode": "8",
                "media_type": "tv",
            },
            "identity_inferred_fields": [
                "title",
                "year",
                "season",
                "episode",
                "media_type",
            ],
        },
        event_authoritative=True,
        nfo={"title": "NFO Show", "year": 2026, "season": 1, "episode": 3},
    )

    assert (identity.title, identity.year, identity.season, identity.episode) == (
        "NFO Show",
        2026,
        1,
        3,
    )
    assert not identity.warnings


def test_catalog_nfo_supplements_event_without_promoting_path_guesses():
    event = resolve_identity(
        {
            "media_path": "/media/Wrong.Path.2024.S01E02.strm",
            "identity": {"title": "事件剧名", "season": 1, "episode": 2},
        },
        event_authoritative=True,
    )

    completed = supplement_identity(
        event,
        {
            "title": "目录剧名",
            "year": 2026,
            "tmdb_id": "123",
            "original_title": "Event Show",
        },
    )

    assert completed.title == "事件剧名"
    assert completed.year == EXPECTED_YEAR
    assert completed.tmdb_id == "123"
    assert completed.original_title == "Event Show"
    assert "identity_conflict:title" in completed.warnings


def test_nfo_external_ids_aliases_and_original_title():
    values = parse_nfo(
        """<movie><title>作品</title><originaltitle>Original</originaltitle>
        <alias>Alias</alias><uniqueid type="tmdb">7</uniqueid>
        <uniqueid type="douban">8</uniqueid></movie>"""
    )
    assert values["title"] == "作品"
    assert values["original_title"] == "Original"
    assert values["aliases"] == ("Alias",)
    assert values["tmdb_id"] == "7"
    assert values["douban_id"] == "8"


def test_episode_nfo_prefers_show_title_and_supports_namespaces():
    values = parse_nfo(
        """<episodedetails xmlns="urn:kodi">
        <title>第二集</title><showtitle>示例剧</showtitle>
        <season>1</season><episode>2</episode>
        <alternativetitle>Example Show</alternativetitle></episodedetails>"""
    )

    assert values["title"] == "示例剧"
    assert values["aliases"] == ("Example Show",)


def test_invalid_season_and_episode_values_are_not_coerced_to_another_episode():
    for season, episode in ((-1, 2), (0, 2), (1.5, 2), (1, "2.5"), (100, 2)):
        identity = resolve_identity(
            {
                "media_path": "/media/Show.mkv",
                "identity": {"title": "Show", "season": season, "episode": episode},
            },
            event_authoritative=True,
        )
        assert identity.season is None or identity.episode is None


def test_duplicate_event_paths_are_normalized_and_merge_complete_authority():
    identities = event_identities(
        {
            "items": [
                {
                    "media_path": r"C:\Media\Show.S01E02.strm",
                    "identity": {"title": "Show", "season": 1, "episode": 2},
                },
                {
                    "media_path": "c:/media/Show.S01E02.strm",
                    "identity": {"title": "Show", "tmdb_id": "42", "year": 2026},
                },
            ]
        }
    )

    assert len(identities) == 1
    assert identities[0].title == "Show"
    assert (identities[0].season, identities[0].episode) == (1, 2)
    assert (identities[0].tmdb_id, identities[0].year) == ("42", 2026)


def test_catalog_and_event_rows_share_model_and_keep_strm_path():
    row = {"path": "/media/Show/Show.S01E02.strm", "title": "Show"}
    catalog = catalog_identity(row)
    event = event_identities(
        {"items": [{"media_path": row["path"], "identity": {"title": "Show"}}]}
    )[0]
    assert type(catalog) is type(event)
    assert catalog.media_path.endswith(".strm")
    assert (catalog.season, catalog.episode) == (1, 2)
