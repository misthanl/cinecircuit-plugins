from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cinecircuit_plugins.subtitle_manager import SubtitleWorkspacePlugin
from app.modules.plugins.contracts import PluginApiRequest, PluginManifest
from app.modules.plugins.permissions import PluginPermission


def test_subtitle_plugin_manifest_is_isolated_and_page_enabled() -> None:
    manifest = SubtitleWorkspacePlugin.manifest
    assert manifest.frontend_module == "frontend.js"
    assert manifest.navigation == {
        "title": "字幕管理",
        "icon": "mdi-subtitles-outline",
        "section": "tools",
        "order": 65,
    }
    assert set(manifest.permissions) == {
        PluginPermission.ORGANIZER_HISTORY,
        PluginPermission.MEDIA_FILES_READ,
        PluginPermission.MEDIA_FILES_WRITE_SIDECAR,
        PluginPermission.NOTIFICATION_SEND,
    }
    assert PluginPermission.ORGANIZER_SUBMIT not in manifest.permissions


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


def test_subtitle_upload_requires_successful_organizer_destination() -> None:
    plugin = SubtitleWorkspacePlugin()
    context = SimpleNamespace(
        config={},
        organizer=SimpleNamespace(has_successful_destination=AsyncMock(return_value=False)),
        media_files=SimpleNamespace(write_subtitle=AsyncMock()),
    )
    request = PluginApiRequest(
        action="upload",
        method="POST",
        query={"media_path": "/media/movie.mkv"},
        content="1\n00:00:00,000 --> 00:00:01,000\n字幕\n".encode(),
        filename="movie.srt",
    )

    with pytest.raises(ValueError, match="成功整理记录"):
        asyncio.run(plugin.handle_api(request, context))
    context.media_files.write_subtitle.assert_not_awaited()


def test_subtitle_upload_uses_safe_sidecar_gateway() -> None:
    plugin = SubtitleWorkspacePlugin()
    writer = AsyncMock(return_value={"subtitle_path": "/media/movie.zh-CN.srt"})
    context = SimpleNamespace(
        config={"default_language": "zh-CN", "overwrite_existing": False},
        organizer=SimpleNamespace(has_successful_destination=AsyncMock(return_value=True)),
        media_files=SimpleNamespace(write_subtitle=writer),
    )
    request = PluginApiRequest(
        action="upload",
        method="POST",
        query={"media_path": "/media/movie.mkv"},
        content=b"subtitle",
        filename="movie.srt",
    )

    result = asyncio.run(plugin.handle_api(request, context))

    assert result["subtitle_path"].endswith("movie.zh-CN.srt")
    writer.assert_awaited_once_with(
        "/media/movie.mkv",
        b"subtitle",
        extension="srt",
        language="zh-CN",
        overwrite=False,
    )
