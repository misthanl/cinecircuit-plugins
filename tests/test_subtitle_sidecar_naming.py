import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cinecircuit_plugins.subtitle_manager.automatic_download import _save_pool
from cinecircuit_plugins.subtitle_manager.sidecar_naming import sidecar_metadata, sidecar_label


@pytest.mark.parametrize("kind,code,title", [
    ("zh-CN-en", "zh", "简英双语"),
    ("zh-TW-en", "zh", "繁英雙語"),
    ("zh-CN", "zh-CN", "简体中文"),
    ("zh-TW", "zh-TW", "繁體中文"),
    ("en", "en", "English"),
])
def test_language_is_separate_from_display_title(kind, code, title):
    assert sidecar_metadata(kind) == {"language": code, "title": title}
    assert sidecar_label(kind) == f"{code}({title})"


def test_legacy_host_writer_uses_legacy_language_suffix_once():
    calls = []
    async def legacy(path, content, *, extension, language, overwrite):
        calls.append((path, language))
        return {"path": path + "." + language + "." + extension}
    context = SimpleNamespace(config={}, media_files=SimpleNamespace(write_subtitle=legacy))
    result = {"skipped": 0, "saved": [], "details": []}
    asyncio.run(_save_pool(context, {"media_path": "/media/movie.mkv"},
                           [(0, ("ass", "zh-CN-en", b"subtitle"), {})], set(), result))
    assert calls == [("/media/movie.mkv", "zh-CN-en")]


def test_current_host_writer_retains_display_title():
    async def current(path, content, *, extension, language, title, overwrite):
        pass
    assert sidecar_metadata("zh-CN-en", writer=current) == {"language": "zh", "title": "简英双语"}


@pytest.mark.parametrize("existing", ["movie.zh-CN-en.ass", "movie.zh(简英双语).ass"])
def test_automatic_save_respects_existing_new_and_legacy_names(existing):
    writer = AsyncMock()
    context = SimpleNamespace(config={}, media_files=SimpleNamespace(write_subtitle=writer))
    result = {"skipped": 0, "saved": [], "details": []}
    asyncio.run(_save_pool(context, {"media_path": "/media/movie.mkv"},
                           [(0, ("ass", "zh-CN-en", b"subtitle"), {})],
                           {existing.casefold()}, result))
    writer.assert_not_awaited()
    assert result["skipped"] == 1
