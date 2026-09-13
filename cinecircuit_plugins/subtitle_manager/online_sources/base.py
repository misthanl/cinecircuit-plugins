"""Public contracts shared by online subtitle sources."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
import re
from pathlib import PurePosixPath
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit, urlunsplit

from .captcha import CaptchaChallenge


class SourceState(StrEnum):
    READY = "ready"
    DISABLED = "disabled"
    RESTRICTED = "restricted"
    ERROR = "error"


class SourceErrorKind(StrEnum):
    CONFIGURATION = "configuration"
    TIMEOUT = "timeout"
    NETWORK = "network"
    PROTOCOL = "protocol"
    CAPTCHA = "captcha"
    LOGIN = "login"
    QUOTA = "quota"
    DOWNLOAD = "download"


@dataclass(frozen=True, slots=True)
class SourceError:
    provider: str
    kind: SourceErrorKind
    message: str
    retryable: bool = False
    manual_url: str = ""
    challenge: CaptchaChallenge | None = None


@dataclass(frozen=True, slots=True)
class SearchRequest:
    query: str
    identity: Any
    language: str = ""
    season: int | None = None
    episode: int | None = None
    year: int | None = None
    tmdb_id: str = ""
    imdb_id: str = ""
    douban_id: str = ""

    @classmethod
    def from_identity(cls, identity: Any, query: str, *, language: str = "") -> SearchRequest:
        def value(name: str, default: Any = None) -> Any:
            if isinstance(identity, dict):
                return identity.get(name, default)
            return getattr(identity, name, default)

        def integer(name: str) -> int | None:
            raw = value(name)
            try:
                return int(raw) if raw not in (None, "") else None
            except (TypeError, ValueError):
                return None

        return cls(
            query=query,
            identity=identity,
            language=language,
            season=integer("season"),
            episode=integer("episode"),
            year=integer("year"),
            tmdb_id=str(value("tmdb_id", "") or ""),
            imdb_id=str(value("imdb_id", "") or ""),
            douban_id=str(value("douban_id", "") or ""),
        )


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    provider: str
    result_id: str
    title: str
    detail_url: str = ""
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    language: str = ""
    subtitle_format: str = ""
    downloadable: bool = False
    download_ref: Any = None
    score: float = 0.0
    match_reason: str = "尚未校验"
    matched: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()

    def with_match(self, *, score: float, reason: str, matched: bool) -> SourceCandidate:
        return replace(self, score=score, match_reason=reason, matched=matched)

    def as_dict(self) -> dict[str, Any]:
        candidate = enrich_candidate(self)
        source_url = safe_public_link(candidate.detail_url)
        return {
            "provider": candidate.provider,
            "id": candidate.result_id,
            "title": candidate.title,
            "url": source_url,
            "year": candidate.year,
            "season": candidate.season,
            "episode": candidate.episode,
            "language": candidate.language,
            "format": candidate.subtitle_format,
            "downloadable": candidate.downloadable,
            "score": candidate.score,
            "match_reason": candidate.match_reason,
            "matched": candidate.matched,
            "tags": list(candidate.tags),
        }


_SUBTITLE_FORMATS = ("ass", "ssa", "srt", "vtt", "webvtt", "sub")
_FORMAT_TOKEN = re.compile(r"(?i)(?<![a-z0-9])(webvtt|ass|ssa|srt|vtt|sub)(?![a-z0-9])")


def _candidate_file_names(candidate: SourceCandidate) -> list[str]:
    names: list[str] = []
    refs = candidate.download_ref or ()
    refs = refs if isinstance(refs, (list, tuple)) else (refs,)
    for item in refs:
        if isinstance(item, dict):
            names.extend(str(item.get(key) or "") for key in ("file_name", "filename", "name", "f"))
        elif isinstance(item, (list, tuple)) and len(item) > 1:
            names.append(str(item[1] or ""))
    return [name for name in names if name]


def infer_subtitle_format(*values: str) -> str:
    """Infer subtitle formats from labels, releases and returned file names."""

    found: list[str] = []
    for value in values:
        text = str(value or "")
        extension = PurePosixPath(text.split("?", 1)[0]).suffix.lstrip(".").casefold()
        candidates = ([extension] if extension in _SUBTITLE_FORMATS else []) + [
            match.casefold() for match in _FORMAT_TOKEN.findall(text)
        ]
        for candidate in candidates:
            normalized = "vtt" if candidate == "webvtt" else candidate
            if normalized not in found:
                found.append(normalized)
    return "/".join(found)


def infer_subtitle_language(*values: str) -> str:
    """Infer common subtitle language labels without matching release-name fragments."""

    text = " ".join(str(value or "") for value in values)
    folded = text.casefold()
    simplified = bool(
        re.search(r"(?<![a-z0-9])(zh[-_. ]?cn|chs|chi|zho|cn)(?![a-z0-9])", folded)
        or any(marker in text for marker in ("简体", "简中", "中文", "国配"))
    )
    traditional = bool(
        re.search(r"(?<![a-z0-9])(zh[-_. ]?tw|cht)(?![a-z0-9])", folded)
        or any(marker in text for marker in ("繁体", "繁中"))
    )
    english = bool(
        re.search(r"(?<![a-z0-9])(en|eng|english)(?![a-z0-9])", folded)
        or any(marker in text for marker in ("英语", "英文", "中英", "简英", "繁英", "国/英"))
    )
    japanese = bool(
        re.search(r"(?<![a-z0-9])(ja|jpn|japanese)(?![a-z0-9])", folded) or "日语" in text
    )
    korean = bool(re.search(r"(?<![a-z0-9])(ko|kor|korean)(?![a-z0-9])", folded) or "韩语" in text)
    if simplified:
        return "zh-CN/en" if english else "zh-CN"
    if traditional:
        return "zh-TW/en" if english else "zh-TW"
    if english:
        return "en"
    if japanese:
        return "ja"
    if korean:
        return "ko"
    return ""


def enrich_candidate(candidate: SourceCandidate) -> SourceCandidate:
    """Fill metadata omitted by a provider while preserving authoritative fields."""

    evidence = [candidate.title, *candidate.tags, *_candidate_file_names(candidate)]
    return replace(
        candidate,
        language=candidate.language or infer_subtitle_language(*evidence),
        subtitle_format=candidate.subtitle_format or infer_subtitle_format(*evidence),
    )


@dataclass(frozen=True, slots=True)
class SourceSearchResult:
    provider: str
    state: SourceState
    candidates: tuple[SourceCandidate, ...] = ()
    errors: tuple[SourceError, ...] = ()
    attempts: int = 1


@dataclass(frozen=True, slots=True)
class DownloadResult:
    provider: str
    files: tuple[tuple[str, bytes], ...] = ()
    error: SourceError | None = None


class SourceFailure(RuntimeError):
    def __init__(self, error: SourceError):
        super().__init__(error.message)
        self.error = error


@runtime_checkable
class OnlineSource(Protocol):
    name: str

    async def status(self) -> SourceState: ...

    async def search(self, request: SearchRequest) -> SourceSearchResult: ...

    async def details(self, candidate: SourceCandidate) -> SourceCandidate: ...

    async def download(self, candidate: SourceCandidate) -> DownloadResult: ...


def text_error_kind(text: str) -> SourceErrorKind | None:
    lowered = text.casefold()
    if any(word in lowered for word in ("验证码", "captcha", "人机验证")):
        return SourceErrorKind.CAPTCHA
    if "cloudflare" in lowered and any(
        marker in lowered
        for marker in (
            "cf-chl-",
            "/cdn-cgi/challenge-platform/",
            "cloudflare ray id",
            "just a moment...",
        )
    ):
        return SourceErrorKind.CAPTCHA
    if any(word in lowered for word in ("请登录", "登录后", "sign in", "log in")):
        return SourceErrorKind.LOGIN
    if any(word in lowered for word in ("配额", "quota", "rate limit", "too many requests")):
        return SourceErrorKind.QUOTA
    return None


def language_text(value: Any) -> str:
    """Normalize both plain language strings and ASSRT lang objects."""
    if not isinstance(value, dict):
        return str(value or "")
    descriptions = value.get("desc") or value.get("description")
    if descriptions:
        return str(descriptions)
    raw_flags = value.get("langlist")
    flags = raw_flags if isinstance(raw_flags, dict) else value
    return "/".join(
        str(key).removeprefix("lang")
        for key, enabled in flags.items()
        if enabled and key not in {"desc", "description", "langlist"}
    )


def same_origin(left: str, right: str) -> bool:
    """Allow intermediate HTML navigation only within the configured source."""

    try:
        first, second = urlsplit(left), urlsplit(right)
        return (
            first.scheme.casefold() == second.scheme.casefold()
            and first.hostname == second.hostname
            and (first.port or (443 if first.scheme == "https" else 80))
            == (second.port or (443 if second.scheme == "https" else 80))
        )
    except ValueError:
        return False


def safe_public_link(url: str) -> str:
    """Return browser-safe public-link syntax without exposing URL credentials."""
    try:
        parsed = urlsplit(str(url or ""))
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or (parsed.username or parsed.password)
        ):
            return ""
        return urlunsplit(parsed)
    except ValueError:
        return ""


def http_failure(provider: str, exc: Exception, manual_url: str = "") -> SourceFailure | None:
    """Translate public HTTP restrictions without depending on a client package."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    kinds = {
        401: (SourceErrorKind.LOGIN, "需要登录"),
        403: (SourceErrorKind.CAPTCHA, "访问被拒绝，可能需要验证码或手动访问"),
        429: (SourceErrorKind.QUOTA, "请求配额或频率受限"),
    }
    if status not in kinds:
        return None
    kind, label = kinds[status]
    return SourceFailure(SourceError(provider, kind, f"{provider} {label}", manual_url=manual_url))
