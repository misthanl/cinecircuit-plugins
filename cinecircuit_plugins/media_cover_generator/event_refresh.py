from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any

from app.modules.plugins.contracts import PluginContext, PluginEvent


SOURCE_EVENTS = (
    "organizer.completed",
    "sync.completed",
    "metadata.scrape.completed",
)
REFRESH_EVENT = "media-cover.media-refresh"
_SPACE = re.compile(r"\s+")


def schedule_refresh(context: PluginContext, event: PluginEvent) -> dict[str, object]:
    """Schedule a deduplicated refresh without blocking the event producer."""

    completion_id = str(
        event.data.get("completion_id")
        or event.data.get("operation_id")
        or event.data.get("job_id")
        or event.data.get("completed_at")
        or ""
    )
    if not completion_id:
        return {"status": "skipped", "reason": "missing_completion_id"}
    completion_key = sha256(
        f"{event.type}:{event.data.get('provider_key', '')}:{completion_id}".encode()
    ).hexdigest()
    delay = max(0, min(3600, int(context.config.get("delay", 60))))
    payload = {**event.data, "_source_event": event.type}
    if not context.jobs.schedule_event(
        REFRESH_EVENT,
        payload,
        key=f"media:{completion_key}",
        delay_seconds=delay,
    ):
        return {"status": "skipped", "reason": "duplicate_media_completion"}
    return {"status": "pending", "delay_seconds": delay}


async def locate_target_libraries(
    context: PluginContext, data: dict[str, Any]
) -> dict[str, set[str]]:
    """Locate only configured libraries containing media named by the completion event."""

    targets = _event_targets(data)
    server_ids = _strings(context.config.get("selected_servers"))
    if not targets or not server_ids:
        return {}
    configured = _configured_targets(context.config, server_ids)
    located: dict[str, set[str]] = {}
    for server_id in server_ids:
        response = await context.media_servers.libraries(server_id)
        libraries = list(response.get("items") or [])
        allowed = configured.get(server_id)
        if allowed is not None:
            libraries = [
                library for library in libraries if str(library.get("id") or "") in allowed
            ]
        for library in libraries[:50]:
            library_id = str(library.get("id") or "")
            if library_id and await _library_contains_target(
                context, server_id, library_id, targets
            ):
                located.setdefault(server_id, set()).add(library_id)
    return located


async def _library_contains_target(
    context: PluginContext,
    server_id: str,
    library_id: str,
    targets: list[dict[str, Any]],
) -> bool:
    start = 0
    for _page in range(20):
        response = await context.media_servers.metadata_items(
            server_id,
            library_id,
            start=start,
            limit=500,
            include_types=("Movie", "Series"),
        )
        items = list(response.get("items") or [])
        if any(_matches(item, target) for item in items for target in targets):
            return True
        start += len(items)
        if not items or start >= int(response.get("total") or 0):
            break
    return False


def _configured_targets(
    config: dict[str, Any], server_ids: list[str]
) -> dict[str, set[str] | None]:
    result: dict[str, set[str] | None] = {server_id: None for server_id in server_ids}
    raw_targets = config.get("library_targets") or []
    if raw_targets:
        result = {server_id: set() for server_id in server_ids}
        for raw in raw_targets:
            try:
                server_id, library_id = json.loads(str(raw))
            except (TypeError, ValueError):
                continue
            library_ids = result.get(server_id)
            if library_ids is not None and str(library_id).strip():
                library_ids.add(str(library_id))
    return result


def _event_targets(data: dict[str, Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for value in data.get("items") or []:
        if not isinstance(value, dict):
            continue
        identity = value.get("identity")
        target = dict(identity) if isinstance(identity, dict) else {}
        if not str(target.get("title") or "").strip():
            title, year = _identity_from_path(str(value.get("relative_media_path") or ""))
            target["title"] = title
            target.setdefault("year", year)
        external_ids = dict(target.get("external_ids") or {})
        if target.get("tmdb_id"):
            external_ids["tmdb"] = str(target["tmdb_id"])
        target["external_ids"] = external_ids
        if target.get("title") or external_ids:
            targets.append(target)
    return targets[:500]


def _identity_from_path(value: str) -> tuple[str, str]:
    parts = [part for part in value.replace("\\", "/").split("/") if part]
    if not parts:
        return "", ""
    stem = re.sub(r"\.[^.]+$", "", parts[-1])
    if re.search(r"(?i)S\d{1,2}E\d{1,3}", stem):
        candidates = [
            part
            for part in reversed(parts[:-1])
            if not re.search(r"(?i)(?:season\s*\d+|第\s*\d+\s*季)", part)
        ]
        stem = candidates[0] if candidates else stem
    elif len(parts) > 1 and re.search(r"(?:19|20)\d{2}", parts[-2]):
        stem = parts[-2]
    year_match = re.search(r"(?:19|20)\d{2}", stem)
    year = year_match.group(0) if year_match else ""
    title = re.sub(r"[\[(（]?\s*(?:19|20)\d{2}\s*[\])）]?", "", stem)
    return re.sub(r"[._]+", " ", title).strip(" -_[]【】()（）"), year


def _matches(media: dict[str, Any], target: dict[str, Any]) -> bool:
    expected_ids = {
        str(key).casefold(): str(value)
        for key, value in (target.get("external_ids") or {}).items()
        if str(value).strip()
    }
    actual_ids = {
        str(key).casefold(): str(value)
        for key, value in (media.get("provider_ids") or {}).items()
        if str(value).strip()
    }
    if any(actual_ids.get(key) == value for key, value in expected_ids.items()):
        return True
    expected_title = _key(target.get("title"))
    if not expected_title or expected_title not in {
        _key(media.get("name")),
        _key(media.get("original_title")),
    }:
        return False
    expected_year = str(target.get("year") or "")[:4]
    actual_year = str(media.get("year") or "")[:4]
    return not expected_year or not actual_year or expected_year == actual_year


def _key(value: object) -> str:
    return _SPACE.sub("", str(value or "")).casefold()


def _strings(value: object) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else []
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))
