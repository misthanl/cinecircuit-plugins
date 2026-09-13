import asyncio
from functools import wraps
from types import SimpleNamespace

import httpx
import pytest

from cinecircuit_plugins.subtitle_manager.online_sources import (
    AssrtSource,
    OnlineSubtitleService,
    OpenSubtitlesSource,
    SearchRequest,
    SourceCandidate,
    SourceErrorKind,
    SourceSearchResult,
    SourceState,
    SubHDSource,
    ZimukuSource,
    evaluate_candidate,
)
from cinecircuit_plugins.subtitle_manager.online_sources.base import enrich_candidate

EXPECTED_ATTEMPTS = 2


def async_test(function):
    @wraps(function)
    def run(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))

    return run


@pytest.fixture(autouse=True)
def allow_mock_urls(monkeypatch):
    async def allowed(url):
        return None

    monkeypatch.setattr(
        "cinecircuit_plugins.subtitle_manager.subtitle_download.public_url", allowed
    )


def identity(**changes):
    values = {
        "title": "示例剧",
        "english_title": "Example Show",
        "aliases": ("示例节目",),
        "year": 2026,
        "season": 1,
        "episode": 2,
        "tmdb_id": "123",
        "imdb_id": "tt456",
    }
    values.update(changes)
    return SimpleNamespace(**values)


@async_test
async def test_assrt_search_detail_and_real_download():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/sub/search"):
            return httpx.Response(
                200,
                json={
                    "status": 0,
                    "sub": {
                        "subs": [
                            {
                                "id": 7,
                                "native_name": "Example Show S01E02",
                                "lang": {
                                    "langlist": {"langchs": True, "langeng": False}
                                },
                            }
                        ]
                    },
                },
            )
        if request.url.path.endswith("/sub/detail"):
            return httpx.Response(
                200,
                json={
                    "status": 0,
                    "sub": {
                        "subs": [
                            {
                                "lang": "chs",
                                "filelist": [
                                    {
                                        "url": "https://files.example/sub.srt",
                                        "f": "show.srt",
                                    }
                                ],
                            }
                        ]
                    },
                },
            )
        return httpx.Response(200, content=b"1\n00:00:01,000 --> 00:00:02,000\nhello")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = AssrtSource(
            client,
            {"assrt_api_key": "secret", "assrt_api_url": "https://api.example/v1"},
        )
        result = await source.search(
            SearchRequest.from_identity(identity(), "Example Show S01E02")
        )
        downloaded = await source.download(result.candidates[0])

    assert result.candidates[0].result_id == "7"
    assert result.candidates[0].language == "chs"
    assert downloaded.files[0][0] == "show.srt"
    assert [request.url.path for request in requests] == [
        "/v1/sub/search",
        "/v1/sub/search",
        "/v1/sub/detail",
        "/sub.srt",
    ]


@async_test
async def test_assrt_exposes_business_quota_error():
    def handler(request):
        return httpx.Response(200, json={"status": 1, "errmsg": "今日配额已用完"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = AssrtSource(
            client,
            {"assrt_api_key": "secret", "assrt_api_url": "https://api.example/v1"},
        )
        report = await OnlineSubtitleService([source], retries=0).search(
            SearchRequest.from_identity(identity(), "Example Show S01E02")
        )

    assert report.sources[0].state == SourceState.RESTRICTED
    assert report.errors[0].kind == SourceErrorKind.QUOTA


@async_test
async def test_assrt_combines_exact_and_title_search_with_language_and_format():
    queries = []

    def handler(request):
        query = request.url.params["q"]
        queries.append(query)
        assert request.url.params["cnt"] == "15"
        assert request.url.params["filelist"] == "1"
        rows = (
            [
                {
                    "id": 7,
                    "native_name": "肖申克的救赎 国/英",
                    "subtype": "Subrip(srt)",
                }
            ]
            if query == "肖申克的救赎 1994"
            else [
                {
                    "id": 7,
                    "native_name": "肖申克的救赎 国/英",
                    "subtype": "Subrip(srt)",
                },
                {
                    "id": 8,
                    "native_name": "肖申克的救赎 简繁英",
                    "filelist": [{"f": "subtitle.ass"}, {"f": "subtitle.srt"}],
                },
            ]
        )
        return httpx.Response(200, json={"status": 0, "sub": {"subs": rows}})

    movie = identity(
        title="肖申克的救赎",
        english_title="The Shawshank Redemption",
        aliases=(),
        year=1994,
        season=None,
        episode=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AssrtSource(
            client,
            {"assrt_api_key": "secret", "assrt_api_url": "https://api.example/v1"},
        ).search(SearchRequest.from_identity(movie, "肖申克的救赎 1994"))

    assert queries == ["肖申克的救赎 1994", "肖申克的救赎"]
    assert [item.result_id for item in result.candidates] == ["7", "8"]
    assert result.candidates[0].language == "国/英"
    assert result.candidates[0].subtitle_format == "srt"
    assert result.candidates[1].language == "简繁英"
    assert result.candidates[1].subtitle_format == "ass/srt"


@async_test
async def test_assrt_infers_language_from_search_file_names_when_lang_is_omitted():
    def handler(request):
        return httpx.Response(200, json={
            "status": 0,
            "sub": {"subs": [{
                "id": 9,
                "native_name": "The Shawshank Redemption 1994",
                "filelist": [{"f": "The.Shawshank.Redemption.1994.zh-TW.ass"}],
            }]},
        })

    movie = identity(
        title="肖申克的救赎", english_title="The Shawshank Redemption",
        aliases=(), year=1994, season=None, episode=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AssrtSource(
            client, {"assrt_api_key": "secret", "assrt_api_url": "https://api.example/v1"},
        ).search(SearchRequest.from_identity(movie, "The Shawshank Redemption 1994"))

    assert result.candidates[0].language == "zh-TW"


@async_test
async def test_opensubtitles_prefers_tmdb_and_downloads_by_file_id():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"token": "session-token"})
        if request.url.path.endswith("/subtitles"):
            assert request.url.params["tmdb_id"] == "123"
            assert request.url.params["season_number"] == "1"
            assert request.url.params["episode_number"] == "2"
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "result",
                            "attributes": {
                                "release": "Example Show S01E02",
                                "language": "zh",
                                "feature_details": {
                                    "title": "Example Show",
                                    "season_number": 1,
                                    "episode_number": 2,
                                    "year": 2026,
                                },
                                "files": [{"file_id": 99, "file_name": "episode.srt"}],
                            },
                        }
                    ]
                },
            )
        if request.url.path.endswith("/download"):
            assert request.headers["Authorization"] == "Bearer session-token"
            assert request.read()
            return httpx.Response(
                200,
                json={
                    "link": "https://files.example/episode.srt",
                    "file_name": "episode.srt",
                },
            )
        return httpx.Response(200, content=b"subtitle")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = OpenSubtitlesSource(
            client,
            {
                "opensubtitles_api_key": "secret",
                "opensubtitles_api_url": "https://os.example/api/v1",
                "opensubtitles_username": "fixture",
                "opensubtitles_password": "fixture-password",
            },
        )
        result = await source.search(
            SearchRequest.from_identity(
                identity(), "Example Show S01E02", language="zh"
            )
        )
        downloaded = await source.download(result.candidates[0])

    assert (
        len(
            [request for request in requests if request.url.path.endswith("/subtitles")]
        )
        == 1
    )
    assert result.candidates[0].metadata["identity_match"] == {
        "kind": "tmdb_id",
        "value": "123",
    }
    assert downloaded.files == (("episode.srt", b"subtitle"),)


@async_test
async def test_subhd_uses_search_work_detail_hierarchy_not_unrelated_anchors():
    requests = []

    def handler(request):
        requests.append(str(request.url))
        path = request.url.path
        if path.startswith("/search/"):
            return httpx.Response(
                200,
                text=(
                    '<nav><a href="/wrong">Example Show S01E02</a></nav>'
                    '<div class="search-result">'
                    '<a href="/d/work">Example Show</a></div>'
                ),
            )
        if path == "/d/work":
            return httpx.Response(
                200,
                text=(
                    '<div class="subtitle-list">'
                    '<a href="/a/subtitle">Example Show S01E02 简体字幕</a>'
                    '<a href="https://other.example/a/wrong">外站字幕</a></div>'
                ),
            )
        if path == "/a/subtitle":
            return httpx.Response(
                200,
                text='<a class="download" href="https://files.example/show.zip">下载</a>',
            )
        return httpx.Response(200, content=b"archive")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = SubHDSource(client, {"subhd_url": "https://subhd.example"})
        found = await source.search(
            SearchRequest.from_identity(identity(), "Example Show S01E02")
        )
        downloaded = await source.download(found.candidates[0])

    assert len(found.candidates) == 1
    assert found.candidates[0].detail_url.endswith("/a/subtitle")
    assert evaluate_candidate(
        found.candidates[0],
        SearchRequest.from_identity(identity(), "Example Show S01E02"),
    ).matched
    assert downloaded.files == (("show.zip", b"archive"),)
    assert not any("other.example" in url for url in requests)


@async_test
async def test_zimuku_captcha_is_visible_and_has_manual_fallback():
    def handler(request):
        return httpx.Response(200, text="<html>请完成验证码后继续</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = ZimukuSource(client, {"zimuku_url": "https://zmk.example"})
        report = await OnlineSubtitleService([source], retries=3).search(
            SearchRequest.from_identity(identity(), "Example Show S01E02")
        )

    assert report.sources[0].attempts == 1
    assert report.sources[0].state == SourceState.RESTRICTED
    assert report.errors[0].kind == SourceErrorKind.CAPTCHA
    assert report.errors[0].manual_url.startswith("https://")


@async_test
async def test_subhd_cloudflare_asset_on_result_page_is_not_a_captcha():
    def handler(request):
        if request.url.path.startswith("/search/"):
            return httpx.Response(
                200,
                text=(
                    '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
                    '<a href="/d/36225837">Lanterns S01E04</a>'
                ),
            )
        return httpx.Response(
            200,
            text='<main>Lanterns S01E04 subtitle details</main>',
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await SubHDSource(
            client, {"subhd_url": "https://subhd.example"}
        ).search(SearchRequest.from_identity(identity(), "Lanterns S01E04"))

    assert result.state == SourceState.READY
    assert len(result.candidates) == 1
    assert result.candidates[0].detail_url == "https://subhd.example/d/36225837"


@async_test
async def test_subhd_current_row_and_view_text_markup_yields_subtitles():
    def handler(request):
        if request.url.path.startswith("/search/"):
            return httpx.Response(
                200,
                text=(
                    '<div class="row"><div class="col-2">'
                    '<a href="/d/36225837"><img src="poster.jpg"></a></div>'
                    '<div>绿灯军团 Lanterns (2026)</div></div>'
                ),
            )
        if request.url.path == "/d/36225837":
            return httpx.Response(
                200,
                text=(
                    '<div class="px-3 py-2">'
                    '<div class="view-text"><a class="link-dark" href="/a/s6Anw8">'
                    "Lanterns S01E04 HBO MAX 官方简中</a></div>"
                    "<span>官方字幕</span><span>双语</span><span>简体</span><span>ASS</span>"
                    "</div>"
                    '<div class="px-3 py-2">'
                    '<div class="view-text"><a class="link-dark" href="/a/older">'
                    "Lanterns S01E03 HBO MAX 官方简中</a></div>"
                    "<span>官方字幕</span><span>繁体</span><span>SRT</span>"
                    "</div>"
                ),
            )
        return httpx.Response(200, text='<a class="download" href="/download/sub.zip">下载</a>')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        request = SearchRequest.from_identity(
            identity(title="绿灯军团", english_title="Lanterns", episode=4),
            "Lanterns S01E04",
        )
        result = await SubHDSource(
            client, {"subhd_url": "https://subhd.example"}
        ).search(request)

    assert result.state == SourceState.READY
    assert len(result.candidates) == 2
    assert result.candidates[0].detail_url == "https://subhd.example/a/s6Anw8"
    assert result.candidates[0].title == "Lanterns S01E04 HBO MAX 官方简中"
    assert result.candidates[0].tags == ("官方字幕", "双语", "简体", "ASS")
    assert evaluate_candidate(result.candidates[0], request).matched is True
    assert evaluate_candidate(result.candidates[1], request).matched is False


@async_test
async def test_subhd_search_cards_keep_language_and_format_labels():
    def handler(request):
        return httpx.Response(
            200,
            text=(
                '<div class="bg-white shadow-sm rounded-3 mb-4"><div class="view-text">'
                '<a href="/a/current">Lanterns S01E04 WEB-DL</a></div>'
                '<div class="text-truncate"><span>官方字幕</span><span>双语</span>'
                '<span>简体</span><span>英语</span><span>ASS</span></div></div>'
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await OnlineSubtitleService(
            [SubHDSource(client, {"subhd_url": "https://subhd.example"})],
            retries=0,
        ).search(
            SearchRequest.from_identity(
                identity(title="绿灯军团", english_title="Lanterns", episode=4),
                "Lanterns S01E04",
            )
        )

    assert len(report.candidates) == 1
    assert report.candidates[0].language == "zh-CN/en"
    assert report.candidates[0].subtitle_format == "ass"


@async_test
async def test_subhd_current_dynamic_download_flow_without_captcha():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/a/dynamic":
            return httpx.Response(
                200,
                text='<button class="subtitle-prepare-download" data-sid="dynamic">下载</button>',
            )
        if request.url.path == "/api/sub/prepare-download":
            assert request.method == "POST"
            assert request.headers["X-Requested-With"] == "XMLHttpRequest"
            assert request.headers["Origin"] == "https://subhd.example"
            assert request.read() == b'{"sid":"dynamic"}'
            return httpx.Response(200, json={"success": True, "url": "/down/dynamic"})
        if request.url.path == "/down/dynamic":
            return httpx.Response(200, text="<main>download</main>")
        if request.url.path == "/api/sub/down":
            assert request.headers["Referer"] == "https://subhd.example/down/dynamic"
            assert request.read() == b'{"sid":"dynamic","cap":""}'
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "pass": True,
                    "url": "https://files.example/subtitle.zip",
                },
            )
        return httpx.Response(200, content=b"archive")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        downloaded = await SubHDSource(
            client, {"subhd_url": "https://subhd.example"}
        ).download(
            SourceCandidate(
                "SubHD",
                "dynamic",
                "Example Show S01E02",
                detail_url="https://subhd.example/a/dynamic",
                matched=True,
            )
        )

    assert downloaded.files == (("subtitle.zip", b"archive"),)
    assert [request.url.path for request in requests] == [
        "/a/dynamic",
        "/api/sub/prepare-download",
        "/down/dynamic",
        "/api/sub/down",
        "/subtitle.zip",
    ]


def test_download_match_allows_release_name_without_year_after_identity_match():
    from cinecircuit_plugins.subtitle_manager.subtitle_files import matches

    assert matches(
        {
            "title": "绿灯军团",
            "english_title": "Lanterns",
            "year": 2026,
            "season": 1,
            "episode": 4,
            "keyword": "绿灯军团 S01E04",
            "media_path": "/media/绿灯军团.2026.S01E04.strm",
        },
        {
            "title": "Lanterns S01E04 The Weenie",
            "year": None,
            "season": 1,
            "episode": 4,
            "matched": True,
        },
        "Lanterns.S01E04.The.Weenie.CHS.srt",
    )


@async_test
async def test_subhd_dynamic_download_reports_actual_captcha_challenge():
    def handler(request):
        if request.url.path == "/a/dynamic":
            return httpx.Response(200, text='<button data-sid="dynamic">下载</button>')
        if request.url.path == "/api/sub/prepare-download":
            return httpx.Response(200, json={"success": True, "url": "/down/dynamic"})
        if request.url.path == "/down/dynamic":
            return httpx.Response(200, text="<main>download</main>")
        return httpx.Response(
            200,
            json={"success": False, "pass": False, "msg": "<svg></svg>"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = SubHDSource(client, {"subhd_url": "https://subhd.example"})
        with pytest.raises(Exception) as captured:
            await source.download(
                SourceCandidate(
                    "SubHD",
                    "dynamic",
                    "Example Show S01E02",
                    detail_url="https://subhd.example/a/dynamic",
                    matched=True,
                )
            )

    assert captured.value.error.kind == SourceErrorKind.CAPTCHA
    assert captured.value.error.manual_url == "https://subhd.example/a/dynamic"
    challenge = captured.value.error.challenge
    assert challenge is not None
    assert challenge.site == "subhd"
    assert challenge.context["sid"] == "dynamic"
    assert challenge.image.startswith("data:image/svg+xml;base64,")


@async_test
async def test_zimuku_downloads_only_from_explicit_detail_download_control():
    def handler(request):
        if request.url.path == "/search":
            return httpx.Response(
                200,
                text=(
                    '<div class="search-result">'
                    '<a href="/detail/9">Example Show S01E02</a></div>'
                ),
            )
        if request.url.path == "/detail/9":
            return httpx.Response(
                200,
                text=(
                    '<nav><a href="https://evil.example/not-a-download">忽略</a></nav>'
                    '<a class="down1" href="https://files.example/episode.ass">'
                    "下载字幕</a>"
                ),
            )
        return httpx.Response(200, content=b"[Script Info]")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = ZimukuSource(client, {"zimuku_url": "https://zmk.example"})
        found = await source.search(
            SearchRequest.from_identity(identity(), "Example Show S01E02")
        )
        downloaded = await source.download(found.candidates[0])

    assert downloaded.files == (("episode.ass", b"[Script Info]"),)


def test_candidate_public_dict_never_exposes_internal_metadata_or_download_reference():
    candidate = SourceCandidate(
        "ASSRT",
        "1",
        "Example Show S01E02",
        download_ref="https://signed.example/private-token",
        metadata={"raw": {"secret": "token"}},
    )

    exposed = candidate.as_dict()
    assert "metadata" not in exposed and "raw" not in exposed
    assert "download_ref" not in exposed
    assert "private-token" not in str(exposed)
    assert (
        SourceCandidate(
            "ASSRT", "2", "Unsafe", detail_url="javascript:alert(1)"
        ).as_dict()["url"]
        == ""
    )


def test_candidate_enrichment_infers_missing_language_and_format_from_available_labels():
    bilingual = enrich_candidate(
        SourceCandidate(
            "SubHD",
            "inferred",
            "Example.Show.S01E02.简英双语.ASS",
            tags=("双语", "简体"),
        )
    )
    from_file = enrich_candidate(
        SourceCandidate(
            "OpenSubtitles",
            "file",
            "Example Show S01E02",
            download_ref=({"file_name": "Example.Show.S01E02.eng.srt"},),
        )
    )
    authoritative = enrich_candidate(
        SourceCandidate(
            "ASSRT",
            "explicit",
            "Example.Show.chs.srt",
            language="ja",
            subtitle_format="vtt",
        )
    )

    assert (bilingual.language, bilingual.subtitle_format) == ("zh-CN/en", "ass")
    assert (from_file.language, from_file.subtitle_format) == ("en", "srt")
    assert (authoritative.language, authoritative.subtitle_format) == ("ja", "vtt")


def test_opensubtitles_format_rejects_release_suffixes_and_uses_requested_srt():
    from cinecircuit_plugins.subtitle_manager.online_sources.opensubtitles import (
        _subtitle_format,
    )

    assert _subtitle_format(({"file_id": 1, "file_name": "Movie.2026.EN"},)) == "srt"
    assert (
        _subtitle_format(({"file_id": 2, "file_name": "Movie.264-KYOGO-HI"},))
        == "srt"
    )
    assert _subtitle_format(({"file_id": 3, "file_name": "Movie.zh-CN.ass"},)) == "ass"


def test_matcher_rejects_wrong_or_missing_episode_and_movie_year_conflict():
    episode_request = SearchRequest.from_identity(identity(), "Example Show S01E02")
    wrong = evaluate_candidate(
        SourceCandidate("ASSRT", "1", "Example Show S01E03"), episode_request
    )
    bare = evaluate_candidate(
        SourceCandidate("ASSRT", "2", "Example Show"), episode_request
    )
    movie = identity(
        season=None, episode=None, title="Example Movie", english_title="Example Movie"
    )
    wrong_year = evaluate_candidate(
        SourceCandidate("SubHD", "3", "Example Movie 2024"),
        SearchRequest.from_identity(movie, "Example Movie 2026"),
    )
    structured_conflict = evaluate_candidate(
        SourceCandidate("ASSRT", "4", "Example Show S01E03", season=1, episode=2),
        episode_request,
    )
    short_title = identity(
        title="It",
        english_title="It",
        aliases=(),
        season=None,
        episode=None,
        year=2017,
    )
    substring = evaluate_candidate(
        SourceCandidate("SubHD", "5", "Titanic 2017"),
        SearchRequest.from_identity(short_title, "It 2017"),
    )

    assert not wrong.matched and "季集不匹配" in wrong.match_reason
    assert not bare.matched and "未标明季集" in bare.match_reason
    assert not wrong_year.matched and "年份冲突" in wrong_year.match_reason
    assert (
        not structured_conflict.matched
        and "结构化季集" in structured_conflict.match_reason
    )
    assert not substring.matched and "片名" in substring.match_reason


def test_matcher_keeps_year_conflict_only_when_opensubtitles_used_exact_id():
    movie = identity(
        season=None, episode=None, title="Obsession", english_title="Obsession"
    )
    request = SearchRequest.from_identity(movie, "Obsession 2026")
    exact = evaluate_candidate(
        SourceCandidate(
            "OpenSubtitles",
            "exact",
            "Obsession 2025",
            year=2025,
            metadata={
                "identity_match": {"kind": "tmdb_id", "value": "123"}
            },
        ),
        request,
    )
    fallback = evaluate_candidate(
        SourceCandidate("OpenSubtitles", "query", "Obsession 2025", year=2025),
        request,
    )

    assert exact.matched
    assert "精确 ID 匹配" in exact.match_reason
    assert not fallback.matched
    assert "年份冲突" in fallback.match_reason


@async_test
async def test_service_runs_sources_concurrently_keeps_timeout_and_deduplicates():
    class Source:
        def __init__(self, name, delay):
            self.name = name
            self.delay = delay

        async def status(self):
            return SourceState.READY

        async def search(self, request):
            await asyncio.sleep(self.delay)
            candidate = SourceCandidate(
                self.name,
                self.name,
                "Example Show S01E02",
                language="zh",
                subtitle_format="ass",
                downloadable=True,
            )
            return SourceSearchResult(self.name, SourceState.READY, (candidate,))

        async def details(self, candidate):
            return candidate

        async def download(self, candidate):
            raise AssertionError

    report = await OnlineSubtitleService(
        [Source("ASSRT", 0.001), Source("slow", 0.3)], timeout=0.1, retries=0
    ).search(
        SearchRequest.from_identity(identity(), "Example Show S01E02", language="zh")
    )

    assert len(report.candidates) == 1
    assert report.candidates[0].provider == "ASSRT"
    assert any(
        error.kind == SourceErrorKind.TIMEOUT and error.provider == "slow"
        for error in report.errors
    )


@async_test
async def test_service_keeps_distinct_same_title_results_from_one_source():
    class Source:
        name = "SubHD"

        async def status(self):
            return SourceState.READY

        async def search(self, request):
            return SourceSearchResult(
                self.name,
                SourceState.READY,
                (
                    SourceCandidate(self.name, "first", "Example Show S01E02"),
                    SourceCandidate(self.name, "second", "Example Show S01E02"),
                ),
            )

        async def details(self, candidate):
            return candidate

        async def download(self, candidate):
            raise AssertionError

    report = await OnlineSubtitleService([Source()], retries=0).search(
        SearchRequest.from_identity(identity(), "Example Show S01E02")
    )

    assert [item.result_id for item in report.candidates] == ["first", "second"]


@async_test
async def test_service_refuses_unmatched_download():
    report = await OnlineSubtitleService([]).download(
        SourceCandidate("ASSRT", "1", "unknown")
    )
    assert report.error and report.error.kind == SourceErrorKind.DOWNLOAD


@async_test
async def test_service_keeps_earlier_alias_results_when_source_budget_expires():
    class Source:
        name = "ASSRT"

        async def status(self):
            return SourceState.READY

        async def search(self, request):
            if request.query == "first":
                return SourceSearchResult(
                    self.name,
                    SourceState.READY,
                    (SourceCandidate(self.name, "1", "Example Show S01E02"),),
                )
            await asyncio.sleep(1)
            raise AssertionError("cancelled by total source budget")

        async def details(self, candidate):
            return candidate

        async def download(self, candidate):
            raise AssertionError

    requests = (
        SearchRequest.from_identity(identity(), "first"),
        SearchRequest.from_identity(identity(), "second"),
    )
    report = await OnlineSubtitleService([Source()], timeout=0.03, retries=0).search(
        requests
    )

    assert [candidate.result_id for candidate in report.candidates] == ["1"]
    assert report.sources[0].attempts == EXPECTED_ATTEMPTS
    assert any(error.kind is SourceErrorKind.TIMEOUT for error in report.errors)


@async_test
async def test_opensubtitles_uses_validated_login_base_url():
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.path.endswith("/login"):
            return httpx.Response(
                200,
                json={
                    "token": "session-token",
                    "base_url": "https://vip-api.opensubtitles.com",
                },
            )
        if request.url.path.endswith("/subtitles"):
            return httpx.Response(200, json={"data": []})
        raise AssertionError(request.url)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = OpenSubtitlesSource(
            client,
            {
                "opensubtitles_api_key": "secret",
                "opensubtitles_api_url": "https://api.opensubtitles.com/api/v1",
                "opensubtitles_username": "fixture",
                "opensubtitles_password": "fixture-password",
            },
        )
        await source.search(
            SearchRequest.from_identity(identity(), "Example Show S01E02")
        )

    assert hosts[0] == "api.opensubtitles.com"
    assert hosts[1:] == ["vip-api.opensubtitles.com"] * 3


@async_test
async def test_subhd_preserves_results_when_one_work_page_fails():
    def handler(request):
        if request.url.path.startswith("/search/"):
            return httpx.Response(
                200,
                text=(
                    '<div class="search-result"><a href="/d/good">Good</a></div>'
                    '<div class="search-result"><a href="/d/bad">Bad</a></div>'
                ),
            )
        if request.url.path == "/d/good":
            return httpx.Response(
                200,
                text=(
                    '<div class="subtitle-list">'
                    '<a href="/a/good">Example Show S01E02</a></div>'
                ),
            )
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await SubHDSource(
            client, {"subhd_url": "https://subhd.example"}
        ).search(SearchRequest.from_identity(identity(), "Example Show S01E02"))

    assert [candidate.result_id for candidate in result.candidates] == ["good"]
    assert result.state is SourceState.READY
    assert result.errors and result.errors[0].kind is SourceErrorKind.NETWORK


@async_test
async def test_subhd_detail_preserves_direct_link_when_nested_page_fails():
    def handler(request):
        if request.url.path == "/a/root":
            return httpx.Response(
                200,
                text=(
                    '<a class="download" href="https://files.example/good.srt">下载</a>'
                    '<div class="subtitle-list"><a href="/a/stale">旧详情</a></div>'
                ),
            )
        if request.url.path == "/a/stale":
            return httpx.Response(500)
        return httpx.Response(200, content=b"subtitle")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = SubHDSource(client, {"subhd_url": "https://subhd.example"})
        downloaded = await source.download(
            SourceCandidate(
                "SubHD",
                "root",
                "Example Show S01E02",
                detail_url="https://subhd.example/a/root",
            )
        )

    assert downloaded.files == (("good.srt", b"subtitle"),)


@async_test
async def test_page_sources_do_not_advertise_unsupported_archives():
    def handler(request):
        if request.url.path == "/search":
            return httpx.Response(
                200,
                text=(
                    '<div class="search-result">'
                    '<a href="/detail/9">Example Show S01E02</a></div>'
                ),
            )
        return httpx.Response(
            200,
            text='<a class="down1" href="https://files.example/episode.rar">下载</a>',
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = ZimukuSource(client, {"zimuku_url": "https://zmk.example"})
        result = await source.search(
            SearchRequest.from_identity(identity(), "Example Show S01E02")
        )
        downloaded = await source.download(result.candidates[0])

    assert downloaded.error
    assert not downloaded.files


@pytest.mark.parametrize("plan", [
    {"keyword": "Example Show", "identity": {"season": 1, "episode": 2}},
    SimpleNamespace(keyword="Example Show", identity={"season": 1, "episode": 2}),
])
def test_public_plan_adapter_keeps_mapping_and_object_compatibility(plan):
    request = OnlineSubtitleService.request_from_plan(plan, language="en")
    assert (request.query, request.season, request.episode, request.language) == ("Example Show", 1, 2, "en")
    assert OnlineSubtitleService.request_from_plan(request) is request


def test_public_candidate_match_builder_preserves_source_and_returns_new_value():
    candidate = SourceCandidate("synthetic", "one", "Example")
    checked = candidate.with_match(score=98, reason="identity", matched=True)
    assert checked is not candidate
    assert not candidate.matched and candidate.score == 0
    assert (checked.provider, checked.result_id, checked.score, checked.match_reason, checked.matched) == (
        "synthetic", "one", 98, "identity", True
    )
