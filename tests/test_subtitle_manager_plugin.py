from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from app.modules.plugins.contracts import PluginApiRequest, PluginEvent, PluginManifest
from app.modules.plugins.permissions import PluginPermission

from cinecircuit_plugins.subtitle_manager import SubtitleWorkspacePlugin
from cinecircuit_plugins.subtitle_manager.event_search import event_identities
from cinecircuit_plugins.subtitle_manager.online_sources import (
    SourceCandidate,
    SourceError,
    SourceErrorKind,
)

EXPECTED_BATCH_SIZE = 2
EXPECTED_YEAR = 2026


def test_search_languages_uses_opensubtitles_chinese_language_codes() -> None:
    assert SubtitleWorkspacePlugin._search_languages({}) == (
        "zh-cn,zh-tw,zh-ca,ze,en"
    )
    assert SubtitleWorkspacePlugin._search_languages(
        {
            "auto_subtitle_language_priority": [
                "zh-CN-en",
                "zh-TW-en",
                "zh-CN",
                "zh-TW",
                "zh",
                "en",
            ]
        }
    ) == "ze,zh-cn,zh-tw,zh-ca,en"


def test_search_languages_expands_generic_chinese_without_losing_other_languages() -> None:
    assert SubtitleWorkspacePlugin._search_languages(
        {"auto_subtitle_language_priority": ["zh", "ja", "ko", "en"]}
    ) == "zh-cn,zh-tw,zh-ca,ze,ja,ko,en"


def test_subtitle_plugin_manifest_is_isolated_and_page_enabled() -> None:
    manifest = SubtitleWorkspacePlugin.manifest
    assert manifest.frontend_module == "frontend.js"
    assert manifest.navigation == {
        "title": "字幕管理",
        "icon": "mdi-subtitles-outline",
        "section": "tools",
        "order": 65,
        "visibility_config_key": "show_sidebar_nav",
    }
    assert set(manifest.permissions) == {
        PluginPermission.ORGANIZER_HISTORY,
        PluginPermission.MEDIA_FILES_READ,
        PluginPermission.MEDIA_FILES_WRITE_SIDECAR,
        PluginPermission.NOTIFICATION_SEND,
    }
    assert PluginPermission.ORGANIZER_SUBMIT not in manifest.permissions


def test_config_merges_matching_and_removes_obsolete_controls():
    schema = SubtitleWorkspacePlugin.manifest.config_schema
    assert [section["key"] for section in schema["sections"]] == ["general", "online"]
    assert all(not section.get("description") for section in schema["sections"])
    fields = {field["key"]: field for field in schema["fields"]}
    assert not {"enabled", "auto_search_on_transfer"} & fields.keys()
    assert fields["show_sidebar_nav"]["default"] is True
    assert not any(field.get("icon") for field in fields.values())
    assert not any(field.get("section") == "automatic" for field in fields.values())
    assert fields["trigger_event"]["default"] == ""
    assert not {"ai_link_enabled", "auto_transfer_subtitle_strategy"} & fields.keys()
    assert "AI" not in str(schema)
    assert not any(key.startswith("timeline_") for key in fields)


@pytest.mark.parametrize("event_type", SubtitleWorkspacePlugin.manifest.events)
@pytest.mark.parametrize(
    "legacy_strategy", [None, "ai_source_only", "online_then_ai_source"]
)
def test_selected_event_searches_only_its_media(
    event_type, legacy_strategy, monkeypatch
):
    saver = AsyncMock(
        return_value={"media_path": "/media/one.S01E02.mkv", "saved": [], "failed": 0}
    )
    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.plugin.save_candidates", saver
    )
    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.plugin.http_client",
        lambda **_kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(500))
        ),
    )
    plugin = SubtitleWorkspacePlugin()
    candidate = SourceCandidate(
        "ASSRT",
        "candidate",
        "One S01E02",
        season=1,
        episode=2,
        downloadable=True,
        matched=True,
        score=90,
    )
    service = SimpleNamespace(
        search=AsyncMock(
            return_value=SimpleNamespace(candidates=(candidate,), errors=())
        ),
        download=AsyncMock(),
    )
    service.search_sequential = lambda requests: _single_source_reports(service, requests)
    plugin._online_service = Mock(return_value=service)
    plugin._catalog = AsyncMock(side_effect=AssertionError("must not scan history"))
    config = {"trigger_event": event_type, "show_sidebar_nav": False}
    if legacy_strategy:
        config.update(
            auto_transfer_subtitle_strategy=legacy_strategy, ai_link_enabled=True
        )
    ctx = SimpleNamespace(config=config, logger=Mock())
    row = {
        "relative_media_path": "/media/one.S01E02.mkv",
        "identity": {"title": "One", "media_type": "tv", "season": 1, "episode": 2},
    }
    result = asyncio.run(
        plugin.on_event(PluginEvent(event_type, {"items": [row, row]}), ctx)
    )
    service.search.assert_awaited_once()
    assert [item.query for item in service.search.await_args.args[0]] == ["One S01E02"]
    assert result["media_count"] == 1
    assert result["items"][0]["media_path"] == "/media/one.S01E02.mkv"
    plugin._catalog.assert_not_awaited()
    assert saver.call_args.args[1]["media_path"] == "/media/one.S01E02.mkv"
    assert saver.call_args.kwargs["downloader"] is service.download


def test_event_media_target_prefers_resolved_media_path():
    from cinecircuit_plugins.subtitle_manager.event_search import media_targets

    targets = media_targets(
        {
            "items": [
                {
                    "relative_media_path": "Shows/Demo.S01E01.mkv",
                    "media_path": "/strm/Shows/Demo.S01E01.strm",
                    "identity": {"title": "Demo", "season": 1, "episode": 1},
                }
            ]
        }
    )

    assert targets == [
        {
            "media_path": "/strm/Shows/Demo.S01E01.strm",
            "keyword": "Demo S01 E01",
            "title": "Demo",
            "year": "",
            "season": "1",
            "episode": "1",
            "language": "",
        }
    ]


def test_event_uses_catalog_nfo_supplement_and_only_downloads_top_match(
    monkeypatch,
):
    saver = AsyncMock(
        return_value={
            "media_path": "/media/one.S01E02.strm",
            "saved": [],
            "failed": 0,
        }
    )
    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.plugin.save_candidates", saver
    )
    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.plugin.http_client",
        lambda **_kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(500))
        ),
    )
    best = SourceCandidate(
        "ASSRT",
        "best",
        "Event S01E02",
        season=1,
        episode=2,
        downloadable=True,
        matched=True,
        score=96,
    )
    second = SourceCandidate(
        "SubHD",
        "second",
        "Event S01E02",
        season=1,
        episode=2,
        downloadable=True,
        matched=True,
        score=90,
    )
    service = SimpleNamespace(
        search=AsyncMock(
            return_value=SimpleNamespace(candidates=(best, second), errors=())
        ),
        download=AsyncMock(),
    )
    plugin = SubtitleWorkspacePlugin()
    service.search_sequential = lambda requests: _single_source_reports(service, requests)
    plugin._online_service = Mock(return_value=service)
    path = "/media/one.S01E02.strm"
    ctx = SimpleNamespace(
        config={"trigger_event": "sync.completed", "auto_match_score": 75},
        logger=Mock(),
        media_files=SimpleNamespace(
            catalog=AsyncMock(
                return_value={
                    "items": [
                        {
                            "path": path,
                            "identity": {
                                "title": "NFO title",
                                "year": 2026,
                                "tmdb_id": "42",
                                "season": 1,
                                "episode": 2,
                            },
                        }
                    ]
                }
            )
        ),
    )

    asyncio.run(
        plugin.on_event(
            PluginEvent(
                "sync.completed",
                {
                    "items": [
                        {
                            "media_path": path,
                            "identity": {
                                "title": "Event",
                                "media_type": "tv",
                                "season": 1,
                                "episode": 2,
                            },
                        }
                    ]
                },
            ),
            ctx,
        )
    )

    request = service.search.await_args.args[0][0]
    assert request.year == EXPECTED_YEAR
    assert request.tmdb_id == "42"
    assert saver.await_args.args[2] == [best]


def test_event_batch_reads_catalog_once_and_rejects_unavailable_candidate(
    monkeypatch,
):
    saver = AsyncMock(
        return_value={"media_path": "/media/item.strm", "saved": [], "failed": 0}
    )
    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.plugin.save_candidates", saver
    )
    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.plugin.http_client",
        lambda **_kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(500))
        ),
    )
    candidate = SourceCandidate(
        "SubHD", "downloadable", "Movie 2026", downloadable=True, matched=True, score=90
    )
    unavailable = SourceCandidate(
        "OpenSubtitles",
        "login-required",
        "Movie 2026",
        downloadable=False,
        matched=True,
        score=99,
    )
    service = SimpleNamespace(
        search=AsyncMock(
            return_value=SimpleNamespace(candidates=(unavailable, candidate), errors=())
        ),
        download=AsyncMock(),
    )
    plugin = SubtitleWorkspacePlugin()
    service.search_sequential = lambda requests: _single_source_reports(service, requests)
    plugin._online_service = Mock(return_value=service)
    catalog = AsyncMock(return_value={"items": []})
    context = SimpleNamespace(
        config={"trigger_event": "sync.completed"},
        logger=Mock(),
        media_files=SimpleNamespace(catalog=catalog),
    )
    items = [
        {
            "media_path": f"/media/movie-{index}.strm",
            "identity": {"title": f"Movie {index}", "year": 2026},
        }
        for index in range(2)
    ]

    asyncio.run(
        plugin.on_event(PluginEvent("sync.completed", {"items": items}), context)
    )

    catalog.assert_awaited_once_with(query="", limit=500)
    assert saver.await_count == EXPECTED_BATCH_SIZE
    assert all(call.args[2] == [candidate] for call in saver.await_args_list)


def test_event_catalog_error_is_logged_and_exposed_as_identity_warning():
    plugin = SubtitleWorkspacePlugin()
    context = SimpleNamespace(
        logger=Mock(),
        media_files=SimpleNamespace(
            catalog=AsyncMock(side_effect=OSError("catalog unavailable"))
        ),
    )
    identity = event_identities(
        {
            "items": [
                {
                    "media_path": "/media/Movie.2026.strm",
                    "identity": {"title": "Movie", "year": 2026},
                }
            ]
        }
    )[0]

    completed = asyncio.run(plugin._supplement_event_identities(context, [identity]))

    assert completed[0].warnings == ("identity_supplement_failed",)
    assert "catalog unavailable" in str(context.logger.warning.call_args.args[1])


@pytest.mark.parametrize(
    "edited,season_pack,expected",
    [
        ("Example Show S02E09", False, "Example Show S01E02"),
        ("Example Show S02", False, "Example Show S01E02"),
        ("Example Show S02E09", True, "Example Show S01"),
    ],
)
def test_edited_episode_query_replaces_conflicting_identity_token(
    edited, season_pack, expected
):
    identity = event_identities(
        {
            "items": [
                {
                    "media_path": "/media/Example.Show.S01E02.strm",
                    "identity": {
                        "title": "Example Show",
                        "media_type": "tv",
                        "season": 1,
                        "episode": 2,
                    },
                }
            ]
        }
    )[0]

    queries = SubtitleWorkspacePlugin._queries_for_search(
        identity, [], edited, season_pack=season_pack
    )

    assert queries[0].keyword == expected


def test_manual_actions_and_error_payload_reject_unsafe_public_links():
    assert (
        SubtitleWorkspacePlugin._manual_search_actions(
            {"online_providers": ["subhd"], "subhd_url": "javascript:alert(1)"},
            "Movie",
        )
        == []
    )
    error = SourceError(
        "SubHD",
        SourceErrorKind.CAPTCHA,
        "restricted",
        manual_url="https://user:secret@example.test/search",
    )

    assert SubtitleWorkspacePlugin._error_dict(error)["manual_url"] == ""


@pytest.mark.parametrize(
    "selected,items",
    [
        ("", [{"relative_media_path": "one.mkv"}]),
        ("sync.completed", [{"relative_media_path": "one.mkv"}]),
        ("organizer.completed", []),
        ("organizer.completed", [{"identity": {"title": "One"}}]),
    ],
)
def test_irrelevant_or_targetless_event_does_not_scan(selected, items):
    plugin = SubtitleWorkspacePlugin()
    plugin._online_search = AsyncMock()
    ctx = SimpleNamespace(config={"trigger_event": selected}, logger=Mock())
    result = asyncio.run(
        plugin.on_event(PluginEvent("organizer.completed", {"items": items}), ctx)
    )
    assert result["status"] == "skipped"
    plugin._online_search.assert_not_awaited()


@pytest.mark.parametrize("section", ["admin", "sidebar", "unknown"])
def test_plugin_navigation_rejects_unknown_sections(section: str) -> None:
    with pytest.raises(ValueError, match="navigation.section"):
        PluginManifest.from_dict(
            {
                "id": "page-test",
                "name": "Page",
                "version": "1",
                "navigation": {"title": "Page", "section": section},
            }
        )


def test_subtitle_upload_rejects_paths_outside_managed_directories() -> None:
    plugin = SubtitleWorkspacePlugin()
    context = SimpleNamespace(
        config={},
        organizer=SimpleNamespace(
            has_successful_destination=AsyncMock(return_value=False)
        ),
        media_files=SimpleNamespace(
            write_subtitle=AsyncMock(), is_catalog_media=AsyncMock(return_value=False)
        ),
    )
    request = PluginApiRequest(
        action="upload",
        method="POST",
        query={"media_path": "/media/movie.mkv"},
        content="1\n00:00:00,000 --> 00:00:01,000\n字幕\n".encode(),
        filename="movie.srt",
    )

    with pytest.raises(ValueError, match="同步或整理目录"):
        asyncio.run(plugin.handle_api(request, context))
    context.media_files.write_subtitle.assert_not_awaited()


def test_subtitle_poster_uses_the_file_gateway() -> None:
    plugin = SubtitleWorkspacePlugin()
    poster = AsyncMock(
        return_value={"data_url": "data:image/jpeg;base64,cG9zdGVy", "content_type": "image/jpeg"}
    )
    context = SimpleNamespace(media_files=SimpleNamespace(poster=poster))
    request = PluginApiRequest(
        action="poster",
        method="GET",
        query={"media_path": "/media/movie.strm"},
    )

    result = asyncio.run(plugin.handle_api(request, context))

    assert result["content_type"] == "image/jpeg"
    poster.assert_awaited_once_with("/media/movie.strm")


def test_subtitle_upload_accepts_configured_strm_catalog_media() -> None:
    plugin = SubtitleWorkspacePlugin()
    writer = AsyncMock(return_value={"subtitle_path": "/media/movie.zh-CN.srt"})
    context = SimpleNamespace(
        config={"overwrite_existing": False},
        organizer=SimpleNamespace(
            has_successful_destination=AsyncMock(return_value=False)
        ),
        media_files=SimpleNamespace(
            is_catalog_media=AsyncMock(return_value=True), write_subtitle=writer
        ),
    )
    request = PluginApiRequest(
        action="upload",
        method="POST",
        query={"media_path": "/media/movie.strm", "language": "zh-CN"},
        content=b"subtitle",
        filename="movie.srt",
    )

    asyncio.run(plugin.handle_api(request, context))

    writer.assert_awaited_once()


def test_subtitle_upload_uses_safe_sidecar_gateway() -> None:
    plugin = SubtitleWorkspacePlugin()
    writer = AsyncMock(return_value={"subtitle_path": "/media/movie.zh-CN.srt"})
    context = SimpleNamespace(
        config={"default_language": "zh-CN", "overwrite_existing": False},
        organizer=SimpleNamespace(
            has_successful_destination=AsyncMock(return_value=True)
        ),
        media_files=SimpleNamespace(
            write_subtitle=writer, is_catalog_media=AsyncMock(return_value=False)
        ),
    )
    request = PluginApiRequest(
        action="upload",
        method="POST",
        query={"media_path": "/media/movie.mkv"},
        content="1\n00:00:01,000 --> 00:00:02,000\n欢迎观看\n".encode(),
        filename="movie.srt",
    )

    result = asyncio.run(plugin.handle_api(request, context))

    assert result["subtitle_path"].endswith("movie.zh-CN.srt")
    writer.assert_awaited_once_with(
        "/media/movie.mkv",
        "1\n00:00:01,000 --> 00:00:02,000\n欢迎观看\n".encode(),
        extension="srt",
        language="zh-CN",
        overwrite=False,
    )


async def _single_source_reports(service, requests):
    yield await service.search(requests)
