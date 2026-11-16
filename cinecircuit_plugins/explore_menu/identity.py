"""Resolve catalog identities before considering the opt-in AI fallback."""

import asyncio
import re
import unicodedata

import httpx
from .titles import title_context
from .seasons import resolve_season

ERRORS = (ValueError, RuntimeError, TimeoutError, OSError, httpx.HTTPError)


def media_types(kind):
    # Animation, children's and documentary catalogs contain both films and series.
    return {"movie", "tv"} if kind in {"anime", "kids", "documentary"} else {"movie" if kind == "movie" else "tv"}


def normalized(value):
    return re.sub(r"\W+", "", unicodedata.normalize("NFKC", str(value or ""))).casefold()


def same_title(item, title):
    names = [item.get("title"), item.get("original_title"), *(item.get("alternate_titles") or [])]
    parsed = title_context({"title": title})
    queries = {normalized(parsed["title"])}
    if parsed["season"]:
        queries.add(normalized(parsed["series_title"] + str(parsed["season"])))
    return bool(queries & {normalized(name) for name in names if name})


def year_of(item):
    return str(item.get("year") or item.get("first_air_date") or item.get("release_date") or "")[:4]


def corroborated(row, detail):
    left, right = normalized(row.get("overview")), normalized(detail.get("overview"))
    return min(len(left), len(right)) >= 40 and (left in right or right in left)


async def read_candidate(context, candidate, row, kind, semaphore, *, unique=False):
    expected_year = year_of(row)
    if not expected_year or year_of(candidate):
        return candidate if not expected_year or year_of(candidate) == expected_year else None
    async with semaphore:
        try:
            async with asyncio.timeout(7):
                detail = await context.media.detail("tmdb", {
                    "source_id": candidate["source_id"], "media_type": kind,
                    "include_extensions": False, "include_library": False,
                    "include_credits": False, "include_recommendations": False, "include_seasons": False,
                })
        except ERRORS:
            return None
    if (detail.get("source_key") != "tmdb" or detail.get("media_type") != kind
            or str(detail.get("source_id")) != str(candidate["source_id"])
            or not same_title(detail, row["title"])):
        return None
    actual_year = year_of(detail)
    if actual_year:
        return detail if actual_year == expected_year else None
    if unique:
        return {**detail, "identity_warnings": ["元数据暂缺年份，已选中唯一同名候选，请确认。"]}
    return detail if corroborated(row, detail) else None


async def canonical(context, row, kind):
    seasonal = await resolve_season(context, row, year_of(row), same_title, include_orders=False)
    if seasonal:
        return seasonal
    title = title_context(row)["title"]
    if not title:
        return None
    result = await context.media.search(title, source="tmdb", count=24)
    candidates = {(item.get("media_type"), str(item["source_id"])): item for item in result.get("items", [])
                  if item.get("source_key") == "tmdb" and item.get("source_id")
                  and item.get("media_type") in media_types(kind) and same_title(item, title)}
    if len(candidates) > 6:
        return None
    semaphore = asyncio.Semaphore(3)
    matches = await asyncio.gather(*(
        read_candidate(context, item, row, item["media_type"], semaphore, unique=len(candidates) == 1)
        for item in candidates.values()
    ))
    confirmed = [item for item in matches if item]
    if title_context(row)["season"] and len(confirmed) == 1:
        confirmed[0] = {**confirmed[0], "requested_season": 1}
    if len(confirmed) == 1:
        return confirmed[0]
    return await resolve_season(context, row, year_of(row), same_title, skip_direct=True)


async def resolve(context, row, kind):
    try:
        async with asyncio.timeout(16):
            match = await canonical(context, row, kind)
        if match:
            return {**match, "resolution_method": "catalog_metadata_match"}
    except ERRORS:
        pass
    assist = getattr(context.media, "assist_identity", None)
    if not callable(assist):
        return None
    try:
        title = title_context(row)
        options = {"episode_evidence": {"season": title["season"], "allow_undated_season": True}} if title["season"] else {}
        match = await assist(
            source="tmdb", title=title["series_title"] if title["season"] else title["title"], media_type="movie" if kind == "movie" else "tv",
            year=year_of(row), overview=str(row.get("overview") or ""),
            allow_single_candidate=True,
            **options,
        )
    except ERRORS:
        return None
    if (not match or match.get("source_key") != "tmdb" or not match.get("source_id")
            or match.get("media_type") not in media_types(kind)
            or (year_of(row) and year_of(match) != year_of(row) and not match.get("season_identity") and not match.get("identity_warnings"))):
        return None
    return match
