"""Canonical media identity used by every subtitle workflow.

The functions in this module deliberately do not depend on host internals.  Host
gateways may provide an event row, a catalog row and (when available) NFO or
metadata dictionaries; all later subtitle code can then operate on one stable
model instead of inspecting those payloads again.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree

_EPISODE = re.compile(r"(?i)(?:^|[ ._\-])S(\d{1,2})[ ._\-]*E(\d{1,3})(?:\b|[ ._\-])")
_SEASON = re.compile(r"(?i)(?:^|[ ._\-])S(?:eason[ ._\-]*)?(\d{1,2})(?:\b|[ ._\-])")
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_EMPTY: tuple[Any, ...] = (None, "", [], (), {})
MIN_MEDIA_YEAR = 1878
MAX_MEDIA_YEAR = 2200


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any, *, maximum: int) -> int | None:
    if value in _EMPTY or isinstance(value, (bool, float)):
        return None
    text = str(value).strip()
    if not text.isdigit():
        return None
    number = int(text)
    return number if 0 < number <= maximum else None


def _year(value: Any) -> int | None:
    if value in _EMPTY or isinstance(value, bool):
        return None
    match = _YEAR.search(str(value))
    if not match:
        return None
    year = int(match.group(1))
    return year if MIN_MEDIA_YEAR <= year <= MAX_MEDIA_YEAR else None


def _media_type(value: Any) -> str:
    normalized = _text(value).casefold()
    if normalized in {"tv", "show", "series", "episode", "电视剧", "电视节目"}:
        return "tv"
    if normalized in {"movie", "film", "电影"}:
        return "movie"
    return normalized


def _aliases(value: Any) -> tuple[str, ...]:
    values: Iterable[Any]
    if isinstance(value, str):
        values = re.split(r"[|;/、]", value)
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = ()
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        title = _text(item)
        key = title.casefold()
        if title and key not in seen:
            seen.add(key)
            result.append(title)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class MediaIdentity:
    """Normalized identity; ``media_path`` is location, never identity authority."""

    title: str = ""
    english_title: str = ""
    original_title: str = ""
    aliases: tuple[str, ...] = ()
    year: int | None = None
    media_type: str = ""
    season: int | None = None
    episode: int | None = None
    tmdb_id: str = ""
    imdb_id: str = ""
    douban_id: str = ""
    original_language: str = ""
    media_path: str = ""
    warnings: tuple[str, ...] = field(default=(), compare=False)
    authoritative_fields: tuple[str, ...] = field(default=(), compare=False, repr=False)

    @property
    def is_episode(self) -> bool:
        return self.episode is not None or self.media_type == "tv" and self.season is not None

    def titles(self) -> tuple[str, ...]:
        return _aliases((self.title, self.english_title, self.original_title, *self.aliases))

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "english_title": self.english_title,
            "original_title": self.original_title,
            "aliases": list(self.aliases),
            "year": self.year,
            "media_type": self.media_type,
            "season": self.season,
            "episode": self.episode,
            "tmdb_id": self.tmdb_id,
            "imdb_id": self.imdb_id,
            "douban_id": self.douban_id,
            "original_language": self.original_language,
            "media_path": self.media_path,
            "warnings": list(self.warnings),
        }


_KEYS: dict[str, tuple[str, ...]] = {
    "title": ("title", "name", "media_name"),
    "english_title": ("english_title", "englishTitle", "title_en"),
    "original_title": ("original_title", "originalTitle", "originaltitle"),
    "aliases": ("aliases", "alias", "aka", "alternative_titles"),
    "year": ("year", "release_year"),
    "media_type": ("media_type", "type", "category"),
    "season": ("season", "season_number"),
    "episode": ("episode", "episode_number"),
    "tmdb_id": ("tmdb_id", "tmdb", "tmdbid"),
    "imdb_id": ("imdb_id", "imdb", "imdbid"),
    "douban_id": ("douban_id", "douban", "doubanid"),
    "original_language": ("original_language", "originalLanguage", "language"),
}


def _pick(data: Mapping[str, Any], field_name: str) -> Any:
    for key in _KEYS[field_name]:
        value = data.get(key)
        if value not in _EMPTY:
            return value
    return None


def _mapping_values(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": _text(_pick(data, "title")),
        "english_title": _text(_pick(data, "english_title")),
        "original_title": _text(_pick(data, "original_title")),
        "aliases": _aliases(_pick(data, "aliases")),
        "year": _year(_pick(data, "year")),
        "media_type": _media_type(_pick(data, "media_type")),
        "season": _number(_pick(data, "season"), maximum=99),
        "episode": _number(_pick(data, "episode"), maximum=999),
        "tmdb_id": _text(_pick(data, "tmdb_id")),
        "imdb_id": _text(_pick(data, "imdb_id")),
        "douban_id": _text(_pick(data, "douban_id")),
        "original_language": _text(_pick(data, "original_language")).casefold(),
    }


def parse_nfo(value: str | Mapping[str, Any] | None) -> dict[str, Any]:
    """Return identity fields from an NFO mapping or XML body."""

    if isinstance(value, Mapping):
        return _mapping_values(value)
    body = _text(value)
    if not body:
        return {}
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return {}

    kind = root.tag.rsplit("}", 1)[-1].casefold()
    raw = _nfo_fields(root, kind)
    raw["media_type"] = "tv" if kind in {"episodedetails", "tvshow"} else "movie"
    nodes = list(root.iter())
    raw["aliases"] = [
        node.text
        for node in nodes
        if node.tag.rsplit("}", 1)[-1].casefold() in {"alias", "alternativetitle"}
        and _text(node.text)
    ]
    for node in nodes:
        if node.tag.rsplit("}", 1)[-1].casefold() != "uniqueid":
            continue
        kind = _text(node.attrib.get("type")).casefold()
        if kind in {"tmdb", "imdb", "douban"} and _text(node.text):
            raw[f"{kind}_id"] = node.text
    return _mapping_values(raw)


def _nfo_fields(root: ElementTree.Element, kind: str) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for field_name, tags in {
        "title": ("showtitle", "title") if kind in {"episodedetails", "tvshow"} else ("title",),
        "english_title": ("englishtitle", "title_en"),
        "original_title": ("originaltitle",),
        "year": ("year", "premiered"),
        "season": ("season",),
        "episode": ("episode",),
        "tmdb_id": ("tmdbid",),
        "imdb_id": ("imdbid",),
        "douban_id": ("doubanid",),
        "original_language": ("language",),
    }.items():
        for tag in tags:
            node = next(
                (item for item in root.iter() if item.tag.rsplit("}", 1)[-1].casefold() == tag),
                None,
            )
            if node is not None and _text(node.text):
                raw[field_name] = node.text
                break
    return raw


def identity_from_path(path: str) -> dict[str, Any]:
    """Conservative last-resort extraction from a media path."""

    normalized = _text(path).replace("\\", "/")
    stem = PurePosixPath(normalized).stem
    episode = _EPISODE.search(f" {stem} ")
    season = episode or _SEASON.search(f" {stem} ")
    year = _YEAR.search(stem)
    cut = min(
        (match.start() for match in (episode, year) if match is not None),
        default=len(stem),
    )
    title = re.sub(r"[._]+", " ", stem[:cut]).strip(" -_([{（【")
    values: dict[str, Any] = {
        "title": title,
        "year": int(year.group(1)) if year else None,
    }
    if season:
        values["season"] = int(season.group(1))
        values["media_type"] = "tv"
    if episode:
        values["episode"] = int(episode.group(2))
    return values


def media_path_key(path: str) -> str:
    """Normalize equivalent event/catalog path spellings without changing the path."""

    value = posixpath.normpath(_text(path).replace("\\", "/"))
    return value.casefold() if re.match(r"^[A-Za-z]:/", value) else value


def _canonical(field_name: str, value: Any) -> Any:
    if field_name == "year":
        return _year(value)
    if field_name == "season":
        return _number(value, maximum=99)
    if field_name == "episode":
        return _number(value, maximum=999)
    if field_name == "media_type":
        return _media_type(value)
    if field_name == "aliases":
        return _aliases(value)
    return _text(value)


def _event_authority(
    row: Mapping[str, Any], authoritative: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = row.get("identity_inferred_fields", ())
    inferred_fields = {str(item) for item in raw} if isinstance(raw, (list, tuple, set)) else set()
    inferred_values = {key: authoritative[key] for key in inferred_fields if key in authoritative}
    for key in inferred_fields:
        if key in authoritative:
            authoritative[key] = () if key == "aliases" else None
    return authoritative, inferred_values


def _resolve_field(
    field_name: str,
    authoritative: Mapping[str, Any],
    candidates: Iterable[Any],
    *,
    warn_conflicts: bool,
) -> tuple[Any, str]:
    current = authoritative[field_name]
    available = [candidate for candidate in candidates if candidate not in _EMPTY]
    warning = ""
    if warn_conflicts and current not in _EMPTY:
        expected = _canonical(field_name, current)
        if any(_canonical(field_name, candidate) != expected for candidate in available):
            warning = f"identity_conflict:{field_name}"
    if current in _EMPTY and available:
        current = available[0]
    return _canonical(field_name, current), warning


def resolve_identity(
    row: Mapping[str, Any],
    *,
    event_authoritative: bool = False,
    nfo: str | Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> MediaIdentity:
    """Resolve an event or catalog row using strict source precedence.

    Event rows use ``row['identity']`` as the authority.  Catalog rows use their
    structured ``identity`` first when present, then their ordinary columns.
    NFO and metadata only fill gaps.  Path parsing is always the last resort.
    """

    path = _text(row.get("media_path") or row.get("path") or row.get("relative_media_path"))
    structured = row.get("identity")
    structured = structured if isinstance(structured, Mapping) else {}
    row_values = _mapping_values(row)
    authoritative = _mapping_values(structured)
    if event_authoritative:
        authoritative, inferred_values = _event_authority(row, authoritative)
    else:
        inferred_values = {}
        authoritative = {
            key: value if value not in _EMPTY else row_values[key]
            for key, value in authoritative.items()
        }
    supplements = (
        parse_nfo(nfo or row.get("nfo")),
        _mapping_values(metadata or {}),
        identity_from_path(path),
        inferred_values,
    )
    result, warnings = _resolved_identity_fields(
        row_values, authoritative, supplements, event_authoritative
    )

    return _media_identity_result(path, result, warnings, authoritative, event_authoritative)


def _media_identity_result(
    path: str,
    result: dict[str, Any],
    warnings: list[str],
    authoritative: dict[str, Any],
    event_authoritative: bool,
) -> MediaIdentity:
    if not result["media_type"]:
        result["media_type"] = (
            "tv" if result["season"] is not None or result["episode"] is not None else "movie"
        )
    authority = tuple(
        field_name
        for field_name in _KEYS
        if event_authoritative and authoritative[field_name] not in _EMPTY
    )
    return MediaIdentity(
        media_path=path,
        warnings=tuple(warnings),
        authoritative_fields=authority,
        **result,
    )


def _resolved_identity_fields(
    row_values: dict[str, Any],
    authoritative: dict[str, Any],
    supplements: tuple[dict[str, Any], ...],
    event_authoritative: bool,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    result: dict[str, Any] = {}
    for field_name in _KEYS:
        candidates = [
            row_values[field_name],
            *(source.get(field_name) for source in supplements),
        ]
        result[field_name], warning = _resolve_field(
            field_name,
            authoritative,
            candidates,
            warn_conflicts=event_authoritative,
        )
        if warning:
            warnings.append(warning)

    return result, warnings


def supplement_identity(identity: MediaIdentity, supplement: Mapping[str, Any]) -> MediaIdentity:
    """Fill event gaps without promoting earlier path guesses to authority."""

    authoritative = {
        field_name: getattr(identity, field_name) for field_name in identity.authoritative_fields
    }
    resolved = resolve_identity(
        {"media_path": identity.media_path, "identity": authoritative},
        event_authoritative=True,
        metadata=supplement,
    )
    return replace(
        resolved,
        warnings=tuple(dict.fromkeys((*identity.warnings, *resolved.warnings))),
    )


def identity_with_warning(identity: MediaIdentity, warning: str) -> MediaIdentity:
    return replace(
        identity,
        warnings=tuple(dict.fromkeys((*identity.warnings, _text(warning)))),
    )


def merge_event_identities(current: MediaIdentity, incoming: MediaIdentity) -> MediaIdentity:
    """Merge duplicate event rows without losing either row's authoritative fields."""

    authority: dict[str, Any] = {}
    warnings = list((*current.warnings, *incoming.warnings))
    for field_name in (*current.authoritative_fields, *incoming.authoritative_fields):
        value = (
            getattr(current, field_name)
            if field_name in current.authoritative_fields
            else getattr(incoming, field_name)
        )
        existing = authority.get(field_name)
        if existing not in _EMPTY and _canonical(field_name, existing) != _canonical(
            field_name, value
        ):
            warnings.append(f"identity_conflict:{field_name}")
            continue
        authority[field_name] = value
    supplement = current.as_dict()
    for field_name in _KEYS:
        value = getattr(incoming, field_name)
        if value not in _EMPTY and (
            supplement.get(field_name) in _EMPTY or field_name in incoming.authoritative_fields
        ):
            supplement[field_name] = value
    resolved = resolve_identity(
        {"media_path": current.media_path, "identity": authority},
        event_authoritative=True,
        metadata=supplement,
    )
    return replace(
        resolved,
        warnings=tuple(dict.fromkeys((*warnings, *resolved.warnings))),
    )
