import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zipfile import ZipFile

import httpx
import pytest

from cinecircuit_plugins.subtitle_manager import automatic_download as automatic
from cinecircuit_plugins.subtitle_manager import source_download as source_downloads
from cinecircuit_plugins.subtitle_manager import subtitle_download as downloads
from cinecircuit_plugins.subtitle_manager.subtitle_files import (
    matches,
    subtitle_text,
    unpack,
)

SRT = "1\n00:00:01,000 --> 00:00:02,000\n测试字幕\n".encode()
HTTPS_PORT = 443
HTTP_PORT = 80
TARGET = {
    "media_path": "/media/Show.S01E02.mkv",
    "keyword": "Show S01 E02",
    "title": "Show",
}


def zipped(files):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for name, value in files:
            archive.writestr(name, value)
    return output.getvalue()


@pytest.mark.parametrize(
    "name", ["../bad.srt", "/bad.srt", "C:/bad.srt", "a/../../bad.srt"]
)
def test_rejects_archive_traversal(name):
    with pytest.raises(ValueError, match="非法路径"):
        unpack(zipped([(name, SRT)]), "archive.zip")


def test_zip_limits_and_excludes_non_subtitles():
    assert unpack(
        zipped([("folder/Show.S01E02.srt", SRT), ("evil.exe", b"MZ")]), "archive.zip"
    ) == [("Show.S01E02.srt", SRT)]
    with pytest.raises(ValueError, match="安全限制"):
        unpack(zipped([(f"{i}.srt", b"a") for i in range(65)]), "archive.zip")


@pytest.mark.parametrize(
    "content", [b"<html>captcha</html>", b"not a subtitle", b"\x00binary"]
)
def test_rejects_html_and_invalid_content(content):
    with pytest.raises(ValueError):
        subtitle_text(content, "srt")


@pytest.mark.parametrize(
    "filename,accepted",
    [
        ("Show.S01E02.srt", True),
        ("Show.S01E03.srt", False),
        ("Show.S02E02.srt", False),
        ("subtitle.srt", False),
        ("Show.S01E02-E03.srt", False),
    ],
)
def test_episode_matching(filename, accepted):
    assert matches(TARGET, {"title": "Show Season 1"}, filename) is accepted


def test_movie_year_and_incomplete_episode_identity():
    movie = {
        "media_path": "/movie.mkv",
        "keyword": "Movie",
        "title": "Movie",
        "year": "2020",
    }
    assert matches(movie, {"title": "Movie (2020)"}, "movie.srt")
    assert not matches(movie, {"title": "Movie (1990)"}, "movie.srt")
    assert not matches({**movie, "season": "1"}, {"title": "Movie (2020)"}, "movie.srt")


def test_final_match_accepts_trusted_alias_and_structured_identity():
    episode = {
        **TARGET,
        "title": "示例剧",
        "english_title": "Example Show",
        "aliases": ["Example Series"],
    }
    candidate = {
        "title": "Example Show S01E02",
        "season": 1,
        "episode": 2,
        "_single_payload": True,
    }
    assert matches(episode, candidate, "subtitle.srt")
    assert not matches(
        {**episode, "episode": 3, "keyword": "示例剧 S01E03"}, candidate, "subtitle.srt"
    )

    movie = {
        "media_path": "/movie.mkv",
        "keyword": "电影",
        "title": "电影",
        "english_title": "Example Movie",
        "year": 2026,
    }
    assert matches(movie, {"title": "Example Movie", "year": 2026}, "subtitle.srt")


@pytest.mark.parametrize("provider", ["ASSRT", "OpenSubtitles"])
def test_api_resolves_real_file_without_forwarding_credentials(provider, monkeypatch):
    monkeypatch.setattr(downloads, "public_url", AsyncMock())
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"token": "session-token"})
        if request.url.path.endswith("/sub/detail"):
            assert request.headers["authorization"] == "Bearer secret"
            return httpx.Response(
                200,
                json={
                    "status": 0,
                    "sub": {
                        "subs": [
                            {
                                "filelist": [
                                    {
                                        "url": "https://cdn.example/test.srt",
                                        "f": "Show.S01E02.srt",
                                    }
                                ]
                            }
                        ]
                    },
                },
            )
        if request.url.path.endswith("/download"):
            assert request.headers["api-key"] == "secret"
            assert request.headers["authorization"] == "Bearer session-token"
            assert b'"file_id":7' in request.content
            return httpx.Response(
                200,
                json={
                    "link": "https://cdn.example/test.srt",
                    "file_name": "Show.S01E02.srt",
                },
            )
        assert "authorization" not in request.headers
        assert "api-key" not in request.headers
        return httpx.Response(200, content=SRT)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await source_downloads.download_files(
                client,
                {
                    "assrt_api_key": "secret",
                    "opensubtitles_api_key": "secret",
                    "opensubtitles_username": "fixture",
                    "opensubtitles_password": "fixture-password",
                },
                {"provider": provider, "id": 12, "files": [{"file_id": 7}]},
            )

    assert asyncio.run(run()) == [("Show.S01E02.srt", SRT)]
    assert len(calls) == (3 if provider == "OpenSubtitles" else 2)


def test_html_download_link_and_captcha(monkeypatch):
    monkeypatch.setattr(downloads, "public_url", AsyncMock())

    def handler(request):
        if request.url.path == "/detail":
            return httpx.Response(
                200, text='<a class="download" href="/Show.S01E02.srt">下载</a>'
            )
        if request.url.path == "/captcha":
            return httpx.Response(200, text="<html>请完成验证码</html>")
        return httpx.Response(200, content=SRT)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await source_downloads.download_files(
                client, {}, {"provider": "SubHD", "url": "https://example.com/detail"}
            )
            with pytest.raises(ValueError, match="验证码"):
                await source_downloads.download_files(
                    client,
                    {},
                    {"provider": "SubHD", "url": "https://example.com/captcha"},
                )
            return result

    assert asyncio.run(run()) == [("Show.S01E02.srt", SRT)]


def test_download_redirect_revalidates_url(monkeypatch):
    validator = AsyncMock(side_effect=[None, ValueError("internal")])
    monkeypatch.setattr(downloads, "public_url", validator)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    302, headers={"location": "http://127.0.0.1/secret"}
                )
            )
        ) as client:
            with pytest.raises(ValueError, match="internal"):
                await downloads.fetch(client, "https://example.com/test")

    asyncio.run(run())
    assert validator.await_args_list[1].args == ("http://127.0.0.1/secret",)


def test_same_origin_redirect_preserves_api_headers(monkeypatch):
    monkeypatch.setattr(downloads, "public_url", AsyncMock())
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                301,
                headers={
                    "location": "/api/v1/subtitles?languages=zh-cn&query=inception"
                },
            )
        assert request.headers["api-key"] == "secret"
        assert request.headers["user-agent"] == "CineCircuit v1.0"
        return httpx.Response(200, json={"data": []})

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            return await downloads.fetch(
                client,
                "https://api.opensubtitles.com/api/v1/subtitles"
                "?languages=zh-CN&query=Inception",
                headers={"Api-Key": "secret", "User-Agent": "CineCircuit v1.0"},
            )

    content, final_url = asyncio.run(run())
    assert content == b'{"data":[]}'
    assert final_url.endswith("languages=zh-cn&query=inception")


def test_cross_origin_redirect_drops_api_headers(monkeypatch):
    monkeypatch.setattr(downloads, "public_url", AsyncMock())

    def handler(request):
        if request.url.host == "api.opensubtitles.com":
            return httpx.Response(
                302, headers={"location": "https://download.example/subtitle.srt"}
            )
        assert "api-key" not in request.headers
        assert "authorization" not in request.headers
        return httpx.Response(200, content=SRT)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            return await downloads.fetch(
                client,
                "https://api.opensubtitles.com/api/v1/download",
                headers={"Api-Key": "secret", "Authorization": "Bearer token"},
            )

    assert asyncio.run(run())[0] == SRT


def test_download_connects_to_validated_ip_and_preserves_http_host(monkeypatch):
    monkeypatch.setattr(
        downloads,
        "public_url",
        AsyncMock(
            return_value=(
                "https://93.184.216.34/subtitle.srt",
                "files.example",
                "files.example",
            )
        ),
    )

    def handler(request):
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "files.example"
        return httpx.Response(200, content=SRT)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await downloads.fetch(client, "https://files.example/subtitle.srt")

    content, final_url = asyncio.run(run())
    assert content == SRT
    assert final_url == "https://files.example/subtitle.srt"


def test_download_keeps_logical_host_for_central_security_transport(monkeypatch):
    monkeypatch.setattr(
        downloads,
        "public_url",
        AsyncMock(
            return_value=(
                "https://198.18.12.34/subtitle.srt",
                "files.example",
                "files.example",
            )
        ),
    )

    def handler(request):
        assert request.url.host == "files.example"
        assert request.headers["host"] == "files.example"
        return httpx.Response(200, content=SRT)

    async def run():
        transport = httpx.MockTransport(handler)
        transport._outbound_security_transport = True
        async with httpx.AsyncClient(transport=transport) as client:
            return await downloads.fetch(client, "https://files.example/subtitle.srt")

    content, final_url = asyncio.run(run())
    assert content == SRT
    assert final_url == "https://files.example/subtitle.srt"


def test_public_url_pins_dns_and_rejects_mixed_private_answers(monkeypatch):
    async def run(addresses, url="https://files.example/subtitle.srt"):
        resolver = AsyncMock(
            return_value=[(2, 1, 6, "", (address, 443)) for address in addresses]
        )
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolver)
        result = await downloads.public_url(url)
        return result, resolver

    (pinned, host, sni), resolver = asyncio.run(run(["93.184.216.34"]))
    assert pinned == "https://93.184.216.34/subtitle.srt"
    assert host == sni == "files.example"
    assert resolver.await_args.args[1] == HTTPS_PORT

    with pytest.raises(ValueError, match="内部地址"):
        asyncio.run(run(["93.184.216.34", "127.0.0.1"]))

    (_, _, _), resolver = asyncio.run(
        run(["93.184.216.34"], "http://files.example/subtitle.srt")
    )
    assert resolver.await_args.args[1] == HTTP_PORT


def test_public_url_allows_dns_fake_ip_but_rejects_literal_fake_ip(monkeypatch):
    async def resolve(url):
        resolver = AsyncMock(return_value=[(2, 1, 6, "", ("198.18.12.34", 443))])
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolver)
        return await downloads.public_url(url)

    pinned, host, sni = asyncio.run(resolve("https://subhd.tv/search/Lanterns"))

    assert pinned == "https://198.18.12.34/search/Lanterns"
    assert host == sni == "subhd.tv"
    with pytest.raises(ValueError, match="内部地址"):
        asyncio.run(resolve("https://198.18.12.34/search/Lanterns"))


def test_fetch_links_preserves_success_when_another_link_fails(monkeypatch):
    monkeypatch.setattr(downloads, "public_url", AsyncMock())

    def handler(request):
        if request.url.path.endswith("bad.srt"):
            return httpx.Response(500)
        return httpx.Response(200, content=SRT)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await downloads.fetch_links(
                client,
                [
                    ("https://files.example/bad.srt", "bad.srt"),
                    ("https://files.example/good.srt", "good.srt"),
                ],
            )

    assert asyncio.run(run()) == [("good.srt", SRT)]


@pytest.mark.parametrize("existing,expected", [(False, 1), (True, 0)])
def test_pipeline_writes_event_media_only_and_preserves_existing(
    monkeypatch, existing, expected
):
    monkeypatch.setattr(
        automatic,
        "http_client",
        lambda **kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(500))
        ),
    )
    downloader = AsyncMock(
        return_value=[
            (
                "subs.zip",
                zipped([("Show.S01E01.srt", SRT), ("Show.S01E02.zh-CN.srt", SRT)]),
            )
        ]
    )
    monkeypatch.setattr(automatic, "download_files", downloader)
    writer = AsyncMock(return_value={"subtitle_path": "/media/Show.S01E02.zh-CN.srt"})
    ctx = SimpleNamespace(
        config={},
        logger=Mock(),
        media_files=SimpleNamespace(
            subtitles=AsyncMock(
                return_value={
                    "items": [{"name": "Show.S01E02.zh-CN.srt"}] if existing else []
                }
            ),
            write_subtitle=writer,
        ),
    )
    result = asyncio.run(automatic.save_candidates(ctx, TARGET, [{"title": "Show"}]))
    assert len(result["saved"]) == expected
    assert writer.await_count == expected
    if expected:
        writer.assert_awaited_once_with(
            TARGET["media_path"],
            SRT,
            extension="srt",
            language="zh-CN",
            overwrite=False,
        )


def test_invalid_target_prevents_download(monkeypatch):
    downloader = AsyncMock()
    monkeypatch.setattr(automatic, "download_files", downloader)
    ctx = SimpleNamespace(
        media_files=SimpleNamespace(
            subtitles=AsyncMock(side_effect=FileNotFoundError())
        )
    )
    result = asyncio.run(automatic.save_candidates(ctx, TARGET, [{"title": "Show"}]))
    assert result["reason"] == "media_path_unavailable"
    downloader.assert_not_awaited()


def test_archive_language_and_format_priority():
    files = [("Show.S01E02.en.srt", SRT), ("Show.S01E02.zh-CN.srt", SRT)]
    result = automatic.prepared_files(
        automatic.PreparationContext({}, TARGET, {"title": "Show", "language": "en"}),
        files,
    )
    assert [item[1] for item in result] == ["zh-CN", "en"]


def test_failed_candidate_continues_without_leaking_error(monkeypatch):
    monkeypatch.setattr(automatic, "http_client", lambda **kwargs: httpx.AsyncClient())
    monkeypatch.setattr(
        automatic,
        "download_files",
        AsyncMock(
            side_effect=[
                ValueError("secret-download-token"),
                [("Show.S01E02.zh-CN.srt", SRT)],
            ]
        ),
    )
    ctx = SimpleNamespace(
        config={},
        logger=Mock(),
        media_files=SimpleNamespace(
            subtitles=AsyncMock(return_value={"items": []}),
            write_subtitle=AsyncMock(return_value={"bytes": len(SRT)}),
        ),
    )
    result = asyncio.run(
        automatic.save_candidates(ctx, TARGET, [{"title": "Show"}, {"title": "Show"}])
    )
    assert result["failed"] == 1
    assert len(result["saved"]) == 1
    assert "secret-download-token" not in str(result) + str(ctx.logger.mock_calls)
