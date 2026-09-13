import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.modules.plugins.contracts import PluginApiRequest
from cinecircuit_plugins.subtitle_manager.plugin import SubtitleWorkspacePlugin
from cinecircuit_plugins.subtitle_manager.event_search import catalog_identity


def test_page_uses_paged_sdk_records_without_scanning_subtitles():
    files = SimpleNamespace(
        recorded_catalog=AsyncMock(return_value={
            "items": [{"path": "/media/later.mkv", "title": "Later"}],
            "count": 1, "has_more": True, "offset": 500,
        }),
        catalog=AsyncMock(side_effect=AssertionError("directory scan")),
        subtitles=AsyncMock(side_effect=AssertionError("eager subtitle scan")),
    )
    result = asyncio.run(SubtitleWorkspacePlugin().handle_api(
        PluginApiRequest(action="catalog", method="GET", query={"offset": "500", "limit": "100", "query": "Later"}),
        SimpleNamespace(media_files=files),
    ))
    files.recorded_catalog.assert_awaited_once_with(query="Later", limit=100, offset=500)
    assert result["has_more"] is True
    assert result["offset"] == 500
    assert "subtitles" not in result["items"][0]


def test_online_identity_uses_exact_recorded_path_not_first_catalog_page():
    files = SimpleNamespace(
        recorded_detail=AsyncMock(return_value={
            "path": "/media/last.strm", "title": "Last",
            "identity": {"title": "Last", "tmdb_id": "42"},
        }),
        catalog=AsyncMock(side_effect=AssertionError("directory scan")),
    )
    result = asyncio.run(SubtitleWorkspacePlugin()._catalog_media_identity(
        SimpleNamespace(media_files=files), "/media/last.strm",
    ))
    assert result.tmdb_id == "42"
    files.recorded_detail.assert_awaited_once_with("/media/last.strm")


def test_catalog_filename_title_falls_back_to_clean_path_identity():
    identity = catalog_identity({
        "path": "/media/电影/盗梦空间 (2010)/盗梦空间 (2010) - 2160p.strm",
        "name": "盗梦空间 (2010) - 2160p.strm",
        "title": "盗梦空间 (2010) - 2160p.mkv",
    })
    assert identity.title == "盗梦空间"
    assert identity.year == 2010


def test_catalog_structured_title_still_wins_over_filename_display_title():
    identity = catalog_identity({
        "path": "/media/Inception (2010)/Inception (2010) - 2160p.strm",
        "title": "Inception (2010) - 2160p.mkv",
        "identity": {"title": "盗梦空间", "year": 2010, "tmdb_id": "27205"},
    })
    assert identity.title == "盗梦空间"
    assert identity.year == 2010
    assert identity.tmdb_id == "27205"
