"""SubHD public-page adapter. It deliberately stops at verification walls."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote_plus, unquote, urljoin, urlsplit

from bs4 import BeautifulSoup

from ..subtitle_download import api_json, fetch, fetch_links
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
from .captcha import cookie_snapshot, svg_data_url

_MAX_WORKS = 5
_MAX_CANDIDATES = 20
_SUBTITLE_TAGS = (
    "官方字幕",
    "其他来源",
    "双语",
    "简体",
    "繁体",
    "英语",
    "SRT",
    "ASS",
    "SSA",
    "VTT",
)
_SEARCH_SELECTOR = (
    ".search-result a[href], .movie-list a[href], .col-md-9 .media-heading a[href], a[href*='/d/']"
)
_DOWNLOAD_SELECTOR = (
    "a.download[href], .download a[href], a#download[href], "
    ".subtitle-list a[href], .sub-list a[href], "
    ".view-text a[href*='/a/'], a[href*='/download/']"
)
_DETAIL_DOWNLOAD_SELECTOR = (
    "a.download[href], .download a[href], a#download[href], a[href*='/download/']"
)
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


class SubHDSource:
    name = "SubHD"

    def __init__(self, client: Any, config: dict[str, Any]):
        self.client = client
        self.root = str(config.get("subhd_url") or "https://subhd.tv").rstrip("/")

    async def status(self) -> SourceState:
        return SourceState.READY

    def _restricted(self, content: bytes, url: str) -> None:
        text = content.decode("utf-8", "ignore")
        kind = text_error_kind(text)
        if kind is SourceErrorKind.CAPTCHA:
            # Normal SubHD pages also load Cloudflare's challenge bootstrap.
            # Actual result/download controls are stronger evidence than that
            # passive script reference.
            page = BeautifulSoup(content, "html.parser")
            if page.select_one(_SEARCH_SELECTOR) or page.select_one(_DOWNLOAD_SELECTOR):
                return
        if kind:
            requirement = "验证码" if kind is SourceErrorKind.CAPTCHA else "登录或解除限制"
            raise SourceFailure(
                SourceError(
                    self.name,
                    kind,
                    f"SubHD 需要{requirement}",
                    manual_url=url,
                )
            )

    async def _page(self, url: str) -> tuple[bytes, str]:
        try:
            return await fetch(self.client, url)
        except Exception as exc:
            failure = http_failure(self.name, exc, url)
            if failure:
                raise failure from exc
            raise

    async def search(self, request: SearchRequest) -> SourceSearchResult:
        search_url = f"{self.root}/search/{quote_plus(request.query)}"
        content, final_url = await self._page(search_url)
        self._restricted(content, final_url)
        direct_candidates = self._candidate_cards(content, final_url)
        if direct_candidates:
            return SourceSearchResult(
                self.name, SourceState.READY, tuple(direct_candidates.values())
            )
        works = self._search_works(content, final_url)
        found: dict[str, SourceCandidate] = {}
        errors: list[SourceError] = []
        for work_url, work_title in works.items():
            candidates, error = await self._work_candidates(work_url, work_title)
            found.update(candidates)
            if error is not None:
                errors.append(error)
            if len(found) >= _MAX_CANDIDATES:
                break
        state = SourceState.READY if found or not errors else SourceState.ERROR
        if any(error.kind in {SourceErrorKind.CAPTCHA, SourceErrorKind.LOGIN} for error in errors):
            state = SourceState.RESTRICTED
        return SourceSearchResult(self.name, state, tuple(found.values()), tuple(errors))

    @staticmethod
    def _candidate_cards(content: bytes, final_url: str) -> dict[str, SourceCandidate]:
        """Parse current SubHD result cards, including their language/format labels."""

        soup = BeautifulSoup(content, "html.parser")
        found: dict[str, SourceCandidate] = {}
        for anchor in soup.select(".view-text a[href*='/a/']")[:_MAX_CANDIDATES]:
            href = urljoin(final_url, str(anchor.get("href") or ""))
            if not same_origin(final_url, href):
                continue
            container = anchor.find_parent("div", class_="bg-white")
            if container is None:
                container = anchor.find_parent("div", class_="px-3")
            item_text = (
                container.get_text(" ", strip=True)
                if container is not None
                else (anchor.parent or anchor).get_text(" ", strip=True)
            )
            title = anchor.get_text(" ", strip=True)
            if not title:
                continue
            tags = tuple(tag for tag in _SUBTITLE_TAGS if tag in item_text)
            found[href] = SourceCandidate(
                "SubHD",
                href.rstrip("/").rsplit("/", 1)[-1],
                title,
                href,
                downloadable=True,
                download_ref=href,
                tags=tags,
            )
        return found

    @staticmethod
    def _search_works(content: bytes, final_url: str) -> dict[str, str]:
        soup = BeautifulSoup(content, "html.parser")
        works: dict[str, str] = {}
        # Search-result cards only; navigation and unrelated anchors are ignored.
        for anchor in soup.select(_SEARCH_SELECTOR):
            href = urljoin(final_url, str(anchor.get("href") or ""))
            if not same_origin(final_url, href):
                continue
            card = anchor.find_parent(class_=("search-result", "media", "movie-list"))
            if card is None:
                card = anchor.find_parent("div", class_="row")
            title = (
                card.get_text(" ", strip=True)
                if card is not None
                else anchor.get_text(" ", strip=True)
            ) or str(anchor.get("title") or "")
            if not title or href in works:
                continue
            works[href] = title
            if len(works) >= _MAX_WORKS:
                break
        return works

    async def _work_candidates(
        self, work_url: str, work_title: str
    ) -> tuple[dict[str, SourceCandidate], SourceError | None]:
        try:
            body, work_final_url = await self._page(work_url)
            self._restricted(body, work_final_url)
        except SourceFailure as exc:
            return {}, exc.error
        except Exception:
            return {}, SourceError(
                self.name,
                SourceErrorKind.NETWORK,
                "SubHD 作品页读取失败",
                True,
                work_url,
            )
        work_page = BeautifulSoup(body, "html.parser")
        anchors = work_page.select(
            ".subtitle-list a[href], .sub-list a[href], .view-text a[href*='/a/']"
        )
        if not anchors:
            fallback = SourceCandidate(
                self.name,
                work_url.rstrip("/").rsplit("/", 1)[-1],
                work_title,
                work_url,
                downloadable=True,
                download_ref=work_url,
            )
            return {work_url: fallback}, None
        return self._subtitle_anchor_candidates(anchors, work_final_url, work_title), None

    def _subtitle_anchor_candidates(
        self, anchors: Any, work_final_url: str, work_title: str
    ) -> dict[str, SourceCandidate]:
        found: dict[str, SourceCandidate] = {}
        for anchor in anchors[:_MAX_CANDIDATES]:
            href = urljoin(work_final_url, str(anchor.get("href") or ""))
            if not same_origin(work_final_url, href):
                continue
            anchor_label = anchor.get_text(" ", strip=True)
            current_detail = urlsplit(href).path.startswith("/a/")
            row = anchor.find_parent(["li", "tr", "article", "div"])
            label = (
                anchor_label
                if current_detail
                else row.get_text(" ", strip=True)
                if row is not None
                else anchor_label
            )
            candidate_title = label if current_detail else f"{work_title} {label}".strip()
            item_container = anchor.find_parent("div", class_="px-3")
            item_text = (
                item_container.get_text(" ", strip=True) if item_container is not None else label
            )
            tags = tuple(tag for tag in _SUBTITLE_TAGS if tag in item_text)
            found[href] = SourceCandidate(
                self.name,
                href.rstrip("/").rsplit("/", 1)[-1],
                candidate_title,
                href,
                downloadable=True,
                download_ref=href,
                tags=tags,
            )
        return found

    def _browser_headers(self, referer: str, *, ajax: bool = False) -> dict[str, str]:
        parsed = urlsplit(self.root)
        headers = {
            "User-Agent": _BROWSER_USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": referer,
            "Origin": f"{parsed.scheme}://{parsed.netloc}",
        }
        if ajax:
            headers.update(
                {
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest",
                }
            )
        return headers

    async def _dynamic_download_links(
        self, page: BeautifulSoup, page_url: str, result_id: str
    ) -> list[tuple[str, str]]:
        control = page.select_one("[data-sid]")
        sid = str(control.get("data-sid") or "") if control is not None else ""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", sid):
            return []
        prepare_url = urljoin(self.root + "/", "api/sub/prepare-download")
        prepared = await api_json(
            self.client,
            prepare_url,
            method="POST",
            json={"sid": sid},
            headers=self._browser_headers(page_url, ajax=True),
        )
        down_url = urljoin(self.root + "/", str(prepared.get("url") or ""))
        if (
            prepared.get("success") is not True
            or not same_origin(self.root, down_url)
            or not urlsplit(down_url).path.startswith("/down/")
        ):
            return []
        await fetch(
            self.client,
            down_url,
            headers=self._browser_headers(page_url),
        )
        download_api = urljoin(self.root + "/", "api/sub/down")
        resolved = await api_json(
            self.client,
            download_api,
            method="POST",
            json={"sid": sid, "cap": ""},
            headers=self._browser_headers(down_url, ajax=True),
        )
        if resolved.get("pass") is False:
            raise SourceFailure(self._download_captcha_error(page_url, down_url, sid, resolved))
        file_url = str(resolved.get("url") or "").strip()
        parsed = urlsplit(file_url)
        if (
            resolved.get("success") is not True
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return []
        return [(file_url, _file_name(file_url) or f"{result_id}.zip")]

    def _download_captcha_error(
        self,
        page_url: str,
        down_url: str,
        sid: str,
        resolved: dict[str, Any],
    ) -> SourceError:
        svg = str(resolved.get("msg") or "")
        api_url = urljoin(self.root + "/", "api/sub/down")
        return SourceError(
            self.name,
            SourceErrorKind.CAPTCHA,
            "SubHD 下载需要验证码",
            manual_url=page_url,
            challenge=CaptchaChallenge(
                provider=self.name,
                site="subhd",
                image=svg_data_url(svg),
                instruction="请输入下载页面中显示的验证码",
                verification_url=down_url,
                submit_url=api_url,
                method="POST",
                payload={"sid": sid},
                resume_url=page_url,
                cookies=cookie_snapshot(self.client),
                context={
                    "flow": "subhd-download",
                    "sid": sid,
                    "down_url": down_url,
                    "referer": down_url,
                },
            ),
        )

    async def submit_download_captcha(
        self,
        *,
        sid: str,
        down_url: str,
        referer: str,
        code: str,
        result_id: str,
    ) -> DownloadResult:
        api_url = urljoin(self.root + "/", "api/sub/down")
        try:
            resolved = await api_json(
                self.client,
                api_url,
                method="POST",
                json={"sid": sid, "cap": str(code or "").strip()},
                headers=self._browser_headers(referer, ajax=True),
            )
        except SourceFailure as exc:
            return DownloadResult(self.name, error=exc.error)
        except Exception as exc:
            failure = http_failure(self.name, exc, referer)
            if failure is not None:
                return DownloadResult(self.name, error=failure.error)
            return DownloadResult(
                self.name,
                error=SourceError(
                    self.name,
                    SourceErrorKind.NETWORK,
                    "SubHD 验证码提交失败",
                    True,
                    referer,
                ),
            )
        return await self._captcha_download_result(resolved, referer, down_url, sid, result_id)

    async def _captcha_download_result(
        self, resolved: dict[str, Any], referer: str, down_url: str, sid: str, result_id: str
    ) -> DownloadResult:
        if resolved.get("pass") is False:
            return DownloadResult(
                self.name,
                error=self._download_captcha_error(referer, down_url, sid, resolved),
            )
        file_url = str(resolved.get("url") or "").strip()
        parsed = urlsplit(file_url)
        if (
            resolved.get("success") is not True
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return DownloadResult(
                self.name,
                error=SourceError(
                    self.name,
                    SourceErrorKind.DOWNLOAD,
                    "SubHD 验证码校验失败或接口未返回下载地址",
                    manual_url=referer,
                ),
            )
        return DownloadResult(
            self.name,
            tuple(
                await fetch_links(
                    self.client,
                    [(file_url, _file_name(file_url) or f"{result_id}.zip")],
                )
            ),
        )

    async def details(self, candidate: SourceCandidate) -> SourceCandidate:
        content, final_url = await self._page(candidate.detail_url)
        self._restricted(content, final_url)
        soup = BeautifulSoup(content, "html.parser")
        links, subtitle_pages = self._detail_targets(soup, final_url)
        restriction: SourceFailure | None = None
        if not links:
            try:
                links.extend(
                    await self._dynamic_download_links(soup, final_url, candidate.result_id)
                )
            except SourceFailure as error:
                restriction = error
        # A work page can list multiple subtitle detail pages; parse each separately.
        for page in list(dict.fromkeys(subtitle_pages))[:_MAX_CANDIDATES]:
            try:
                links.extend(await self._detail_page_links(page, candidate.result_id))
            except SourceFailure as error:
                restriction = error
                continue
            except Exception:
                # One stale result must not discard public links
                # already found on the same work page.
                continue
        if not links and restriction is not None:
            raise restriction
        return replace(
            candidate,
            downloadable=bool(links),
            download_ref=tuple(dict.fromkeys(links)),
        )

    @staticmethod
    def _detail_targets(
        soup: BeautifulSoup, final_url: str
    ) -> tuple[list[tuple[str, str]], list[str]]:
        links: list[tuple[str, str]] = []
        pages: list[str] = []
        for anchor in soup.select(_DOWNLOAD_SELECTOR):
            href = urljoin(final_url, str(anchor.get("href") or ""))
            if _unsupported_archive(href):
                continue
            filename = _file_name(href)
            if filename:
                links.append((href, filename))
            elif href != final_url and same_origin(final_url, href):
                pages.append(href)
        return links, pages

    async def _detail_page_links(self, page: str, result_id: str) -> list[tuple[str, str]]:
        body, page_url = await self._page(page)
        self._restricted(body, page_url)
        detail = BeautifulSoup(body, "html.parser")
        links: list[tuple[str, str]] = []
        for anchor in detail.select(_DETAIL_DOWNLOAD_SELECTOR):
            href = urljoin(page_url, str(anchor.get("href") or ""))
            if not _unsupported_archive(href):
                links.append((href, _file_name(href) or f"{result_id}.zip"))
        if not links:
            links.extend(await self._dynamic_download_links(detail, page_url, result_id))
        return links

    async def download(self, candidate: SourceCandidate) -> DownloadResult:
        detailed = await self.details(candidate)
        if not detailed.download_ref:
            return DownloadResult(
                self.name,
                error=SourceError(
                    self.name,
                    SourceErrorKind.DOWNLOAD,
                    "SubHD 未提供公开下载地址，可能需要手动下载",
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
