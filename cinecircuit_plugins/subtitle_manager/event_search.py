"""Convert selected completion-event media to the canonical subtitle identity."""

from pathlib import PurePosixPath
from typing import Any

from .identity import (
    MediaIdentity,
    media_path_key,
    merge_event_identities,
    resolve_identity,
)
from .search_plan import SearchPlan, build_search_plan


def event_identities(data: dict[str, Any]) -> list[MediaIdentity]:
    """Resolve and de-duplicate only media explicitly carried by an event."""

    identities: dict[str, MediaIdentity] = {}
    rows = data.get("items")
    if not isinstance(rows, list):
        return []
    for row in rows:
        if not isinstance(row, dict):
            continue
        identity = resolve_identity(row, event_authoritative=True)
        if identity.media_path and identity.title:
            key = media_path_key(identity.media_path)
            existing = identities.get(key)
            identities[key] = merge_event_identities(existing, identity) if existing else identity
    return list(identities.values())


def event_search_plans(data: dict[str, Any]) -> list[SearchPlan]:
    """Generate automatic plans; an event never opts into a season package."""

    return [build_search_plan(identity, season_pack=False) for identity in event_identities(data)]


def catalog_identity(row: dict[str, Any]) -> MediaIdentity:
    """Convert one physical-video or STRM catalog row to the same model."""

    prepared = dict(row)
    structured = row.get("identity")
    structured_title = (
        str(structured.get("title") or "").strip()
        if isinstance(structured, dict)
        else ""
    )
    catalog_title = str(row.get("title") or "").strip()
    # Recorded catalogs may expose the remote video filename as ``title``
    # before metadata detail has loaded. It is a display label, not identity
    # authority; let the conservative path parser remove year/release tokens.
    media_suffixes = {"mkv", "mp4", "avi", "mov", "wmv", "m4v", "ts", "m2ts", "strm"}
    if (
        not structured_title
        and PurePosixPath(catalog_title.replace("\\", "/")).suffix.lstrip(".").casefold()
        in media_suffixes
    ):
        # All three keys are title aliases in ``resolve_identity``. Recorded
        # rows commonly duplicate the same filename into both title and name.
        for key in ("title", "name", "media_name"):
            prepared.pop(key, None)
    return resolve_identity(prepared, event_authoritative=False)


def media_targets(data: dict[str, Any]) -> list[dict[str, str]]:
    """Legacy target dictionaries backed by canonical identities.

    The spaced ``S01 E02`` keyword is retained until the legacy plugin caller is
    switched to :func:`event_search_plans`; all new searches use strict S01E02.
    """

    targets: list[dict[str, str]] = []
    for identity in event_identities(data):
        keyword = identity.title
        if identity.season is not None:
            keyword += f" S{identity.season:02d}"
        if identity.episode is not None:
            keyword += f" E{identity.episode:02d}"
        targets.append(
            {
                "media_path": identity.media_path,
                "keyword": keyword,
                "title": identity.title,
                "year": str(identity.year or ""),
                "season": str(identity.season if identity.season is not None else ""),
                "episode": str(identity.episode if identity.episode is not None else ""),
                "language": identity.original_language,
            }
        )
    return targets
