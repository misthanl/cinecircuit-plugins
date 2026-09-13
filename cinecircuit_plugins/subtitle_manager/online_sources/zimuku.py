"""Zimuku public-page adapter.

The adapter detects Zimuku's fixed-image verification page and exposes it as a
user-solvable CAPTCHA challenge. It does not run OCR or otherwise bypass the
check by itself.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote_plus, unquote, urljoin, urlsplit

from bs4 import BeautifulSoup

from ..subtitle_download import fetch, fetch_links
from .base import (
    CaptchaChallenge,
    DownloadResult,
    SearchRequest,
    SourceCandidate,
    SourceError,
    SourceErrorKind,
    SourceFailure,
    SourceSearchResult,
    SourceState,
    http_failure,
    same_origin,
    text_error_kind,
)
from .captcha import bmp_data_url, cookie_snapshot

_MAX_CANDIDATES = 20
_SEARCH_SELECTOR = (
    ".item a[href], .search-result a[href], .media-heading a[href], a[href*='/detail/']"
)
_DOWNLOAD_SELECTOR = (
    "a.down1[href], a.download[href], .download a[href], a#down[href], a[href*='/download/']"
)


class ZimukuSource:
    name = "字幕库"

    def __init__(self, client: Any, config: dict[str, Any]):
        self.client = client
        self.root = str(config.get("zimuku_url") or "https://zmk.pw").rstrip("/")

    async def status(self) -> SourceState:
        return SourceState.READY

    def _restricted(self, content: bytes, url: str, *, resume_url: str = "") -> None:
        kind = text_error_kind(content.decode("utf-8", "ignore"))
        if not kind:
            return
        label = {
            SourceErrorKind.CAPTCHA: "验证码",
            SourceErrorKind.LOGIN: "登录",
            SourceErrorKind.QUOTA: "访问配额",
        }.get(kind, "访问限制")
        if kind is SourceErrorKind.CAPTCHA:
            challenge = self._captcha_challenge(content, url, resume_url=resume_url)
            raise SourceFailure(
                SourceError(
                    self.name,
                    kind,
                    f"字幕库遇到{label}限制",
                    manual_url=url,
                    challenge=challenge,
                )
            )
        raise SourceFailure(SourceError(self.name, kind, f"字幕库遇到{label}限制", manual_url=url))

    def _captcha_challenge(self, content: bytes, url: str, *, resume_url: str) -> CaptchaChallenge:
        text = content.decode("utf-8", "ignore")
        soup = BeautifulSoup(content, "html.parser")
        image = soup.select_one("img.verifyimg, img[src*='data:image/bmp;base64,']")
        image_src = str(image.get("src") or "") if image is not None else ""
        if not image_src:
            start = text.find("data:image/bmp;base64,")
            if start >= 0:
                end = text.find('"', start)
                end = len(text) if end < 0 else end
                image_src = text[start:end]
        return CaptchaChallenge(
            provider=self.name,
            site="zimuku",
            image=bmp_data_url(image_src),
            instruction="请输入页面中显示的 5 位数字验证码",
            verification_url=url,
            submit_url=url,
            method="GET",
            payload={"param": "security_verify_img"},
            code_encoding="hex",
            resume_url=resume_url or url,
            cookies=cookie_snapshot(self.client),
        )

    async def _page(self, url: str, *, resume_url: str = "") -> tuple[bytes, str]:
        try:
            return await fetch(self.client, url)
        except Exception as exc:
            failure = http_failure(self.name, exc, url)
            if failure:
                raise failure from exc
            raise

    async def search(self, request: SearchRequest) -> SourceSearchResult:
        search_url = f"{self.root}/search?q={quote_plus(request.query)}"
        content, final_url = await self._page(search_url, resume_url=search_url)
        self._restricted(content, final_url, resume_url=search_url)
        soup = BeautifulSoup(content, "html.parser")
        found: dict[str, SourceCandidate] = {}
        for anchor in soup.select(_SEARCH_SELECTOR):
            href = urljoin(final_url, str(anchor.get("href") or ""))
            if not same_origin(final_url, href):
                continue
            card = anchor.find_parent(class_=("item", "search-result", "media"))
            title = (
                card.get_text(" ", strip=True)
                if card is not None
                else anchor.get_text(" ", strip=True)
            ) or str(anchor.get("title") or "")
            if not title or href in found:
                continue
            found[href] = SourceCandidate(
                self.name,
                href.rstrip("/").rsplit("/", 1)[-1],
                title,
                href,
                downloadable=True,
                download_ref=href,
            )
            if len(found) >= _MAX_CANDIDATES:
                break
        return SourceSearchResult(self.name, SourceState.READY, tuple(found.values()))

    async def details(self, candidate: SourceCandidate) -> SourceCandidate:
        content, final_url = await self._page(candidate.detail_url, resume_url=candidate.detail_url)
        self._restricted(content, final_url, resume_url=candidate.detail_url)
        soup = BeautifulSoup(content, "html.parser")
        links: list[tuple[str, str]] = []
        # Accept only explicit download controls, never every anchor.
        for anchor in soup.select(_DOWNLOAD_SELECTOR):
            href = urljoin(final_url, str(anchor.get("href") or ""))
            if _unsupported_archive(href):
                continue
            links.append((href, _file_name(href) or f"{candidate.result_id}.zip"))
        return replace(
            candidate,
            downloadable=bool(links),
            download_ref=tuple(dict.fromkeys(links)),
        )

    async def download(self, candidate: SourceCandidate) -> DownloadResult:
        detailed = await self.details(candidate)
        if not detailed.download_ref:
            return DownloadResult(
                self.name,
                error=SourceError(
                    self.name,
                    SourceErrorKind.DOWNLOAD,
                    "字幕库未提供公开下载地址，可能需要登录或验证码",
                    manual_url=candidate.detail_url,
                ),
            )
        return DownloadResult(
            self.name,
            tuple(await fetch_links(self.client, list(detailed.download_ref))),
        )


def _file_name(url: str) -> str:
    name = unquote(PurePosixPath(urlsplit(url).path).name)
    return (
        name
        if PurePosixPath(name).suffix.lower() in {".zip", ".srt", ".ass", ".ssa", ".vtt", ".sub"}
        else ""
    )


def _unsupported_archive(url: str) -> bool:
    return PurePosixPath(urlsplit(url).path).suffix.casefold() in {".rar", ".7z"}
