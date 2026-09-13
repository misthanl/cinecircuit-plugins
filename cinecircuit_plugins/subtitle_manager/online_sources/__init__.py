"""Unified online subtitle source adapters and orchestration."""

from .hash_sources import ShooterSource, XunleiSource
from .subdl import SubDLSource
from .assrt import AssrtSource
from .base import (
    CaptchaChallenge,
    DownloadResult,
    OnlineSource,
    SearchRequest,
    SourceCandidate,
    SourceError,
    SourceErrorKind,
    SourceFailure,
    SourceSearchResult,
    SourceState,
    safe_public_link,
)
from .matcher import evaluate_candidate, merge_and_rank
from .opensubtitles import OpenSubtitlesSource
from .service import OnlineSubtitleService, SearchReport
from .subhd import SubHDSource
from .zimuku import ZimukuSource

__all__ = [
    "AssrtSource",
    "ShooterSource",
    "XunleiSource",
    "SubDLSource",
    "CaptchaChallenge",
    "DownloadResult",
    "OnlineSource",
    "OnlineSubtitleService",
    "OpenSubtitlesSource",
    "SearchReport",
    "SearchRequest",
    "SourceCandidate",
    "SourceError",
    "SourceErrorKind",
    "SourceFailure",
    "SourceSearchResult",
    "SourceState",
    "SubHDSource",
    "ZimukuSource",
    "evaluate_candidate",
    "merge_and_rank",
    "safe_public_link",
]
