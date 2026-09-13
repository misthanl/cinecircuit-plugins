"""OpenSubtitles REST API adapter."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit

from ..subtitle_download import api_json, fetch_links
from .base import (
    DownloadResult,
    SearchRequest,
    SourceCandidate,
    SourceError,
    SourceErrorKind,
    SourceFailure,
    SourceSearchResult,
    SourceState,
    http_failure,
)


class OpenSubtitlesSource:
    name = "OpenSubtitles"

    def __init__(self, client: Any, config: dict[str, Any]):
        self.client = client
        self.config = config
        self.base = str(
            config.get("opensubtitles_api_url") or "https://api.opensubtitles.com/api/v1"
        ).rstrip("/")
        self.headers = {
            "Api-Key": str(config.get("opensubtitles_api_key") or ""),
            "User-Agent": "CineCircuit v1.0",
        }
        self._authenticated = False

    async def status(self) -> SourceState:
        return (
            SourceState.READY if self.config.get("opensubtitles_api_key") else SourceState.DISABLED
        )

    async def _authenticate(self) -> None:
        if self._authenticated or not self.config.get("opensubtitles_username"):
            return
        try:
            data = await api_json(
                self.client,
                self.base + "/login",
                method="POST",
                headers=self.headers,
                json={
                    "username": self.config["opensubtitles_username"],
                    "password": self.config.get("opensubtitles_password", ""),
                },
            )
        except Exception as exc:
            failure = http_failure(self.name, exc, "https://www.opensubtitles.com")
            if failure:
                raise failure from exc
            raise
        if not data.get("token"):
            raise SourceFailure(
                SourceError(
                    self.name,
                    SourceErrorKind.LOGIN,
                    "OpenSubtitles 登录失败",
                    manual_url="https://www.opensubtitles.com",
                )
            )
        self.headers["Authorization"] = f"Bearer {data['token']}"
        routed_host = str(data.get("base_url") or "").strip()
        if routed_host:
            parsed = urlsplit(routed_host if "://" in routed_host else f"https://{routed_host}")
            hostname = str(parsed.hostname or "").casefold()
            if (
                parsed.scheme == "https"
                and (hostname == "opensubtitles.com" or hostname.endswith(".opensubtitles.com"))
                and not parsed.username
                and not parsed.password
                and parsed.port in (None, 443)
            ):
                self.base = f"https://{parsed.netloc}/api/v1"
        self._authenticated = True

    @staticmethod
    def _parameters(request: SearchRequest) -> list[dict[str, Any]]:
        common: dict[str, Any] = {}
        if request.language:
            common["languages"] = request.language
        if request.year:
            common["year"] = request.year
        if request.season is not None:
            common["season_number"] = request.season
        if request.episode is not None:
            common["episode_number"] = request.episode
        searches: list[dict[str, Any]] = []
        if request.tmdb_id:
            searches.append({**common, "tmdb_id": request.tmdb_id})
        searches.append({**common, "query": request.query})
        if request.imdb_id:
            searches.append({**common, "imdb_id": request.imdb_id.removeprefix("tt")})
        return searches

    async def search(self, request: SearchRequest) -> SourceSearchResult:
        if await self.status() is SourceState.DISABLED:
            configuration_error = SourceError(
                self.name, SourceErrorKind.CONFIGURATION, "OpenSubtitles API Key 未配置"
            )
            return SourceSearchResult(
                self.name, SourceState.DISABLED, errors=(configuration_error,)
            )
        await self._authenticate()
        found: dict[str, SourceCandidate] = {}
        errors: list[SourceError] = []
        for params in self._parameters(request):
            payload, error = await self._search_payload(params)
            if error is not None:
                errors.append(error)
                continue
            identity_match = next(
                (
                    {"kind": key, "value": str(params[key])}
                    for key in ("tmdb_id", "imdb_id")
                    if params.get(key)
                ),
                None,
            )
            found.update(self._payload_candidates(payload, request, identity_match=identity_match))
            if found:  # Stop at the first identity key that returns candidates.
                break
        state = SourceState.READY if found or not errors else SourceState.ERROR
        if found and not self._has_download_credentials():
            errors.append(
                SourceError(
                    self.name,
                    SourceErrorKind.LOGIN,
                    "OpenSubtitles 下载需要配置账号和密码",
                    manual_url="https://www.opensubtitles.com",
                )
            )
            found = {
                key: replace(candidate, downloadable=False) for key, candidate in found.items()
            }
        return SourceSearchResult(self.name, state, tuple(found.values()), tuple(errors))

    async def _search_payload(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], SourceError | None]:
        try:
            payload = await api_json(
                self.client,
                self.base + "/subtitles",
                params=params,
                headers=self.headers,
            )
            return payload, None
        except Exception as exc:
            failure = http_failure(self.name, exc, "https://www.opensubtitles.com")
            if failure:
                raise failure from exc
            # Never copy response bodies or signed query strings into public errors.
            error = SourceError(
                self.name,
                SourceErrorKind.PROTOCOL,
                "OpenSubtitles 查询失败",
                True,
            )
            return {}, error

    def _payload_candidates(
        self,
        payload: dict[str, Any],
        request: SearchRequest,
        *,
        identity_match: dict[str, str] | None = None,
    ) -> dict[str, SourceCandidate]:
        found: dict[str, SourceCandidate] = {}
        for row in list(payload.get("data") or [])[:20]:
            attrs = row.get("attributes") or {}
            feature = attrs.get("feature_details") or {}
            files = tuple(attrs.get("files") or ())
            key = _candidate_key(row, files)
            if not key:
                continue
            found[key] = SourceCandidate(
                provider=self.name,
                result_id=key,
                title=str(attrs.get("release") or feature.get("title") or request.query),
                detail_url=str(attrs.get("url") or ""),
                year=_integer(feature.get("year")),
                season=_integer(feature.get("season_number")),
                episode=_integer(feature.get("episode_number")),
                language=str(attrs.get("language") or ""),
                subtitle_format=_subtitle_format(files),
                downloadable=any(item.get("file_id") for item in files),
                download_ref=files,
                metadata={"raw": row, "identity_match": identity_match},
            )
        return found

    def _has_download_credentials(self) -> bool:
        return bool(
            self.config.get("opensubtitles_username") and self.config.get("opensubtitles_password")
        )

    async def details(self, candidate: SourceCandidate) -> SourceCandidate:
        return candidate

    async def download(self, candidate: SourceCandidate) -> DownloadResult:
        if not self._has_download_credentials():
            return DownloadResult(
                self.name,
                error=SourceError(
                    self.name,
                    SourceErrorKind.LOGIN,
                    "OpenSubtitles 下载需要配置账号和密码",
                    manual_url=candidate.detail_url or "https://www.opensubtitles.com",
                ),
            )
        await self._authenticate()
        links: list[tuple[str, str]] = []
        for item in candidate.download_ref or ():
            file_id = item.get("file_id") if isinstance(item, dict) else None
            if not file_id:
                continue
            data = await self._download_link(candidate, file_id)
            links.append(
                (
                    str(data["link"]),
                    str(data.get("file_name") or item.get("file_name") or "subtitle.srt"),
                )
            )
        if not links:
            return DownloadResult(
                self.name,
                error=SourceError(
                    self.name,
                    SourceErrorKind.DOWNLOAD,
                    "OpenSubtitles 候选没有 file_id",
                    manual_url=candidate.detail_url,
                ),
            )
        return DownloadResult(self.name, tuple(await fetch_links(self.client, links)))

    async def _download_link(self, candidate: SourceCandidate, file_id: Any) -> dict[str, Any]:
        try:
            data = await api_json(
                self.client,
                self.base + "/download",
                method="POST",
                headers=self.headers,
                json={"file_id": file_id, "sub_format": "srt"},
            )
        except Exception as exc:
            failure = http_failure(
                self.name,
                exc,
                candidate.detail_url or "https://www.opensubtitles.com",
            )
            if failure:
                raise failure from exc
            raise
        if not data.get("link"):
            raise SourceFailure(
                SourceError(
                    self.name,
                    SourceErrorKind.QUOTA,
                    str(data.get("message") or "OpenSubtitles 未返回下载链接"),
                    manual_url=candidate.detail_url,
                )
            )
        return data


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _candidate_key(row: dict[str, Any], files: tuple[Any, ...]) -> str:
    file_id = next((item.get("file_id") for item in files if item.get("file_id")), "")
    return str(row.get("id") or file_id)


def _subtitle_format(files: tuple[Any, ...]) -> str:
    supported = {"ass", "ssa", "srt", "vtt", "webvtt", "sub"}
    for item in files:
        filename = str(item.get("file_name") or "") if isinstance(item, dict) else ""
        extension = filename.rsplit(".", 1)[-1].casefold() if "." in filename else ""
        if extension in supported:
            return "vtt" if extension == "webvtt" else extension
    # The download endpoint is explicitly requested with sub_format=srt.
    return "srt" if any(item.get("file_id") for item in files if isinstance(item, dict)) else ""
