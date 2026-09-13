"""ASSRT API adapter."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import PurePosixPath
from typing import Any

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
    infer_subtitle_language,
    language_text,
)


class AssrtSource:
    name = "ASSRT"

    def __init__(self, client: Any, config: dict[str, Any]):
        self.client = client
        self.config = config
        self.base = str(config.get("assrt_api_url") or "https://api.assrt.net/v1").rstrip("/")
        self.headers = {"Authorization": f"Bearer {config.get('assrt_api_key', '')}"}
        self._search_cache: dict[str, dict[str, Any]] = {}

    async def status(self) -> SourceState:
        return SourceState.READY if self.config.get("assrt_api_key") else SourceState.DISABLED

    def _error(self, payload: dict[str, Any], operation: str) -> SourceFailure:
        message = str(payload.get("errmsg") or payload.get("message") or f"ASSRT {operation}失败")
        lowered = message.casefold()
        kind = (
            SourceErrorKind.QUOTA
            if any(x in lowered for x in ("quota", "配额", "limit"))
            else SourceErrorKind.PROTOCOL
        )
        return SourceFailure(
            SourceError(
                self.name,
                kind,
                message,
                kind is not SourceErrorKind.QUOTA,
                "https://2.assrt.net",
            )
        )

    async def search(self, request: SearchRequest) -> SourceSearchResult:
        if await self.status() is SourceState.DISABLED:
            error = SourceError(self.name, SourceErrorKind.CONFIGURATION, "ASSRT API Key 未配置")
            return SourceSearchResult(self.name, SourceState.DISABLED, errors=(error,))
        rows_by_id: dict[str, dict[str, Any]] = {}
        fallback = _fallback_query(request)
        for query in (request.query, fallback):
            if not query:
                continue
            data = await self._search_payload(query)
            if data.get("status") != 0:
                raise self._error(data, "搜索")
            for row in (data.get("sub") or {}).get("subs") or []:
                result_id = str(row.get("id") or "")
                if result_id:
                    rows_by_id.setdefault(result_id, row)
        candidates = tuple(
            SourceCandidate(
                provider=self.name,
                result_id=str(row.get("id") or ""),
                title=str(row.get("native_name") or row.get("videoname") or request.query),
                detail_url=str(row.get("url") or ""),
                language=_candidate_language(row),
                subtitle_format=_candidate_format(row),
                downloadable=bool(row.get("id")),
                download_ref=str(row.get("id") or ""),
                metadata={"raw": row},
            )
            for row in rows_by_id.values()
            if row.get("id")
        )
        return SourceSearchResult(self.name, SourceState.READY, candidates)

    async def _search_payload(self, query: str) -> dict[str, Any]:
        cache_key = query.casefold()
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]
        try:
            data = await api_json(
                self.client,
                self.base + "/sub/search",
                params={"q": query, "cnt": 15, "filelist": 1},
                headers=self.headers,
            )
        except Exception as exc:
            failure = http_failure(self.name, exc, "https://2.assrt.net")
            if failure:
                raise failure from exc
            raise
        self._search_cache[cache_key] = data
        return data

    async def details(self, candidate: SourceCandidate) -> SourceCandidate:
        try:
            data = await api_json(
                self.client,
                self.base + "/sub/detail",
                params={"id": candidate.result_id},
                headers=self.headers,
            )
        except Exception as exc:
            failure = http_failure(self.name, exc, candidate.detail_url or "https://2.assrt.net")
            if failure:
                raise failure from exc
            raise
        if data.get("status") != 0:
            raise self._error(data, "详情查询")
        rows = (data.get("sub") or {}).get("subs") or []
        links: list[tuple[str, str]] = []
        languages: list[str] = []
        for row in rows:
            languages.extend(language_text(row.get("lang")).split("/"))
            filelist = row.get("filelist") or []
            links.extend(
                (str(item.get("url") or ""), str(item.get("f") or ""))
                for item in filelist
                if item.get("url")
            )
            if not filelist and row.get("url"):
                links.append((str(row["url"]), str(row.get("filename") or "")))
        extension = PurePosixPath(links[0][1]).suffix.lstrip(".").lower() if links else ""
        return replace(
            candidate,
            language="/".join(filter(None, languages)) or candidate.language,
            subtitle_format=extension or candidate.subtitle_format,
            downloadable=bool(links),
            download_ref=tuple(links),
        )

    async def download(self, candidate: SourceCandidate) -> DownloadResult:
        detailed = await self.details(candidate)
        if not detailed.download_ref:
            return DownloadResult(
                self.name,
                error=SourceError(
                    self.name,
                    SourceErrorKind.DOWNLOAD,
                    "ASSRT 未返回可下载文件",
                    manual_url=candidate.detail_url or "https://2.assrt.net",
                ),
            )
        files = await fetch_links(self.client, list(detailed.download_ref))
        return DownloadResult(self.name, tuple(files))


def _fallback_query(request: SearchRequest) -> str:
    """Remove our structured suffix for ASSRT's broader title search."""

    query = request.query.strip()
    if request.episode is not None:
        fallback = re.sub(r"(?i)\s+S\d{1,2}[ ._-]*E\d{1,3}\s*$", "", query).strip()
    elif request.season is not None:
        fallback = re.sub(r"(?i)\s+S\d{1,2}\s*$", "", query).strip()
    elif request.year is not None:
        fallback = re.sub(rf"\s+{request.year}\s*$", "", query).strip()
    else:
        fallback = ""
    return fallback if fallback and fallback.casefold() != query.casefold() else ""


def _candidate_language(row: dict[str, Any]) -> str:
    language = language_text(row.get("lang"))
    if language:
        return language
    evidence = [str(row.get(key) or "") for key in ("native_name", "videoname", "subtype")]
    evidence.extend(
        str(item.get("f") or item.get("filename") or item.get("name") or "")
        for item in row.get("filelist") or []
        if isinstance(item, dict)
    )
    combined = " ".join(evidence)
    markers = (
        "国/英", "中英", "简繁英", "简繁", "简英", "繁英", "双语",
        "简体", "繁体", "中文", "英文",
    )
    labelled = next((marker for marker in markers if marker in combined), "")
    if labelled:
        return labelled
    return infer_subtitle_language(*evidence)


def _candidate_format(row: dict[str, Any]) -> str:
    subtype = str(row.get("subtype") or "").strip().casefold()
    parenthesized = re.search(r"\(([a-z0-9]+)\)", subtype)
    if parenthesized:
        return parenthesized.group(1)
    if subtype in {"ass", "ssa", "srt", "vtt", "sub"}:
        return subtype
    extensions: list[str] = []
    for item in row.get("filelist") or []:
        filename = str(item.get("f") or "") if isinstance(item, dict) else ""
        extension = PurePosixPath(filename).suffix.lstrip(".").casefold()
        if extension in {"ass", "ssa", "srt", "vtt", "sub"} and extension not in extensions:
            extensions.append(extension)
    return "/".join(extensions)
