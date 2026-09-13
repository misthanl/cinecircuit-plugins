import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from test_subtitle_download import TARGET, zipped

from cinecircuit_plugins.subtitle_manager import automatic_download as automatic
from cinecircuit_plugins.subtitle_manager.subtitle_files import (
    output_format,
    subtitle_text,
    unpack,
)
from cinecircuit_plugins.subtitle_manager.subtitle_priority import (
    bilingual,
    file_priority,
)

SUPPORTED_ARCHIVE_FORMAT_COUNT = 3


@pytest.mark.parametrize(
    "extension,text,expected",
    [
        (
            "sbv",
            "0:00:01.250,0:00:02.500\nHello\n你好",
            "00:00:01,250 --> 00:00:02,500\nHello\n你好",
        ),
        (
            "sub",
            "[INFORMATION]\n[TITLE]Test\n[END INFORMATION]\n[SUBTITLE]\n"
            "[COLF]&HFFFFFF,[STYLE]bd,[SIZE]12,[FONT]Arial\n"
            "00:00:01.25,00:00:02.50\nHello[br]你好",
            "00:00:01,250 --> 00:00:02,500\nHello\n你好",
        ),
        (
            "sub",
            "{1}{1}25\n{25}{50}Hello|你好",
            "00:00:01,000 --> 00:00:02,000\nHello\n你好",
        ),
        ("sub", "{0}{0}23.976\n{24}{48}Hello", "00:00:01,001 --> 00:00:02,002\nHello"),
    ],
)
def test_normalize_text_formats(extension, text, expected):
    assert expected in subtitle_text(text.encode(), extension)
    assert output_format(extension) == "srt"


@pytest.mark.parametrize(
    "text",
    [
        "{25}{50}Hello",
        "{1}{1}0\n{2}{3}hello",
        "{1}{1}25\n{50}{25}hello",
        "00:60:00.000,01:00:01.000\nhello",
        "not subtitles",
    ],
)
def test_reject_invalid_sub_without_guessing_frames(text):
    with pytest.raises(ValueError):
        subtitle_text(text.encode(), "sub")


def test_image_sub_is_not_treated_as_text():
    with pytest.raises(ValueError, match="图片 SUB"):
        subtitle_text(b"\x00\x00\x01\xba\x01\x02", "sub")


def test_archive_keeps_new_formats_not_idx():
    files = [(f"Show.S01E02.{ext}", b"test") for ext in ("webvtt", "sbv", "sub", "idx")]
    assert len(unpack(zipped(files), "subtitles.zip")) == SUPPORTED_ARCHIVE_FORMAT_COUNT


def test_webvtt_extension_and_automatic_sbv_use_supported_write_format():
    candidate = {"title": "Show", "language": "en"}
    for extension, text, expected in [
        ("webvtt", "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello there", "vtt"),
        ("sbv", "0:00:01.000,0:00:02.000\nHello there", "srt"),
    ]:
        prepared = automatic.prepare_file(
            automatic.PreparationContext({}, TARGET, candidate),
            f"Show.S01E02.{extension}",
            text.encode(),
        )
        assert prepared[0] == expected


def test_exact_requested_language_order_and_no_ass_header_false_positive():
    languages = ["zh-CN", "zh-TW", "zh-CN", "zh-TW", "zh", "en"]
    bodies = [
        "欢迎观看\nWelcome back",
        "歡迎觀看\nWelcome back",
        "欢迎观看",
        "歡迎觀看",
        "你好",
        "Welcome back",
    ]
    priorities = [
        file_priority({}, ("srt", lang, body.encode()))
        for lang, body in zip(languages, bodies, strict=True)
    ]
    assert [item[0] for item in priorities] == list(range(6))
    assert not bilingual(
        "[Script Info]\nTitle: English words\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,欢迎观看",
        "ass",
    )


def test_prepared_bilingual_subtitle_uses_distinct_language_suffix():
    prepared = automatic.prepare_file(
        automatic.PreparationContext(
            {}, TARGET, {"title": "Show", "language": "zh-CN"}
        ),
        "Show.S01E02.EN&CHS.srt",
        "1\n00:00:01,000 --> 00:00:02,000\n欢迎观看\nWelcome back\n".encode(),
    )

    assert prepared[1] == "zh-CN-en"


def test_later_bilingual_candidate_beats_earlier_pure_chinese(monkeypatch):
    context = SimpleNamespace(
        config={},
        logger=Mock(),
        media_files=SimpleNamespace(
            subtitles=AsyncMock(return_value={"items": []}),
            write_subtitle=AsyncMock(return_value={"ok": True}),
        ),
    )

    async def download(client, config, candidate):
        return [
            (
                "Show.S01E02.chs.srt",
                ("1\n00:00:01,000 --> 00:00:02,000\n" + candidate["body"]).encode(),
            )
        ]

    monkeypatch.setattr(automatic, "download_files", download)
    rows = [
        {"title": "Show", "language": "zh-CN", "body": text}
        for text in ["欢迎观看", "欢迎观看\nWelcome back"]
    ]
    asyncio.run(automatic.save_candidates(context, TARGET, rows))
    context.media_files.write_subtitle.assert_awaited_once()
    assert b"Welcome back" in context.media_files.write_subtitle.await_args.args[1]


@pytest.mark.parametrize(
    "body,language,expected",
    [
        ("Hello there, how are you?", "auto", "en"),
        ("欢迎观看", "auto", "zh-CN"),
        ("歡迎觀看", "auto", "zh-TW"),
        ("你好", "auto", "zh"),
        ("xyz", "auto", None),
        ("xyz", "en", "en"),
    ],
)
def test_manual_upload_detects_or_requires_explicit_language(body, language, expected):
    from app.modules.plugins.contracts import PluginApiRequest

    from cinecircuit_plugins.subtitle_manager.plugin import SubtitleWorkspacePlugin

    writer = AsyncMock(return_value={})
    context = SimpleNamespace(
        config={"default_language": "zh-CN"},
        organizer=SimpleNamespace(
            has_successful_destination=AsyncMock(return_value=True)
        ),
        media_files=SimpleNamespace(write_subtitle=writer),
    )
    request = PluginApiRequest(
        action="upload",
        method="POST",
        filename="movie.srt",
        query={"media_path": "/movie.mkv", "language": language},
        content=("1\n00:00:01,000 --> 00:00:02,000\n" + body).encode(),
    )
    if expected is None:
        with pytest.raises(ValueError, match="手动选择"):
            asyncio.run(SubtitleWorkspacePlugin().handle_api(request, context))
        writer.assert_not_awaited()
    else:
        asyncio.run(SubtitleWorkspacePlugin().handle_api(request, context))
        assert writer.await_args.kwargs["language"] == expected


def test_unsupported_sub_does_not_discard_good_archive_member():
    archive = zipped(
        [
            ("Show.S01E02.sub", b"\x00\x00\x01\xba"),
            ("Show.S01E02.sbv", b"0:00:01.000,0:00:02.000\nHello there"),
        ]
    )
    errors = []
    rows = automatic.prepared_files(
        automatic.PreparationContext({}, TARGET, {"title": "Show"}),
        [("Show.zip", archive)],
        errors=errors,
    )
    assert len(rows) == 1 and rows[0][0] == "srt"
    assert errors == ["暂不支持图片 SUB/IDX 字幕"]
