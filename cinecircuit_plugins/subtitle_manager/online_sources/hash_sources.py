"""Shooter and Xunlei subtitle APIs, matched against actual video samples."""

import asyncio
import json
from pathlib import PurePosixPath
import re
from urllib.parse import unquote

from ..subtitle_download import fetch, fetch_links, fetch_prefix
from ..subtitle_files import FORMATS
from .api_errors import api_failure
from .base import (
    DownloadResult, SourceCandidate, SourceError, SourceErrorKind,
    SourceSearchResult, SourceState, http_failure, infer_subtitle_language,
)
from ..video_hash import fingerprint, identity_value, sample_ranges


class HashSource:
    name = ""
    key = ""
    default_url = ""

    def __init__(self, client, config, media_files=None):
        self.client = client
        self.base = str(config.get(self.key + "_api_url") or self.default_url).rstrip("/")
        self.media_files = media_files
        self._cache = {}

    async def _rows(self, digest, path, request):
        raise NotImplementedError("Hash providers must implement their response protocol")

    def _candidate(self, row, index, request, evidence):
        raise NotImplementedError("Hash providers must implement candidate mapping")

    async def status(self):
        return SourceState.READY

    async def search(self, request):
        path = str(identity_value(request.identity, "media_path"))
        # Compute rows once per media path, but build candidates per request so
        # season/episode matching always follows the current search context.
        key = (path, request.language if self.key == "shooter" else "")
        if key not in self._cache:
            try:
                self._cache[key] = await self._rows_for_path(path, request)
            except (ValueError, OSError, AttributeError) as exc:
                error = SourceError(self.name, SourceErrorKind.CONFIGURATION, str(exc))
                return SourceSearchResult(self.name, SourceState.DISABLED, errors=(error,))
        rows, digest = self._cache[key]
        evidence = {"algorithm": self.key, "hash": digest, "media_path": path}
        candidates = tuple(
            self._candidate(row, index, request, evidence)
            for index, row in enumerate(rows)
        )
        return SourceSearchResult(self.name, SourceState.READY, tuple(c for c in candidates if c.downloadable))

    async def _rows_for_path(self, path, request):
        digest = await self._fingerprint(path)
        try:
            rows = await self._rows(digest, path, request)
        except Exception as exc:
            raise api_failure(self.name, exc) from None
        return rows, digest

    async def _fingerprint(self, path):
        if not path:
            raise ValueError("文件哈希搜索需要媒体文件路径")
        reader = getattr(self.media_files, "read_samples", None)
        if not callable(reader):
            raise ValueError("当前主程序不支持视频采样，请更新主程序")
        return fingerprint(self.key, await reader(path, sample_ranges(self.key)))

    async def details(self, candidate):
        return candidate

    async def download(self, candidate):
        try:
            files = await fetch_links(self.client, candidate.download_ref or ())
            return DownloadResult(self.name, files=tuple(files))
        except Exception as exc:
            failure = http_failure(self.name, exc, "")
            return DownloadResult(self.name, error=failure.error if failure else SourceError(
                self.name, SourceErrorKind.DOWNLOAD, "字幕下载失败", True
            ))


class ShooterSource(HashSource):
    name = "射手影音"
    key = "shooter"
    default_url = "https://www.shooter.cn/api/subapi.php"

    async def _rows(self, digest, path, request):
        pathinfo = path.replace("/", "\\")
        shortname = PurePosixPath(path.replace("\\", "/")).stem
        content, _ = await fetch(self.client, self.base, method="POST", data={
            "filehash": digest, "pathinfo": pathinfo, "shortname": shortname,
            "format": "json", "lang": "Eng" if request.language.casefold() in {"en", "eng", "english"} else "Chn",
        }, headers={"User-Agent": "SPlayer Build 1543", "Accept": "*/*"})
        # Shooter returns an empty body (or an empty list) when no hash matches.
        if content.strip() in {b"", b"\xff"}:
            return []
        rows = json.loads(content) if content.strip() else []
        if isinstance(rows, dict):
            if not rows:
                return []
            nested = (
                rows.get("data") or rows.get("result") or rows.get("results")
                or rows.get("subtitles") or rows.get("sublist") or rows.get("subs")
            )
            if isinstance(nested, list):
                rows = nested
            elif isinstance(nested, dict):
                maybe = (
                    nested.get("data") or nested.get("results")
                    or nested.get("subtitles") or nested.get("sublist") or nested.get("subs")
                )
                rows = maybe if isinstance(maybe, list) else []
            else:
                return []
            if rows is None:
                return []
        elif not isinstance(rows, list):
            raise ValueError("Invalid Shooter response")
        return rows

    def _candidate(self, row, index, request, evidence):
        raw_files = row.get("Files", row.get("files", []))
        raw_files = raw_files if isinstance(raw_files, list) else []
        title = str(identity_value(request.identity, "title") or request.query or "字幕").strip()
        year = identity_value(request.identity, "year") or request.year
        base_name = f"{title} ({year})" if year and str(year) not in title else title
        base_name = re.sub(r'[\\/:*?"<>|]+', " ", base_name).strip(" .") or "字幕"
        links = []
        for file_index, file in enumerate(raw_files):
            url = str(file.get("Link") or file.get("link") or "")
            extension = str(file.get("Ext") or file.get("ext") or "srt").lstrip(".")
            suffix = f".{file_index + 1}" if len(raw_files) > 1 else ""
            if url:
                links.append((url, f"{base_name}{suffix}.{extension}"))
        description = str(row.get("Desc") or row.get("desc") or "").strip()
        explicit_language = str(row.get("language") or row.get("lang") or "").strip()
        inferred_language = infer_subtitle_language(
            explicit_language,
            description,
            *(name for _, name in links),
        )
        if not inferred_language:
            # Shooter's protocol accepts only Eng or Chn. A successful result
            # therefore has coarse but authoritative language information even
            # when the response omits its own language field.
            requested = request.language.strip().casefold()
            inferred_language = "en" if requested in {"en", "eng", "english"} else "zh"
        return SourceCandidate(
            self.name, f"{evidence['hash']}:{index}",
            description or (links[0][1] if len(links) == 1 else f"{base_name}（{len(links)} 个字幕文件）"),
            season=request.season, episode=request.episode,
            language=inferred_language,
            downloadable=bool(links), download_ref=tuple(links),
            metadata={"file_match": evidence, "delay_ms": row.get("Delay", row.get("delay", 0))},
        )


class XunleiSource(HashSource):
    name = "迅雷看看"
    key = "xunlei"
    default_url = "http://sub.xmp.sandai.net:8000/subxl"

    async def _rows_for_path(self, path, request):
        rows, digest = await super()._rows_for_path(path, request)
        semaphore = asyncio.Semaphore(4)

        async def available(row):
            url = str(
                row.get("surl") or row.get("url") or row.get("download")
                or row.get("file") or ""
            )
            if not url:
                return False
            try:
                async with semaphore:
                    prefix, _ = await fetch_prefix(
                        self.client,
                        url,
                        limit=1024,
                        headers={"Range": "bytes=0-1023", "Accept-Encoding": "identity"},
                    )
            except Exception:
                # A transient probe failure must not hide a potentially valid
                # subtitle. The normal preview path will still report it.
                return True
            lowered = prefix.lower().lstrip()
            return not (
                lowered.startswith(b"<?xml")
                and b"<code>nosuchkey</code>" in lowered
            )

        checks = await asyncio.gather(*(available(row) for row in rows))
        return [row for row, keep in zip(rows, checks) if keep], digest

    async def _rows(self, digest, path, request):
        content, _ = await fetch(self.client, self.base + "/" + digest + ".json")
        # Historical records can contain invalid UTF-8 in display names. Keep
        # the otherwise valid response, like the reference Go JSON decoder.
        payload = json.loads(content.decode("utf-8", errors="replace"))
        return _response_rows(payload)

    def _candidate(self, row, index, request, evidence):
        url = str(
            row.get("surl") or row.get("url") or row.get("download")
            or row.get("file") or ""
        )
        raw_name = str(
            row.get("sname") or row.get("filename") or row.get("name") or "subtitle.srt"
        )
        # The historical API frequently returns URL-encoded absolute Windows
        # paths. Only expose the decoded basename; the remote path is neither
        # useful to the user nor a valid local filename.
        decoded_name = unquote(raw_name, errors="replace").replace("\\", "/")
        name = PurePosixPath(decoded_name).name or "subtitle.srt"
        suffix = PurePosixPath(name).suffix.lstrip(".").lower()
        extension = suffix if suffix in FORMATS else ""
        return SourceCandidate(
            self.name, str(row.get("scid") or f"{evidence['hash']}:{index}"), name,
            season=request.season, episode=request.episode, language=str(row.get("language") or ""),
            subtitle_format=extension,
            downloadable=bool(url), download_ref=((url, name),) if url else (),
            metadata={"file_match": evidence},
        )


def _response_rows(payload):
    """Normalize historical response envelopes without accepting malformed rows."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    if payload.get("code") not in {0, "0", None}:
        rows = payload.get("sublist") if payload.get("sublist") is not None else payload.get("subs")
        return rows if isinstance(rows, list) else []
    nested = (payload.get("sublist") or payload.get("subs") or payload.get("data")
              or payload.get("result") or payload.get("results"))
    if isinstance(nested, list):
        return nested
    if isinstance(nested, dict):
        rows = nested.get("sublist") or nested.get("subs") or nested.get("results") or nested.get("data")
        return rows if isinstance(rows, list) else []
    return []
