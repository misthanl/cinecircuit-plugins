"""Compatibility entry point that delegates downloads to online source adapters."""

from typing import Any
from collections.abc import Callable
from .online_sources.base import OnlineSource

from .online_sources import (
    AssrtSource,
    ShooterSource,
    XunleiSource,
    SubDLSource,
    OpenSubtitlesSource,
    SourceCandidate,
    SourceFailure,
    SubHDSource,
    ZimukuSource,
)


async def download_files(client: Any, config: dict, candidate: dict) -> list[tuple[str, bytes]]:
    provider = str(candidate.get("provider") or "")
    source_types: dict[str, Callable[[Any, dict], OnlineSource]] = {
        "SubDL": SubDLSource,
        "射手影音": ShooterSource,
        "迅雷看看": XunleiSource,
        "ASSRT": AssrtSource,
        "OpenSubtitles": OpenSubtitlesSource,
        "SubHD": SubHDSource,
        "字幕库": ZimukuSource,
    }
    source_type = source_types.get(provider)
    if source_type is None:
        raise ValueError("字幕来源未启用")
    source = source_type(client, config)
    internal = SourceCandidate(
        provider=provider,
        result_id=str(candidate.get("id") or candidate.get("result_id") or ""),
        title=str(candidate.get("title") or ""),
        detail_url=str(candidate.get("url") or candidate.get("detail_url") or ""),
        downloadable=True,
        download_ref=(
            tuple(candidate.get("files") or ())
            if provider == "OpenSubtitles"
            else candidate.get("download_ref") or candidate.get("id") or candidate.get("url")
        ),
        matched=True,
    )
    try:
        downloaded = await source.download(internal)
    except SourceFailure as error:
        raise ValueError(error.error.message) from error
    if downloaded.error:
        raise ValueError(downloaded.error.message)
    return list(downloaded.files)
