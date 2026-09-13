"""Event-scoped automatic downloads use the public sidecar write gateway."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Any
from zipfile import BadZipFile

import httpx
from app.modules.plugins.runtime_services import http_client

from .source_download import download_files
from .subtitle_files import (
    FORMATS,
    language_tag,
    matches,
    output_format,
    subtitle_text,
    unpack,
)
from .subtitle_priority import bilingual, file_priority, language_kind, priority
from .text_formats import UnsupportedSubtitle

MAX_CANDIDATES = 20
MAX_POOL_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class PreparationContext:
    config: dict[str, Any]
    target: dict[str, Any]
    candidate: dict[str, Any]


@dataclass(slots=True)
class CollectionContext:
    context: Any
    preparation: PreparationContext
    client: Any
    downloader: Callable[[Any], Awaitable[Any]] | None
    pool: list[Any]
    result: dict[str, Any]


def candidate_value(candidate: Any, key: str, default: Any = "") -> Any:
    return (
        candidate.get(key, default)
        if isinstance(candidate, dict)
        else getattr(candidate, key, default)
    )


def candidate_dict(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return candidate
    serializer = getattr(candidate, "as_dict", None)
    result = serializer() if callable(serializer) else {}
    metadata = getattr(candidate, "metadata", {})
    if metadata.get("file_match"):
        result["_file_match"] = metadata["file_match"]
    return result


def language_priority(config: dict[str, Any], language: str) -> int:
    return priority(config, language)


def prepared_files(
    preparation: PreparationContext,
    files: list[tuple[str, bytes]],
    *,
    errors: list[str] | None = None,
    annotations: dict[int, dict[str, Any]] | None = None,
) -> list[tuple[str, str, bytes]]:
    prepared: list[tuple[str, str, bytes]] = []
    unpacked = [item for filename, content in files for item in unpack(content, filename)]
    checked = replace(
        preparation,
        candidate={**preparation.candidate, "_single_payload": len(unpacked) == 1},
    )
    for name, data in unpacked:
        info: dict[str, Any] = {}
        try:
            value = prepare_file(checked, name, data, info=info)
        except UnsupportedSubtitle as error:
            if errors is None:
                raise
            errors.append(str(error))
            continue
        if value is not None:
            prepared.append(value)
            if annotations is not None:
                annotations[id(value)] = info
    return sorted(prepared, key=lambda value: file_priority(preparation.config, value))


def prepare_file(
    preparation: PreparationContext,
    filename: str,
    content: bytes,
    *,
    info: dict[str, Any] | None = None,
) -> tuple[str, str, bytes] | None:
    config, candidate = preparation.config, preparation.candidate
    extension = PurePosixPath(filename).suffix.lstrip(".").lower()
    if extension not in FORMATS or not matches(preparation.target, candidate, filename):
        return None
    text = subtitle_text(content, extension)
    original_text = text
    language = language_tag(filename, candidate, text)
    if config.get("auto_multi_subtitle_mode") == "chinese_all" and not language.startswith("zh"):
        return None
    if config.get("traditional_to_simplified") and language in {"zh-TW", "zh"}:
        from ._vendor.opencc import OpenCC

        text = OpenCC("t2s").convert(text)
        language = "zh-CN"
    final_format = output_format(extension)
    detected_kind = language_kind(language, text, final_format)
    if detected_kind in {"zh-CN-en", "zh-TW-en"}:
        language = detected_kind
    if info is not None:
        source = str(candidate.get("provider") or "")
        info.update(
            provider=source if source in {"ASSRT", "OpenSubtitles", "SubHD", "字幕库", "SubDL", "射手影音", "迅雷看看"} else "—",
            language=detected_kind,
            format=final_format.upper(),
            bilingual=bilingual(text, final_format),
            converted=text != original_text,
        )
    return final_format, language, text.encode("utf-8")


def _result(media_path: str) -> dict[str, Any]:
    return {
        "media_path": media_path,
        "saved": [],
        "skipped": 0,
        "failed": 0,
        "details": [],
        "errors": [],
    }


def _record_error(result: dict[str, Any], provider: str, kind: str, message: str) -> None:
    result["errors"].append({"provider": provider, "kind": kind, "message": message})


async def _downloaded_files(
    candidate: Any,
    *,
    client: Any,
    config: dict[str, Any],
    downloader: Callable[[Any], Awaitable[Any]] | None,
    result: dict[str, Any],
) -> list[tuple[str, bytes]]:
    if downloader is None:
        if client is None:
            raise RuntimeError("字幕下载客户端未初始化")
        return await download_files(client, config, candidate_dict(candidate))
    downloaded = await downloader(candidate)
    if getattr(downloaded, "error", None):
        error = downloaded.error
        _record_error(result, error.provider, error.kind.value, error.message)
        raise ValueError(error.message)
    return list(getattr(downloaded, "files", ()))


def _add_prepared(
    pool: list, prepared: list, annotations: dict, config: dict, result: dict
) -> None:
    pool.extend((file_priority(config, value), value, annotations[id(value)]) for value in prepared)
    pool.sort(key=lambda row: row[0])
    total = sum(len(row[1][2]) for row in pool)
    while total > MAX_POOL_BYTES:
        total -= len(pool.pop()[1][2])
        result["skipped"] += 1


async def _collect_candidate(
    collection: CollectionContext,
    candidate: Any,
) -> None:
    context = collection.context
    preparation = collection.preparation
    result = collection.result
    provider = str(candidate_value(candidate, "provider") or "")
    try:
        files = await _downloaded_files(
            candidate,
            client=collection.client,
            config=preparation.config,
            downloader=collection.downloader,
            result=result,
        )
        format_errors: list[str] = []
        annotations: dict[int, dict[str, Any]] = {}
        prepared = prepared_files(
            replace(preparation, candidate=candidate_dict(candidate)),
            files,
            errors=format_errors,
            annotations=annotations,
        )
        for message in format_errors:
            result["failed"] += 1
            _record_error(result, provider, "format", message)
            context.logger.warning("字幕格式处理失败：%s", message)
        if not prepared:
            result["skipped"] += 1
        _add_prepared(collection.pool, prepared, annotations, preparation.config, result)
    except UnsupportedSubtitle as error:
        result["failed"] += 1
        _record_error(result, provider, "format", str(error))
        context.logger.warning("字幕格式处理失败：%s", error)
    except (httpx.HTTPError, OSError, ValueError, BadZipFile, KeyError):
        result["failed"] += 1
        if not result["errors"] or result["errors"][-1].get("provider") != provider:
            _record_error(result, provider, "download", "字幕候选下载、解包或匹配失败")
        context.logger.warning("一个字幕候选下载或保存失败，继续尝试其他候选")


async def _collect_candidates(
    context: Any,
    preparation: PreparationContext,
    candidates: list[Any],
    downloader: Callable[[Any], Awaitable[Any]] | None,
    result: dict[str, Any],
) -> list:
    pool: list = []
    async with AsyncExitStack() as stack:
        client = None
        if downloader is None:
            client = await stack.enter_async_context(
                http_client(
                    timeout=30,
                    use_application_proxy=bool(context.config.get("online_use_proxy")),
                )
            )
        collection = CollectionContext(context, preparation, client, downloader, pool, result)
        for candidate in candidates:
            await _collect_candidate(collection, candidate)
    return pool


async def _save_pool(
    context: Any, target: dict, pool: list, existing: set[str], result: dict
) -> dict:
    stem = PurePosixPath(target["media_path"].replace("\\", "/")).stem
    seen: set[str] = set()
    for _, (extension, language, content), info in pool:
        output_name = f"{stem}.{language}.{extension}".casefold()
        if output_name in seen or (
            output_name in existing and not context.config.get("overwrite_existing", False)
        ):
            result["skipped"] += 1
            continue
        try:
            saved = await context.media_files.write_subtitle(
                target["media_path"],
                content,
                extension=extension,
                language=language,
                overwrite=bool(context.config.get("overwrite_existing", False)),
            )
        except (OSError, ValueError):
            result["failed"] += 1
            _record_error(result, str(info.get("provider") or ""), "save", "字幕写入失败")
            context.logger.warning("字幕保存失败，继续尝试其他候选")
            continue
        seen.add(output_name)
        result["saved"].append(saved)
        result["details"].append({**info, "status": "saved"})
        if str(context.config.get("auto_multi_subtitle_mode") or "best") == "best":
            break
    return result


async def save_candidates(
    context: Any,
    target: dict[str, Any],
    candidates: list[Any],
    *,
    downloader: Callable[[Any], Awaitable[Any]] | None = None,
) -> dict[str, Any]:
    result = _result(target["media_path"])
    try:
        inventory = await context.media_files.subtitles(target["media_path"])
    except (OSError, ValueError):
        return {**result, "failed": 1, "reason": "media_path_unavailable"}
    existing = {str(item.get("name") or "").casefold() for item in inventory.get("items") or []}
    ordered = sorted(
        candidates[:MAX_CANDIDATES],
        key=lambda value: language_priority(
            context.config, str(candidate_value(value, "language") or "")
        ),
    )
    pool = await _collect_candidates(
        context,
        PreparationContext(context.config, target, {}),
        ordered,
        downloader,
        result,
    )
    return await _save_pool(context, target, pool, existing, result)
