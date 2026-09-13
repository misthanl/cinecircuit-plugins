"""Validate downloaded files and rank safe preview candidates before persistence."""

from typing import Any

from .automatic_download import PreparationContext, prepare_file
from .identity import MediaIdentity
from .online_sources.base import SourceCandidate, DownloadResult
from .preview_store import PreviewFile
from .subtitle_files import unpack
from .subtitle_priority import file_priority
from .text_formats import UnsupportedSubtitle


def prepare_previews(
    config: dict[str, Any],
    identity: MediaIdentity,
    candidate: SourceCandidate,
    downloaded: DownloadResult,
) -> list[PreviewFile]:
    target = identity.as_dict()
    if identity.is_episode:
        target["keyword"] = f"{identity.title} S{identity.season:02d}E{identity.episode:02d}"
    else:
        target["keyword"] = identity.title
    unpacked = [
        item for filename, content in downloaded.files for item in unpack(content, filename)
    ]
    checked_candidate = {
        **candidate.as_dict(),
        "_file_match": candidate.metadata.get("file_match"),
        "_identity_match": candidate.metadata.get("identity_match"),
        "_single_payload": len(unpacked) == 1,
    }
    previews, format_errors = _prepare_files(config, target, checked_candidate, unpacked)
    if not previews:
        detail = format_errors[0] if format_errors else "下载内容中没有匹配当前媒体的字幕"
        raise ValueError(detail)
    previews.sort(
        key=lambda item: file_priority(
            config,
            (item.extension, item.language, item.content),
        )
    )
    return previews


def _prepare_files(
    config: dict[str, Any],
    target: dict[str, Any],
    candidate: dict[str, Any],
    unpacked: list[tuple[str, bytes]],
) -> tuple[list[PreviewFile], list[str]]:
    previews: list[PreviewFile] = []
    format_errors: list[str] = []
    for source_name, data in unpacked:
        info: dict[str, Any] = {}
        try:
            prepared = prepare_file(
                PreparationContext(config, target, candidate),
                source_name,
                data,
                info=info,
            )
        except UnsupportedSubtitle as error:
            format_errors.append(str(error))
            continue
        if prepared:
            extension, language, prepared_content = prepared
            previews.append(PreviewFile(extension, language, prepared_content, source_name, info))
    return previews, format_errors
