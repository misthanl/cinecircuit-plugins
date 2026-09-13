"""Strict candidate identity matching, de-duplication and ranking."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from .base import SearchRequest, SourceCandidate
from ..video_hash import identity_value, matches_file

_EPISODE = re.compile(
    r"(?i)(?:\bS(?P<s>\d{1,2})[ ._-]*E(?P<e>\d{1,3})\b|"
    r"第\s*(?P<cs>\d{1,2})\s*季\s*第\s*(?P<ce>\d{1,3})\s*集)"
)
_YEAR = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
_SOURCE_ORDER = {"ASSRT": 4, "OpenSubtitles": 3, "SubHD": 2, "字幕库": 1}
_FORMAT_ORDER = {"ass": 5, "ssa": 4, "srt": 3, "vtt": 2, "sub": 1}
_MIN_NON_LATIN_TITLE_LENGTH = 2


def _value(identity: Any, name: str, default: Any = None) -> Any:
    return (
        identity.get(name, default)
        if isinstance(identity, dict)
        else getattr(identity, name, default)
    )


def _titles(identity: Any) -> list[str]:
    values: list[Any] = [
        _value(identity, "title", ""),
        _value(identity, "english_title", ""),
        _value(identity, "original_title", ""),
    ]
    aliases = _value(identity, "aliases", ()) or _value(identity, "alias", ()) or ()
    values.extend([aliases] if isinstance(aliases, str) else aliases)
    return [str(item) for item in values if str(item).strip()]


def normalize_title(value: str) -> str:
    folded = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in folded if character.isalnum())


def _title_matches(alias: str, candidate: str) -> bool:
    """Avoid accepting short Latin titles as arbitrary word fragments."""
    alias_text = unicodedata.normalize("NFKC", alias).casefold()
    candidate_text = unicodedata.normalize("NFKC", candidate).casefold()
    alias_tokens = re.findall(r"[^\W_]+", alias_text, re.UNICODE)
    candidate_tokens = re.findall(r"[^\W_]+", candidate_text, re.UNICODE)
    if not alias_tokens:
        return False
    if all(token.isascii() for token in alias_tokens):
        width = len(alias_tokens)
        return any(
            candidate_tokens[index : index + width] == alias_tokens
            for index in range(len(candidate_tokens) - width + 1)
        )
    normalized_alias = normalize_title(alias_text)
    return len(
        normalized_alias
    ) >= _MIN_NON_LATIN_TITLE_LENGTH and normalized_alias in normalize_title(candidate_text)


def _episode_fields(
    candidate: SourceCandidate,
) -> tuple[int | None, int | None, bool]:
    season, episode = candidate.season, candidate.episode
    match = _EPISODE.search(candidate.title)
    if not match:
        return season, episode, False
    title_season = int(match.group("s") or match.group("cs"))
    title_episode = int(match.group("e") or match.group("ce"))
    conflict = (
        season is not None
        and episode is not None
        and (season != title_season or episode != title_episode)
    )
    resolved_season = season if season is not None else title_season
    resolved_episode = episode if episode is not None else title_episode
    return resolved_season, resolved_episode, conflict


def _reject(
    candidate: SourceCandidate,
    reason: str,
    *,
    year: int | None = None,
    season: int | None = None,
    episode: int | None = None,
) -> SourceCandidate:
    return replace(
        candidate,
        year=year if year is not None else candidate.year,
        season=season,
        episode=episode,
        matched=False,
        score=0,
        match_reason=reason,
    )


def _match_score(
    candidate: SourceCandidate,
    request: SearchRequest,
    title_hit: str,
    year: int | None,
) -> tuple[float, str]:
    score = 70.0 if title_hit or not _titles(request.identity) else 0.0
    reasons = [f"片名命中 {title_hit}" if title_hit else "无片名可供校验"]
    if request.season is not None:
        score += 18
        reasons.append("季集完全匹配")
    elif request.year and year == request.year:
        score += 12
        reasons.append("年份匹配")
    if request.language and _language_matches(request.language, candidate.language):
        score += 6
        reasons.append("语言匹配")
    score += _FORMAT_ORDER.get(candidate.subtitle_format.casefold(), 0) * 0.5
    score += _SOURCE_ORDER.get(candidate.provider, 0) * 0.1
    return round(score, 2), "；".join(reasons)


def _has_exact_identity_match(candidate: SourceCandidate, request: SearchRequest) -> bool:
    match = candidate.metadata.get("identity_match")
    if not isinstance(match, dict):
        return False
    kind = str(match.get("kind") or "")
    value = str(match.get("value") or "").removeprefix("tt")
    expected = {
        "tmdb_id": request.tmdb_id,
        "imdb_id": request.imdb_id.removeprefix("tt"),
    }.get(kind, "")
    return bool(expected and value == expected)


def evaluate_candidate(candidate: SourceCandidate, request: SearchRequest) -> SourceCandidate:
    file_match = candidate.metadata.get("file_match")
    if file_match is not None:
        if matches_file(file_match, identity_value(request.identity, "media_path")):
            return replace(candidate, matched=True, score=100, match_reason="视频文件哈希匹配")
        # Hash-source candidates belong to the exact sampled media file. Never
        # let a restored candidate fall through to the weaker title matcher
        # after the user switches to another media item.
        return _reject(candidate, "视频文件哈希与当前媒体不匹配")
    title = candidate.title
    season, episode, conflict = _episode_fields(candidate)
    if conflict:
        return _reject(
            candidate,
            "候选结构化季集与标题季集冲突",
            season=candidate.season,
            episode=candidate.episode,
        )
    aliases = _titles(request.identity)
    comparable_title = _EPISODE.sub(" ", _YEAR.sub(" ", title))
    title_hit = next((alias for alias in aliases if _title_matches(alias, comparable_title)), "")
    if aliases and not title_hit:
        return _reject(candidate, "片名未命中标题或可信别名", season=season, episode=episode)
    if (request.season is not None or request.episode is not None) and (
        season != request.season or episode != request.episode
    ):
        expected = f"S{request.season or 0:02d}E{request.episode or 0:02d}"
        actual = (
            f"S{season:02d}E{episode:02d}"
            if season is not None and episode is not None
            else "未标明季集"
        )
        return _reject(
            candidate,
            f"单集季集不匹配：需要 {expected}，候选为 {actual}",
            season=season,
            episode=episode,
        )
    return _evaluate_candidate_year(candidate, request, title_hit, season, episode)


def _evaluate_candidate_year(
    candidate: SourceCandidate,
    request: SearchRequest,
    title_hit: str,
    season: int | None,
    episode: int | None,
) -> SourceCandidate:
    title = candidate.title
    years = {int(value) for value in _YEAR.findall(title)}
    year = candidate.year or (next(iter(years)) if len(years) == 1 else None)
    explicit_year_conflict = bool(request.year and years and years != {request.year})
    exact_identity_match = _has_exact_identity_match(candidate, request)
    if (
        request.season is None
        and request.episode is None
        and request.year
        and (explicit_year_conflict or (year and year != request.year))
        and not exact_identity_match
    ):
        return _reject(
            candidate,
            f"年份冲突：需要 {request.year}，候选为 {year}",
            year=year,
        )
    score, reason = _match_score(candidate, request, title_hit, year)
    if exact_identity_match and request.year and year and year != request.year:
        reason += "；精确 ID 匹配，保留年份不同的候选"
    return replace(
        candidate,
        year=year,
        season=season,
        episode=episode,
        matched=True,
        score=score,
        match_reason=reason,
    )


def _language_matches(expected: str, actual: str) -> bool:
    expected_tokens = {token for token in re.split(r"[,/ _-]+", expected.casefold()) if token}
    actual_tokens = {token for token in re.split(r"[,/ _-]+", actual.casefold()) if token}
    aliases = {
        "zh": {"chi", "zho", "chs", "cht", "zh-cn", "zh-tw", "中文", "简体", "繁体"},
        "en": {"eng", "english", "英语"},
    }
    expanded = set(expected_tokens)
    for token in expected_tokens:
        expanded.update(aliases.get(token, set()))
    return bool(expanded & actual_tokens)


def _language_preference_rank(expected: str, actual: str) -> int:
    requested = [item.strip().casefold() for item in expected.split(",") if item.strip()]
    normalized = actual.strip().casefold().replace("_", "-")
    aliases = {
        "zh-cn": {"zh-cn", "zh-hans", "zh", "chi", "zho", "chs", "chinese"},
        "zh-tw": {"zh-tw", "zh-hant", "zh", "chi", "zho", "cht", "chinese"},
        "zh-ca": {"zh-ca", "zh", "chi", "zho", "chinese"},
        "ze": {"ze", "zh-cn-en", "zh-tw-en"},
        "en": {"en", "eng", "english"},
        "ja": {"ja", "jpn", "japanese"},
        "ko": {"ko", "kor", "korean"},
    }
    for index, language in enumerate(requested):
        if normalized in aliases.get(language, {language}):
            return index
    return len(requested) + 1


def merge_and_rank(
    pairs: Iterable[tuple[SourceCandidate, SearchRequest]],
) -> tuple[SourceCandidate, ...]:
    merged: dict[tuple[Any, ...], list[SourceCandidate]] = {}
    for candidate, request in pairs:
        checked = evaluate_candidate(candidate, request)
        if not checked.matched:
            continue
        checked = replace(
            checked,
            metadata={
                **checked.metadata,
                "language_preference_rank": _language_preference_rank(
                    request.language, checked.language
                ),
            },
        )
        key: tuple[Any, ...] = (
            normalize_title(checked.title),
            checked.season,
            checked.episode,
            checked.language.casefold(),
            checked.subtitle_format.casefold(),
        )
        bucket = merged.setdefault(key, [])
        merged[key] = _merge_bucket(bucket, checked)
    return tuple(
        sorted(
            (item for bucket in merged.values() for item in bucket),
            key=lambda item: (
                -item.score,
                int(item.metadata.get("language_preference_rank", 999)),
                item.provider,
                item.title,
                item.result_id,
            ),
        )
    )


def _merge_bucket(bucket: list[SourceCandidate], checked: SourceCandidate) -> list[SourceCandidate]:
    source_identity = checked.result_id or checked.detail_url
    duplicate = next(
        (
            item
            for item in bucket
            if item.provider == checked.provider
            and (item.result_id or item.detail_url) == source_identity
        ),
        None,
    )
    if duplicate is not None:
        if checked.score > duplicate.score:
            bucket[bucket.index(duplicate)] = checked
        return bucket
    if bucket and any(item.provider != checked.provider for item in bucket):
        best = max([*bucket, checked], key=lambda item: item.score)
        return [best]
    bucket.append(checked)
    return bucket
