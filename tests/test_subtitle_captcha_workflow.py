from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from app.modules.plugins.contracts import PluginApiRequest

from cinecircuit_plugins.subtitle_manager.online_sources import (
    OnlineSubtitleService,
    SearchRequest,
    SourceCandidate,
    SourceErrorKind,
    ZimukuSource,
)
from cinecircuit_plugins.subtitle_manager.plugin import SubtitleWorkspacePlugin
from cinecircuit_plugins.subtitle_manager.preview_store import SubtitlePreviewStore


def async_test(function):
    async def run():
        return await function()

    return lambda: asyncio.run(run())


@pytest.fixture(autouse=True)
def allow_mock_urls(monkeypatch):
    async def allowed(url):
        return None

    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.subtitle_download.public_url",
        allowed,
    )


def context():
    path = "/media/Example.Show.S01E02.strm"
    return SimpleNamespace(
        config={
            "online_providers": ["zimuku"],
            "online_use_proxy": False,
            "overwrite_existing": False,
        },
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
        ),
    )


@async_test
async def test_zimuku_search_challenge_is_serializable():
    def handler(request):
        return httpx.Response(
            200,
            text=(
                "<html>请完成验证码后继续"
                '<img class="verifyimg" '
                'src="data:image/bmp;base64,Qk1GAAAAAAAAAHsAAA=="></html>'
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = ZimukuSource(client, {"zimuku_url": "https://zmk.example"})
        report = await OnlineSubtitleService([source], retries=0).search(
            SearchRequest.from_identity(
                SimpleNamespace(
                    title="Example Show",
                    english_title="Example Show",
                    aliases=(),
                    year=2026,
                    season=1,
                    episode=2,
                    tmdb_id="",
                    imdb_id="",
                ),
                "Example Show S01E02",
            )
        )

    error = report.errors[0]
    assert error.kind == SourceErrorKind.CAPTCHA
    assert error.challenge is not None
    assert error.challenge.site == "zimuku"
    assert error.challenge.image.startswith("data:image/bmp;base64,")
    assert error.challenge.payload["param"] == "security_verify_img"
    assert isinstance(error.challenge.as_dict()["cookies"], list)


def test_page_search_returns_and_resumes_zimuku_captcha(monkeypatch):
    state = {"captcha_requests": 0, "search_requests": 0}

    def handler(request):
        if "security_verify_img" in request.url.params:
            state["captcha_requests"] += 1
            return httpx.Response(200, text="<html></html>")
        if request.url.path == "/search":
            state["search_requests"] += 1
            if state["search_requests"] == 1:
                return httpx.Response(
                    200,
                    text=(
                        "<html>请完成验证码后继续"
                        '<img class="verifyimg" '
                        'src="data:image/bmp;base64,Qk1GAAAAAAAAAHsAAA=="></html>'
                    ),
                )
            return httpx.Response(
                200,
                text=(
                    '<div class="search-result">'
                    '<a href="/detail/9">Example Show S01E02</a></div>'
                ),
            )
        return httpx.Response(404)

    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.plugin.http_client",
        lambda **_kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ),
    )
    plugin = SubtitleWorkspacePlugin()
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

    assert len(searched["captcha_challenges"]) == 1
    handle = searched["captcha_challenges"][0]["handle"]
    assert handle

    resumed = asyncio.run(
        plugin.handle_api(
            PluginApiRequest(
                action="online-captcha",
                method="POST",
                payload={"captcha_handle": handle, "code": "12345"},
            ),
            ctx,
        )
    )

    assert resumed["items"][0]["title"] == "Example Show S01E02"
    assert state["captcha_requests"] == 1
    assert state["search_requests"] == 2


def test_page_preview_submits_subhd_download_captcha(monkeypatch, tmp_path):
    state = {"down_requests": 0}
    srt = b"1\n00:00:01,000 --> 00:00:02,000\nExample\n"

    def handler(request):
        path = request.url.path
        if path == "/a/dynamic":
            return httpx.Response(
                200, text='<button data-sid="dynamic">下载</button>'
            )
        if path == "/api/sub/prepare-download":
            return httpx.Response(200, json={"success": True, "url": "/down/dynamic"})
        if path == "/down/dynamic":
            return httpx.Response(200, text="<main>download</main>")
        if path == "/api/sub/down":
            state["down_requests"] += 1
            payload = json.loads(request.content)
            if payload.get("cap") == "1234":
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "pass": True,
                        "url": "https://files.example/subtitle.srt",
                    },
                )
            return httpx.Response(
                200,
                json={
                    "success": False,
                    "pass": False,
                    "msg": "<svg viewBox='0 0 100 30'></svg>",
                },
            )
        if path == "/subtitle.srt":
            return httpx.Response(200, content=srt)
        return httpx.Response(404)

    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.plugin.http_client",
        lambda **_kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ),
    )
    store = SubtitlePreviewStore(tmp_path)
    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.plugin.SubtitlePreviewStore",
        lambda: store,
    )
    plugin = SubtitleWorkspacePlugin()
    ctx = context()
    ctx.config["online_providers"] = ["subhd"]
    media_path = "/media/Example.Show.S01E02.strm"
    candidate = SourceCandidate(
        "SubHD",
        "dynamic",
        "Example Show S01E02",
        season=1,
        episode=2,
        language="zh-CN",
        subtitle_format="srt",
        detail_url="https://subhd.example/a/dynamic",
        downloadable=True,
        download_ref="https://subhd.example/a/dynamic",
        matched=True,
        score=91,
    )
    handle = plugin._remember_candidate(ctx, media_path, candidate)

    preview = asyncio.run(
        plugin.handle_api(
            PluginApiRequest(
                action="online-preview",
                method="POST",
                payload={
                    "media_path": media_path,
                    "candidate_handle": handle,
                },
            ),
            ctx,
        )
    )

    assert preview["captcha_required"] is True
    assert preview["captcha"]["site"] == "subhd"
    assert preview["captcha"]["handle"]
    assert state["down_requests"] == 1

    resolved = asyncio.run(
        plugin.handle_api(
            PluginApiRequest(
                action="online-captcha",
                method="POST",
                payload={
                    "captcha_handle": preview["captcha"]["handle"],
                    "code": "1234",
                },
            ),
            ctx,
        )
    )

    assert "captcha_required" not in resolved
    assert resolved["preview_handle"]
    assert "00:00:01,000 --> 00:00:02,000" in resolved["items"][0]["excerpt"]
    assert "Example" in resolved["items"][0]["excerpt"]
    assert state["down_requests"] == 2
