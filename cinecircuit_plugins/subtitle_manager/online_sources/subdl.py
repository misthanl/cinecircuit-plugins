"""SubDL official v1 search and public subtitle downloads."""

import asyncio
from collections import OrderedDict

from urllib.parse import urljoin, urlsplit

from ..subtitle_download import api_json, fetch
from .api_errors import api_failure
from .base import (
    DownloadResult, SourceCandidate, SourceError, SourceErrorKind, SourceFailure,
    SourceSearchResult, SourceState, http_failure,
)
from ..video_hash import identity_value


_DOWNLOAD_CACHE_LIMIT = 16 * 1024 * 1024


def _remember_download(cache, key, files):
    value = tuple(files)
    cache[key] = value
    cache.move_to_end(key)
    while cache and (len(cache) > 256 or sum(
        len(content) for items in cache.values() for _, content in items
    ) > _DOWNLOAD_CACHE_LIMIT):
        cache.popitem(last=False)
    return value


def _number(value):
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _languages(language):
    aliases = {"zh": "ZH,ZH_BG", "zh-cn": "ZH", "zh-tw": "ZH_BG", "zh-ca": "ZH", "ze": "ZH,ZH_BG",
               "en": "EN", "ja": "JA", "ko": "KO"}
    mapped = (aliases.get(item.lower(), item.upper()) for item in language.split(",") if item)
    return ",".join(dict.fromkeys(code for item in mapped for code in item.split(",")))


def _language_batches(value):
    codes = [item for item in str(value or "").split(",") if item]
    chinese = [item for item in codes if item in {"ZH", "ZH_BG"}]
    other = [item for item in codes if item not in {"ZH", "ZH_BG"}]
    batches = [group for group in (chinese, other) if group]
    return [",".join(group) for group in batches] or [""]


class SubDLSource:
    name = "SubDL"

    def __init__(self, client, config):
        self.client = client
        self.key = str(config.get("subdl_api_key") or "").strip()
        self.base = str(config.get("subdl_api_url") or "https://api.subdl.com/api/v1").rstrip("/")
        self._cache = {}
        self._downloads = OrderedDict()

    async def status(self):
        return SourceState.READY if self.key else SourceState.DISABLED

    def _params(self, request):
        params = {
            "api_key": self.key,
            "subs_per_page": 30,
            "releases": 1,
            # Prefer the raw files kept inside ZIP/full-season uploads.  Besides
            # making episode matching precise, these links remain usable when
            # the anonymous archive endpoint has exhausted its per-IP quota.
            "unpack": 1,
            "client": "custom_integration",
        }
        media_type = identity_value(request.identity, "media_type")
        if media_type in {"movie", "tv"}:
            params["type"] = media_type
        if request.tmdb_id:
            params["tmdb_id"] = request.tmdb_id
        elif request.imdb_id:
            params["imdb_id"] = request.imdb_id
        else:
            params["film_name"] = request.query
            if request.year:
                params["year"] = request.year
        for field in ("season", "episode"):
            value = getattr(request, field)
            if value is not None:
                params[field + "_number"] = value
                params["type"] = "tv"
        if request.language:
            params["languages"] = _languages(request.language)
        return params

    async def search(self, request):
        if not self.key:
            return SourceSearchResult(self.name, SourceState.DISABLED, errors=(SourceError(
                self.name, SourceErrorKind.CONFIGURATION, "SubDL API Key 未配置"
            ),))
        params = self._params(request)
        batches = _language_batches(params.get("languages"))
        results = await asyncio.gather(
            *(self._cached_payload({**params, "languages": batch}) for batch in batches),
            return_exceptions=True,
        )
        payloads = [item for item in results if isinstance(item, dict)]
        if not payloads:
            raise next(item for item in results if isinstance(item, Exception))
        candidates = []
        seen = set()
        for data in payloads:
            works = data.get("results") or []
            # The API documents that subtitles belong to the FIRST work only.
            work = works[0] if works else {}
            for row in data.get("subtitles", []):
                for candidate in self._candidates(row, work):
                    identity = (candidate.result_id, candidate.download_ref)
                    if identity not in seen:
                        seen.add(identity)
                        candidates.append(candidate)
        return SourceSearchResult(self.name, SourceState.READY, tuple(candidates))

    async def _cached_payload(self, params):
        cache_key = tuple(
            sorted((key, str(value)) for key, value in params.items() if key != "api_key")
        )
        if cache_key not in self._cache:
            self._cache[cache_key] = await self._payload(params)
        return self._cache[cache_key]

    async def _payload(self, params):
        try:
            data = await api_json(self.client, self.base + "/subtitles", params=params)
        except Exception as exc:
            # Never propagate a response body or URL which could echo the secret.
            raise api_failure(self.name, exc, "https://subdl.com") from None
        if data.get("status") is not True:
            raise SourceFailure(SourceError(
                self.name, SourceErrorKind.PROTOCOL, "SubDL 查询失败，请检查 API Key 或配额",
                manual_url="https://subdl.com/panel/api",
            ))
        return data

    def _candidates(self, row, work):
        unpacked = row.get("unpack_files")
        if isinstance(unpacked, list) and unpacked:
            return tuple(self._candidate(file, work, parent=row) for file in unpacked)
        return (self._candidate(row, work),)

    def _candidate(self, row, work, parent=None):
        parent = parent or {}
        path = str(
            row.get("url") or row.get("download") or row.get("file") or ""
        ).strip()
        url = urljoin("https://dl.subdl.com", path)
        parsed = urlsplit(url)
        valid = bool(
            path
            and parsed.scheme == "https"
            and parsed.hostname == "dl.subdl.com"
        )
        title = " ".join(str(value) for value in (
            work.get("name"), row.get("release_name"), parent.get("release_name")
        ) if value)
        return SourceCandidate(
            self.name, str(row.get("name") or path), title,
            detail_url=f"https://subdl.com/subtitle/sd{work['sd_id']}" if work.get("sd_id") else "https://subdl.com",
            year=_number(work.get("year")), season=_number(row.get("season") or parent.get("season")),
            episode=_number(row.get("episode") or parent.get("episode")), language={"ZH": "zh-CN", "ZH_BG": "zh-TW"}.get(
                str(row.get("language") or parent.get("language") or "").upper(),
                str(row.get("language") or parent.get("language") or "")
            ),
            downloadable=valid, download_ref=((url, str(row.get("name") or "subtitle.zip")),) if valid else (),
            metadata={"identity_match": {"kind": "tmdb_id", "value": str(work.get("tmdb_id") or "")}},
        )

    async def details(self, candidate):
        return candidate

    async def _download_files(self, links, *, headers=None):
        if not links:
            raise ValueError("字幕源未提供可用下载地址")
        files = []
        for url, name in tuple(links)[:8]:
            content, _ = await fetch(self.client, str(url), headers=headers)
            files.append((str(name or "subtitle"), content))
        return tuple(files)

    async def download(self, candidate):
        key = tuple((str(url), str(name or "")) for url, name in (candidate.download_ref or ()))
        cached = self._downloads.get(key)
        if cached is not None:
            return DownloadResult(self.name, files=cached)
        try:
            # Anonymous downloads are the documented free-account path and do
            # not consume paid account quota. Fall back to authenticated access
            # only when the public raw-file endpoint fails.
            try:
                files = await self._download_files(candidate.download_ref or ())
            except Exception:
                if not self.key:
                    raise
                files = await self._download_files(
                    candidate.download_ref or (),
                    headers={"x-api-key": self.key},
                )
            return DownloadResult(self.name, files=_remember_download(self._downloads, key, files))
        except Exception as exc:
            failure = http_failure(self.name, exc, "https://subdl.com")
            return DownloadResult(self.name, error=failure.error if failure else SourceError(
                self.name, SourceErrorKind.DOWNLOAD,
                "SubDL 字幕下载失败，可能是源站限流或候选文件已失效", True
            ))
