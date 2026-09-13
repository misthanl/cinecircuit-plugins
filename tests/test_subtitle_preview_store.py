from __future__ import annotations

import pytest

from cinecircuit_plugins.subtitle_manager.preview_store import (
    PreviewFile,
    SubtitlePreviewStore,
)

EXPECTED_PREVIEW_ENTRIES = 2


def file(name: str = "Show.S01E02.srt") -> PreviewFile:
    return PreviewFile(
        extension="srt",
        language="zh-CN",
        content=b"1\n00:00:01,000 --> 00:00:02,000\nhello\n",
        source_name=name,
        details={"provider": "ASSRT"},
    )


def test_preview_is_bounded_to_media_and_consumed_once(tmp_path) -> None:
    store = SubtitlePreviewStore(tmp_path)
    created = store.create("/media/Show.S01E02.strm", [file()])
    assert created["items"][0] == {
        "index": 0,
        "name": "Show.S01E02.srt",
        "language": "zh-CN",
        "format": "SRT",
        "bytes": 38,
        "excerpt": "1\n00:00:01,000 --> 00:00:02,000\nhello",
        "provider": "ASSRT",
    }
    with pytest.raises(ValueError, match="当前媒体不匹配"):
        store.consume(created["preview_token"], "/media/Other.mkv")
    with pytest.raises(ValueError, match="已过期"):
        store.consume(created["preview_token"], "/media/Show.S01E02.strm")


def test_preview_selection_and_size_limit(tmp_path) -> None:
    store = SubtitlePreviewStore(tmp_path, max_total_bytes=1024)
    created = store.create("/media/movie.mkv", [file("one.srt"), file("two.srt")])
    chosen = store.consume(created["preview_token"], "/media/movie.mkv", [1])
    assert [item.source_name for item in chosen] == ["two.srt"]
    with pytest.raises(ValueError, match="大小限制"):
        store.create(
            "/media/movie.mkv",
            [PreviewFile("srt", "zh-CN", b"x" * 1025, "large.srt", {})],
        )


def test_preview_details_cannot_override_fixed_public_fields() -> None:
    preview = PreviewFile(
        extension="srt",
        language="zh-CN",
        content=b"real content",
        source_name="real.srt",
        details={
            "provider": "ASSRT",
            "index": 999,
            "name": "spoof.srt",
            "bytes": 999999,
            "excerpt": "spoof",
        },
    ).public(0)

    assert preview["provider"] == "ASSRT"
    assert preview["index"] == 0
    assert preview["name"] == "real.srt"
    assert preview["bytes"] == len(b"real content")
    assert preview["excerpt"] == "real content"


def test_preview_prune_keeps_exact_limit_and_makes_room_for_new_entry(tmp_path) -> None:
    store = SubtitlePreviewStore(tmp_path, max_entries=2)
    first = store.create("/media/one.mkv", [file("one.srt")])
    second = store.create("/media/two.mkv", [file("two.srt")])
    store._prune()
    assert (
        len([path for path in tmp_path.iterdir() if not path.name.startswith(".")])
        == EXPECTED_PREVIEW_ENTRIES
    )

    third = store.create("/media/three.mkv", [file("three.srt")])
    assert (
        len([path for path in tmp_path.iterdir() if not path.name.startswith(".")])
        == EXPECTED_PREVIEW_ENTRIES
    )
    assert not (tmp_path / first["preview_token"]).exists()
    assert (tmp_path / second["preview_token"]).exists()
    assert (tmp_path / third["preview_token"]).exists()
