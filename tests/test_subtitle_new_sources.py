import asyncio
import base64
import hashlib
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import httpx
import pytest

from cinecircuit_plugins.subtitle_manager.identity import MediaIdentity
from cinecircuit_plugins.subtitle_manager.online_sources import (
    SubDLSource, ShooterSource, XunleiSource, SearchRequest, SourceState, SourceFailure,
    OnlineSubtitleService, evaluate_candidate, SourceCandidate, DownloadResult,
)
from cinecircuit_plugins.subtitle_manager.video_hash import sample_ranges, fingerprint
from cinecircuit_plugins.subtitle_manager.preview_preparation import prepare_previews
from cinecircuit_plugins.subtitle_manager.sessions import SubtitleSessions
from cinecircuit_plugins.subtitle_manager.automatic_download import candidate_dict
from cinecircuit_plugins.subtitle_manager.subtitle_files import matches
from cinecircuit_plugins.subtitle_manager.subtitle_files import unpack, subtitle_text
from cinecircuit_plugins.subtitle_manager.subtitle_download import fetch_links
from cinecircuit_plugins.subtitle_manager.plugin import SubtitleWorkspacePlugin

VIDEO = bytes((index * 37 + index // 999) % 256 for index in range(180001))
IDENTITY = MediaIdentity(title="示例", media_type="tv", season=1, episode=2, year=2026,
                         tmdb_id="123", media_path="/media/example.mkv")
SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"


@pytest.fixture(autouse=True)
def allow_mock_urls(monkeypatch):
    async def allowed(url):
        return None
    monkeypatch.setattr("cinecircuit_plugins.subtitle_manager.subtitle_download.public_url", allowed)


def sampled(specs):
    rows = []
    for spec in specs:
        offset = len(VIDEO) * spec.get("numerator", 0) // spec.get("denominator", 1) + spec.get("offset", 0)
        rows.append({"offset": offset, "content_base64": base64.b64encode(VIDEO[offset:offset + spec['length']]).decode()})
    return {"size": len(VIDEO), "samples": rows}


def reader():
    return SimpleNamespace(read_samples=AsyncMock(side_effect=lambda path, specs: sampled(specs)))


def test_fingerprints_have_protocol_order_and_integer_offsets():
    size = len(VIDEO)
    expected = ";".join(hashlib.md5(VIDEO[offset:offset+4096]).hexdigest()
                        for offset in (4096, size * 2 // 3, size // 3, size-8192))
    assert fingerprint("shooter", sampled(sample_ranges("shooter"))) == expected
    expected = hashlib.sha1(b"".join(VIDEO[offset:offset+20480]
                                   for offset in (0, size // 3, size-20480))).hexdigest().upper()
    assert fingerprint("xunlei", sampled(sample_ranges("xunlei"))) == expected


@pytest.mark.parametrize("key", ["shooter", "xunlei"])
@pytest.mark.parametrize("extension", ["mkv", "strm"])
def test_hash_sources_download_and_preserve_evidence_through_preview(key, extension):
    identity = replace(IDENTITY, media_path=f"/media/example.{extension}")
    async def run():
        calls = []
        def respond(request):
            calls.append(request)
            if request.url.host == "download.test":
                return httpx.Response(200, content=SRT)
            if key == "shooter":
                form = parse_qs(request.content.decode())
                assert form["filehash"] == [fingerprint(key, sampled(sample_ranges(key)))]
                assert form["pathinfo"] == [f"\\media\\example.{extension}"]
                assert form["shortname"] == ["example"]
                assert request.headers["user-agent"] == "SPlayer Build 1543"
                return httpx.Response(200, json=[{"Desc": "", "Files": [{"Ext": "srt", "Link": "https://download.test/file"}]}])
            assert request.url.path.endswith(fingerprint(key, sampled(sample_ranges(key))) + ".json")
            return httpx.Response(200, json={"sublist": [{"scid": "one", "sname": "中文字幕.srt", "language": "中文", "surl": "https://download.test/file"}]})
        media = reader()
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            source = (ShooterSource if key == "shooter" else XunleiSource)(client, {}, media)
            request = SearchRequest.from_identity(identity, "示例")
            report = await source.search(request)
            assert report.state is SourceState.READY
            if key == "shooter":
                assert report.candidates[0].title == "示例 (2026).srt"
                assert report.candidates[0].download_ref[0][1] == "示例 (2026).srt"
                assert report.candidates[0].language == "zh"
            assert await source.search(replace(request, query="Another alias")) == report
            assert len(calls) == (1 if key == "shooter" else 2)
            media.read_samples.assert_awaited_once()
            matched = evaluate_candidate(report.candidates[0], request)
            assert matched.matched and matched.score == 100
            assert not evaluate_candidate(matched, replace(request, identity=replace(IDENTITY, media_path="/other.mkv"))).matched
            restored = SourceCandidate(**SubtitleSessions.candidate_payload(matched))
            downloaded = await source.download(restored)
            previews = prepare_previews({}, identity, restored, downloaded)
            assert len(previews) == 1
            target = {**identity.as_dict(), "keyword": "示例 S01E02"}
            assert matches(target, candidate_dict(restored), "subtitle.srt")
            assert not matches(target, candidate_dict(restored), "Other.S01E03.srt")
    asyncio.run(run())


@pytest.mark.parametrize("source_type", [ShooterSource, XunleiSource])
def test_hash_source_does_not_query_when_remote_sampling_fails_or_host_is_unsupported(source_type):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail("Unexpected network request"))) as client:
            media = reader()
            media.read_samples.side_effect = ValueError("STRM 视频不支持 Range")
            source = source_type(client, {}, media)
            result = await source.search(SearchRequest.from_identity(replace(IDENTITY, media_path="/media/example.strm"), "示例"))
            assert result.errors and "STRM" in result.errors[0].message
            media.read_samples.assert_awaited_once()
            result = await source_type(client, {}).search(SearchRequest.from_identity(IDENTITY, "示例"))
            assert "更新主程序" in result.errors[0].message
    asyncio.run(run())


def test_subdl_parameters_identity_cache_and_authenticated_download():
    async def run():
        calls = []
        def respond(request):
            calls.append(request)
            if request.url.host == "dl.subdl.com":
                assert "api_key" not in request.url.params
                assert "x-api-key" not in request.headers
                return httpx.Response(200, content=SRT)
            assert request.url.params["api_key"] == "secret"
            assert request.url.params["tmdb_id"] == "123"
            assert request.url.params["type"] == "tv"
            assert request.url.params["episode_number"] == "2"
            assert request.url.params["languages"] in {"ZH,ZH_BG", "EN"}
            assert request.url.params["unpack"] == "1"
            assert request.url.params["client"] == "custom_integration"
            language = "ZH" if request.url.params["languages"] == "ZH,ZH_BG" else "EN"
            return httpx.Response(200, json={"status": True, "results": [{"name": "示例", "year": 2026, "tmdb_id": 123, "sd_id": 999}],
                "subtitles": [{"release_name": "示例.S01E02", "name": f"{language}.srt", "url": f"/subtitle/{language}.srt", "season": 1, "episode": 2, "language": language}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            source = SubDLSource(client, {"subdl_api_key": "secret"})
            request = replace(SearchRequest.from_identity(IDENTITY, "示例"), language="zh-cn,zh-tw,en")
            result = await source.search(request)
            await source.search(replace(request, query="Other alias"))
            assert len(calls) == 2
            assert [candidate.language for candidate in result.candidates] == ["zh-CN", "EN"]
            ranked = await OnlineSubtitleService([source]).search(request)
            assert [candidate.language for candidate in ranked.candidates] == ["zh-CN", "EN"]
            candidate = evaluate_candidate(result.candidates[0], request)
            assert candidate.matched
            downloaded = await source.download(candidate)
            assert downloaded.files == (("ZH.srt", SRT),)
            assert "secret" not in str(candidate.as_dict())
    asyncio.run(run())


def test_fetch_links_accepts_json_restored_candidate_references():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=SRT))
        ) as client:
            files = await fetch_links(client, [["https://download.test/one.srt", "one.srt"]])
        assert files == [("one.srt", SRT)]

    asyncio.run(run())


def test_subdl_prefers_unpacked_files_and_inherits_parent_metadata():
    async def run():
        response = {"status": True, "results": [{"name": "示例", "tmdb_id": 123, "year": 2026}],
                    "subtitles": [{"release_name": "Season Pack", "season": 1, "language": "ZH",
                                   "name": "pack.zip", "url": "/subtitle/pack.zip", "unpack_files": [
                                       {"name": "Example.S01E02.srt", "url": "/subtitle/n/file", "episode": 2}
                                   ]}]}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response))) as client:
            candidate = (await SubDLSource(client, {"subdl_api_key": "secret"}).search(
                SearchRequest.from_identity(IDENTITY, "示例"))).candidates[0]
        assert candidate.download_ref == (("https://dl.subdl.com/subtitle/n/file", "Example.S01E02.srt"),)
        assert candidate.season == 1 and candidate.episode == 2 and candidate.language == "zh-CN"

    asyncio.run(run())


def test_subdl_keeps_chinese_results_when_the_secondary_language_batch_fails():
    async def run():
        def respond(request):
            if request.url.params["languages"] == "EN":
                return httpx.Response(503)
            return httpx.Response(200, json={
                "status": True,
                "results": [{"name": "示例", "tmdb_id": 123, "sd_id": 9}],
                "subtitles": [{
                    "release_name": "示例.S01E02",
                    "name": "zh.srt",
                    "url": "/subtitle/zh.srt",
                    "season": 1,
                    "episode": 2,
                    "language": "ZH",
                }],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            source = SubDLSource(client, {"subdl_api_key": "secret"})
            request = replace(
                SearchRequest.from_identity(IDENTITY, "示例"),
                language="zh-cn,zh-tw,en",
            )
            result = await source.search(request)
        assert [candidate.language for candidate in result.candidates] == ["zh-CN"]

    asyncio.run(run())


def test_subdl_exact_tmdb_match_allows_release_year_alias_in_raw_filename():
    movie_identity = MediaIdentity(
        title="Obsession", media_type="movie", year=2026,
        tmdb_id="123", media_path="/media/Obsession.2026.mkv",
    )
    candidate = SourceCandidate(
        "SubDL", "one", "Obsession", year=2026, matched=True,
        metadata={"identity_match": {"kind": "tmdb_id", "value": "123"}},
    )
    downloaded = DownloadResult("SubDL", files=(("Obsession.2025.ass", b"[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hello\n"),))
    restored = SourceCandidate(**SubtitleSessions.candidate_payload(candidate))
    previews = prepare_previews({}, movie_identity, restored, downloaded)
    assert len(previews) == 1 and previews[0].extension == "ass"


def test_subdl_mislabeled_chinese_payload_reports_the_source_problem():
    async def run():
        identity = replace(IDENTITY, media_type="movie", season=None, episode=None)
        candidate = SourceCandidate(
            "SubDL", "bad", "示例", language="zh-TW", matched=True,
            downloadable=True,
            metadata={"identity_match": {"kind": "tmdb_id", "value": "123"}},
        )
        downloaded = DownloadResult(
            "SubDL",
            files=(("bad.ass", b"[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,bad\x81"),),
        )
        with pytest.raises(ValueError, match="SubDL.*标记为中文字幕.*语言或文本编码无效"):
            await SubtitleWorkspacePlugin()._preview_from_download(
                SimpleNamespace(config={}), identity, candidate, downloaded
            )

    asyncio.run(run())


@pytest.mark.parametrize("payload", [b"", b"\xff"])
def test_shooter_no_match_sentinels_are_empty_results(payload):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=payload))) as client:
            result = await ShooterSource(client, {}, reader()).search(SearchRequest.from_identity(IDENTITY, "示例"))
        assert result.state is SourceState.READY and result.candidates == () and not result.errors

    asyncio.run(run())


def test_subdl_download_falls_back_to_the_documented_anonymous_endpoint():
    async def run():
        attempts = 0

        def respond(request):
            nonlocal attempts
            attempts += 1
            if not request.headers.get("x-api-key"):
                return httpx.Response(402)
            return httpx.Response(200, content=SRT)

        candidate = SourceCandidate(
            "SubDL", "one", "one", matched=True,
            download_ref=(("https://dl.subdl.com/subtitle/one.zip", "one.zip"),),
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            downloaded = await SubDLSource(client, {"subdl_api_key": "secret"}).download(candidate)
        assert downloaded.files == (("one.zip", SRT),)
        assert attempts == 2

    asyncio.run(run())


def test_subdl_download_reports_quota_and_reuses_successful_content():
    async def run():
        calls = 0

        def success(request):
            nonlocal calls
            calls += 1
            return httpx.Response(200, content=SRT)

        candidate = SourceCandidate(
            "SubDL", "cached", "cached", matched=True,
            download_ref=(("https://dl.subdl.com/subtitle/cache-test.srt", "cache-test.srt"),),
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(success)) as client:
            source = SubDLSource(client, {"subdl_api_key": "secret"})
            assert (await source.download(candidate)).files == (("cache-test.srt", SRT),)
            assert (await source.download(candidate)).files == (("cache-test.srt", SRT),)
        assert calls == 1

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(429))
        ) as client:
            failed = await SubDLSource(client, {"subdl_api_key": "secret"}).download(
                replace(candidate, result_id="quota", download_ref=((
                    "https://dl.subdl.com/subtitle/quota-test.srt", "quota-test.srt"
                ),))
            )
        assert failed.error and failed.error.kind.value == "quota"
        assert "配额" in failed.error.message

    asyncio.run(run())


def test_subdl_missing_key_and_failure_do_not_expose_secret():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"status": False, "error": "secret"}))) as client:
            request = SearchRequest.from_identity(IDENTITY, "示例")
            assert (await SubDLSource(client, {}).search(request)).state is SourceState.DISABLED
            with pytest.raises(SourceFailure) as exc:
                await SubDLSource(client, {"subdl_api_key": "secret"}).search(request)
            assert "secret" not in str(exc.value)
    asyncio.run(run())


def test_subdl_does_not_project_requested_identity_into_results():
    async def run():
        response = {"status": True, "results": [{"name": "Other film", "tmdb_id": 456, "year": 1999}],
                    "subtitles": [{"name": "a.zip", "url": "https://evil.test/a.zip", "release_name": "Other film"}]}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response))) as client:
            request = SearchRequest.from_identity(IDENTITY, "示例")
            candidate = (await SubDLSource(client, {"subdl_api_key": "secret"}).search(request)).candidates[0]
            assert not candidate.downloadable
            assert not evaluate_candidate(candidate, request).matched
            assert candidate.metadata["identity_match"]["value"] == "456"
    asyncio.run(run())


def test_all_sources_registered_with_existing_defaults_unchanged():
    service = SubtitleWorkspacePlugin._online_service(None, {"online_providers": ["subdl", "shooter", "xunlei"]}, reader())
    assert isinstance(service, OnlineSubtitleService)
    assert [source.name for source in service.sources] == ["SubDL", "射手影音", "迅雷看看"]


def test_xunlei_invalid_utf8_name_does_not_drop_the_entire_response():
    async def run():
        payload = b'{"sublist":[{"scid":"1","sname":"bad\xff.srt","surl":"https://download.test/one"}]}'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=payload))) as client:
            result = await XunleiSource(client, {}, reader()).search(SearchRequest.from_identity(IDENTITY, "示例"))
            assert len(result.candidates) == 1 and result.candidates[0].downloadable
    asyncio.run(run())


def test_xunlei_filters_confirmed_missing_objects_with_bounded_prefix_probe():
    async def run():
        digest = fingerprint("xunlei", sampled(sample_ranges("xunlei")))
        calls = []

        def respond(request):
            calls.append(request)
            if request.url.path.endswith(digest + ".json"):
                return httpx.Response(200, json={"sublist": [
                    {"scid": "gone", "sname": "gone.ass", "surl": "https://download.test/gone"},
                    {"scid": "live", "sname": "live.ass", "surl": "https://download.test/live"},
                ]})
            assert request.headers["range"] == "bytes=0-1023"
            if request.url.path == "/gone":
                return httpx.Response(200, content=b"<?xml version='1.0'?><Error><Code>NoSuchKey</Code></Error>")
            return httpx.Response(206, content=b"[Script Info]\n[Events]\nDialogue:")

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await XunleiSource(client, {}, reader()).search(
                SearchRequest.from_identity(IDENTITY, "示例")
            )
        assert [candidate.result_id for candidate in result.candidates] == ["live"]
        assert len(calls) == 3

    asyncio.run(run())


def test_xunlei_decodes_remote_windows_path_to_safe_display_name():
    source = XunleiSource(None, {}, reader())
    request = SearchRequest.from_identity(IDENTITY, "示例")
    candidate = source._candidate(
        {
            "sname": "C%3A%5CDownloads%5C%E8%82%96%E7%94%B3%E5%85%8B.ass",
            "surl": "https://download.test/one",
        },
        0,
        request,
        {"algorithm": "xunlei", "hash": "abc", "media_path": IDENTITY.media_path},
    )
    assert candidate.title == "肖申克.ass"
    assert candidate.download_ref[0][1] == "肖申克.ass"
    assert candidate.subtitle_format == "ass"

    truncated = source._candidate(
        {"sname": "C%3A%5CDownloads%5CMovie.2160p.DT", "surl": "https://download.test/two"},
        1,
        request,
        {"algorithm": "xunlei", "hash": "abc", "media_path": IDENTITY.media_path},
    )
    assert truncated.subtitle_format == ""


def test_missing_extension_is_recovered_from_ass_content_but_xml_is_not():
    ass = b"[events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hi\n"
    assert unpack(ass, "truncated-name") == [("truncated-name.ass", ass)]
    xml = b'<?xml version="1.0"?><Error><Code>NoSuchKey</Code></Error>'
    assert unpack(xml, "truncated-name") == [("truncated-name", xml)]
    with pytest.raises(ValueError, match="不是有效文本字幕"):
        subtitle_text(xml, "ass")


def test_subdl_timeout_is_retryable_without_leaking_request_url():
    async def run():
        def timeout(request):
            raise httpx.ReadTimeout("secret request URL", request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
            with pytest.raises(SourceFailure) as exc:
                await SubDLSource(client, {"subdl_api_key": "secret"}).search(SearchRequest.from_identity(IDENTITY, "示例"))
            assert exc.value.error.retryable
            assert "secret" not in exc.value.error.message
    asyncio.run(run())
