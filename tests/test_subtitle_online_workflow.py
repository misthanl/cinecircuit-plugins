from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
from app.core.task_failures import redact_sensitive_data
from app.modules.plugins.contracts import PluginApiRequest

from cinecircuit_plugins.subtitle_manager.online_sources import (
    DownloadResult,
    SourceCandidate,
    SourceError,
    SourceErrorKind,
    SourceSearchResult,
    SourceState,
)
from cinecircuit_plugins.subtitle_manager.plugin import SubtitleWorkspacePlugin
from cinecircuit_plugins.subtitle_manager.preview_store import SubtitlePreviewStore

SRT = "1\n00:00:01,000 --> 00:00:02,000\n测试字幕\n".encode()
BILINGUAL_SRT = (
    "1\n00:00:01,000 --> 00:00:02,000\n测试字幕\nWelcome back\n"
).encode()
EXPECTED_EPISODE = 2


def context():
    path = "/media/Example.Show.S01E02.strm"
    return SimpleNamespace(
        config={"online_providers": ["assrt"], "overwrite_existing": False},
        state=None,
        logger=Mock(),
        media_files=SimpleNamespace(
            is_catalog_media=AsyncMock(return_value=True),
            recorded_detail=AsyncMock(return_value={
                            "path": path,
                            "title": "Example.Show.S01E02",
                            "identity": {
                                "title": "Example Show",
                                "media_type": "tv",
                                "season": 1,
                                "episode": 2,
                                "tmdb_id": "42",
                            },
                        }),
            write_subtitle=AsyncMock(
                return_value={"subtitle_path": "/media/Example.Show.S01E02.zh-CN.srt"}
            ),
        ),
    )


def test_page_search_preview_and_confirm_use_one_identity_safe_chain(
    tmp_path, monkeypatch
):
    candidate = SourceCandidate(
        "ASSRT",
        "7",
        "Example Show S01E02",
        season=1,
        episode=2,
        language="zh-CN",
        subtitle_format="srt",
        downloadable=True,
        download_ref="7",
        matched=True,
        score=91,
        metadata={"raw": {"secret": "hidden"}},
    )
    restriction = SourceError(
        "字幕库",
        SourceErrorKind.CAPTCHA,
        "字幕库遇到验证码限制",
        manual_url="https://zmk.example/search",
    )
    filtered_candidate = SourceCandidate(
        "ASSRT", "8", "Example Show S01E03", downloadable=True
    )
    report = SimpleNamespace(
        candidates=(candidate,),
        errors=(restriction,),
        sources=(
            SourceSearchResult(
                "ASSRT", SourceState.READY, (candidate, filtered_candidate)
            ),
            SourceSearchResult("字幕库", SourceState.RESTRICTED, errors=(restriction,)),
        ),
    )
    service = SimpleNamespace(
        search=AsyncMock(return_value=report),
        download=AsyncMock(
            return_value=DownloadResult(
                "ASSRT",
                (
                    ("Example.Show.S01E02.zh-CN.srt", SRT),
                    ("Example.Show.S01E02.EN&CHS.srt", BILINGUAL_SRT),
                ),
            )
        ),
    )
    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.plugin.http_client",
        lambda **_kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(500))
        ),
    )
    store = SubtitlePreviewStore(tmp_path)
    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.plugin.SubtitlePreviewStore",
        lambda: store,
    )
    plugin = SubtitleWorkspacePlugin()
    plugin._online_service = Mock(return_value=service)
    ctx = context()
    media_path = "/media/Example.Show.S01E02.strm"

    searched = asyncio.run(
        plugin.handle_api(
            PluginApiRequest(
                action="online-search",
                method="POST",
                payload={"media_path": media_path, "query": "Example Show"},
            ),
            ctx,
        )
    )

    assert service.search.await_args.args[0][0].query == "Example Show S01E02"
    assert searched["identity"]["episode"] == EXPECTED_EPISODE
    assert searched["sources"][0]["candidate_count"] == 1
    assert searched["sources"][0]["raw_candidate_count"] == 2
    assert searched["sources"][1]["errors"][0]["kind"] == "captcha"
    assert searched["manual_actions"] == [
        {
            "provider": "字幕库",
            "url": "https://zmk.example/search",
            "reason": "字幕库遇到验证码限制",
        }
    ]
    public_candidate = searched["items"][0]
    assert "download_ref" not in public_candidate and "raw" not in str(public_candidate)
    assert public_candidate["candidate_handle"] != "***"
    assert redact_sensitive_data(searched)["items"][0]["candidate_handle"] == public_candidate["candidate_handle"]

    preview = asyncio.run(
        plugin.handle_api(
            PluginApiRequest(
                action="online-preview",
                method="POST",
                payload={
                    "media_path": media_path,
                    "candidate_handle": public_candidate["candidate_handle"],
                },
            ),
            ctx,
        )
    )
    assert preview["items"][0]["language"] == "zh-CN-en"
    assert preview["items"][0]["bilingual"] is True
    assert preview["items"][1]["language"] == "zh-CN"
    assert "测试字幕" in preview["items"][0]["excerpt"]
    assert preview["preview_handle"] != "***"
    assert redact_sensitive_data(preview)["preview_handle"] == preview["preview_handle"]

    confirmed = asyncio.run(
        plugin.handle_api(
            PluginApiRequest(
                action="online-confirm",
                method="POST",
                payload={
                    "media_path": media_path,
                    "preview_handle": preview["preview_handle"],
                    "selected": [0, 1],
                },
            ),
            ctx,
        )
    )
    assert len(confirmed["saved"]) == 2
    assert [call.kwargs["language"] for call in ctx.media_files.write_subtitle.await_args_list] == [
        "zh-CN-en",
        "zh-CN",
    ]


def test_explicit_season_pack_removes_episode_from_query_and_request(monkeypatch):
    service = SimpleNamespace(
        search=AsyncMock(
            return_value=SimpleNamespace(candidates=(), errors=(), sources=())
        )
    )
    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.plugin.http_client",
        lambda **_kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(500))
        ),
    )
    plugin = SubtitleWorkspacePlugin()
    plugin._online_service = Mock(return_value=service)

    asyncio.run(
        plugin.handle_api(
            PluginApiRequest(
                action="online-search",
                method="POST",
                payload={
                    "media_path": "/media/Example.Show.S01E02.strm",
                    "query": "Example Show S01E02",
                    "season_pack": True,
                },
            ),
            context(),
        )
    )

    request = service.search.await_args.args[0][0]
    assert request.query == "Example Show S01"
    assert request.season == 1
    assert request.episode is None
