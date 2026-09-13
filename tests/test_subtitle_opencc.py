import importlib
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from cinecircuit_plugins.subtitle_manager.automatic_download import (
    PreparationContext,
    prepare_file,
)


@pytest.mark.parametrize(
    "extension,text",
    [
        ("srt", "1\n00:00:01,000 --> 00:00:02,000\n繁體字幕，歡迎觀看！\n"),
        ("vtt", "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n繁體字幕，歡迎觀看！\n"),
        (
            "ass",
            "[Script Info]\nTitle: test\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,"
            "{\\b1}繁體字幕，歡迎觀看！{\\b0}\\NHello\n",
        ),
        (
            "ssa",
            "[Script Info]\n[Events]\n"
            "Dialogue: Marked=0,0:00:01.00,0:00:02.00,Default,,0,0,0,,"
            "繁體字幕，歡迎觀看！\n",
        ),
    ],
)
def test_real_conversion_without_global_opencc(extension, text, monkeypatch):
    monkeypatch.setitem(sys.modules, "opencc", None)
    result = prepare_file(
        PreparationContext(
            {"traditional_to_simplified": True},
            {
                "media_path": "/Show.S01E02.mkv",
                "title": "Show",
                "keyword": "Show S01E02",
            },
            {"title": "Show", "language": "zh-TW"},
        ),
        f"Show.S01E02.cht.{extension}",
        text.encode(),
    )
    assert result[:2] == (extension, "zh-CN")
    assert result[2].decode() == text.replace(
        "繁體字幕，歡迎觀看！", "繁体字幕，欢迎观看！"
    )
    assert sys.modules["opencc"] is None


def test_disabled_conversion_preserves_traditional_text():
    text = "1\n00:00:01,000 --> 00:00:02,000\n繁體字幕\n"
    result = prepare_file(
        PreparationContext(
            {"traditional_to_simplified": False},
            {
                "media_path": "/Show.S01E02.mkv",
                "title": "Show",
                "keyword": "Show S01E02",
            },
            {"title": "Show", "language": "zh-TW"},
        ),
        "Show.S01E02.cht.srt",
        text.encode(),
    )
    assert result[1:] == ("zh-TW", text.encode())


def test_packaged_plugin_loads_private_converter_without_host_dependency(
    tmp_path, monkeypatch
):
    from app.modules.plugins.registry import PluginRegistry

    from cinecircuit_plugins.subtitle_manager.plugin import SubtitleWorkspacePlugin

    source = Path(
        importlib.import_module(SubtitleWorkspacePlugin.__module__).__file__
    ).parent
    archive_path = tmp_path / "plugin.zip"
    with ZipFile(archive_path, "w") as archive:
        for file in source.rglob("*"):
            if file.is_file() and "__pycache__" not in file.parts:
                archive.write(file, file.relative_to(source).as_posix())
    root = tmp_path / "installed"
    with ZipFile(archive_path) as archive:
        assert "_vendor/opencc/LICENSE.txt" in archive.namelist()
        assert "_vendor/opencc/NOTICE.txt" in archive.namelist()
        assert "_vendor/opencc/dictionary/TSCharacters.txt" in archive.namelist()
        archive.extractall(root)
    monkeypatch.setitem(sys.modules, "opencc", None)
    manifest = SubtitleWorkspacePlugin.manifest
    registry = PluginRegistry()
    registry.validate_package(root, manifest)
    prefix = "cc_test_subtitle_private_dependency"
    try:
        registry._load_package(
            {
                "id": manifest.id,
                "install_path": str(root),
                "entrypoint": manifest.entrypoint,
            },
            runtime_name=prefix,
        )
        converter = importlib.import_module(prefix + "._vendor.opencc").OpenCC("t2s")
        assert converter.convert("繁體字幕，歡迎觀看") == "繁体字幕，欢迎观看"
        assert sys.modules["opencc"] is None
    finally:
        registry._clear_runtime_package(prefix)
