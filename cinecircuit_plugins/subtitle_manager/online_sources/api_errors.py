"""Redact credential-bearing API URLs while retaining retry semantics."""

import httpx

from .base import SourceError, SourceErrorKind, SourceFailure, http_failure


def api_failure(provider, exc, manual_url=""):
    restricted = http_failure(provider, exc, manual_url)
    if restricted:
        return restricted
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        kind, message, retry = SourceErrorKind.TIMEOUT, "字幕接口请求超时", True
    elif isinstance(exc, httpx.HTTPError):
        kind, message, retry = SourceErrorKind.NETWORK, "字幕接口请求失败", True
    else:
        kind, message, retry = SourceErrorKind.PROTOCOL, "字幕接口返回无效数据", False
    return SourceFailure(SourceError(provider, kind, message, retry, manual_url))
