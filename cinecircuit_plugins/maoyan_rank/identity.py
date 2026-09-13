"""Lazy, conservative identity matching using the existing media SDK."""
from datetime import date, timedelta
import re
from typing import Any


def exact_candidates(items, title, media_type):
    def normalize(value):
        return re.sub(r"\W+", "", re.sub(
            r"(?:\bS\d{1,3}\b|第\s*[一二三四五六七八九十百\d]+\s*季)", "", str(value), flags=re.I
        )).casefold()
    result = {}
    for item in items:
        if item.get("media_type") not in {media_type, "series" if media_type == "tv" else "movie"}:
            continue
        if normalize(item.get("title") or "") != normalize(title):
            continue
        key = (str(item.get("source_key") or ""), str(item.get("source_id") or ""))
        if key[1]:
            result[key] = item
    return list(result.values())


def release_hint(row):
    """Count premiere day as day one; never use the machine's current year as metadata."""
    text = str(row.get("release_info") or "")
    absolute = re.fullmatch(r"(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})(?:日)?(?:上映|上线)?", text)
    try:
        if absolute:
            return date(*map(int, absolute.groups()))
        relative = re.fullmatch(r"(?:上映|上线)(\d+)天", text)
        if relative and int(relative[1]) > 0:
            return date.fromisoformat(row["board_date"]) - timedelta(days=int(relative[1]) - 1)
    except (ValueError, KeyError, OverflowError):
        pass
    return None


def detail_dates(detail):
    regional = [entry for entry in (detail.get("release_dates") or {}).get("results", [])
                if entry.get("iso_3166_1") == "CN"]
    values = [item.get("release_date") for entry in regional for item in entry.get("release_dates", [])]
    if not values:
        values = [detail.get("date"), detail.get("air_date"), detail.get("release_date"), detail.get("first_air_date")]
    dates = []
    for value in values:
        try:
            dates.append(date.fromisoformat(str(value)[:10]))
        except ValueError:
            pass
    return dates


def latest_release(dates, *, board_date=""):
    """Prefer the latest release that has already happened on the board day."""
    if not dates:
        return None
    try:
        cutoff = date.fromisoformat(str(board_date))
    except ValueError:
        cutoff = None
    released = [value for value in dates if cutoff is None or value <= cutoff]
    return max(released or dates)


async def match_identity(context: Any, row: dict, cache: dict):
    key = (row.get("media_type"), row.get("maoyan_id"), row["title"], row.get("year"))
    if key in cache:
        return cache[key]
    results = await context.media.search(row["title"], source="tmdb", count=8)
    title_candidates = exact_candidates(
        results.get("items") or [], row["title"], row["media_type"]
    )
    if not title_candidates:
        fallback = await _explicit_season_identity(context, row, cache, key)
        if fallback is not None:
            return fallback[0] if fallback else None
    candidates = title_candidates
    year = str(row.get("year") or "")
    if re.fullmatch(r"\d{4}", year):
        same_year = [item for item in candidates if str(item.get("year") or "") == year]
        # A stale catalog year must not discard every otherwise exact-title candidate.
        candidates = same_year or title_candidates
    if len(candidates) == 1:
        cache[key] = candidates[0]
        return candidates[0]
    if not candidates:
        selected = await _sequel_identity(context, row, results.get("items") or [])
        if selected is not None:
            cache[key] = selected
        return selected
    matches, dated_candidates = await _dated_candidates(context, row, candidates)
    if len(matches) == 1:
        cache[key] = matches[0]
        return matches[0]
    if dated_candidates:
        # TMDB search order is the final deterministic tie-breaker for equally recent remakes.
        newest = max(value for value, _candidate in dated_candidates)
        selected = next(candidate for value, candidate in dated_candidates if value == newest)
        cache[key] = selected
        return selected
    return None


async def _explicit_season_identity(context, row, cache, key):
    if row.get("media_type") != "tv":
        return None
    # Search providers often index the series without its explicit season.
    # Keep row.title intact so subscription admission still checks that season.
    suffix = re.fullmatch(
        r"(.+?)\s*(?:第\s*(?:[一二三四五六七八九]|[一二三四五六七八九]?十[一二三四五六七八九]?|[1-9]\d{0,2})\s*季|\bS\d{1,3})\s*",
        row["title"], re.I,
    )
    if suffix and suffix[1].strip():
        base = suffix[1].strip()
        fallback = await context.media.search(base, source="tmdb", count=8)
        title_candidates = exact_candidates(fallback.get("items") or [], base, "tv")
        # A season premiere year cannot disambiguate the original series year.
        if len(title_candidates) != 1:
            return []
        cache[key] = title_candidates[0]
        return title_candidates
    return None


async def _sequel_identity(context, row, items):
    """Treat a trailing number as a candidate, requiring dated season evidence."""
    if row.get("media_type") != "tv":
        return None
    suffix = re.fullmatch(r"(.+?[^\d\s])\s*([1-9]\d?)", row["title"].strip())
    if not suffix or int(suffix[2]) < 2:
        return None
    base, season = suffix[1].strip(), int(suffix[2])
    hint = release_hint(row)
    year = str(row.get("year") or "")
    release_year = re.fullmatch(r"(\d{4})(?:年)?(?:上映|上线|开播)?", str(row.get("release_info") or ""))
    if not year and release_year:
        year = release_year[1]
    if hint is None and not re.fullmatch(r"\d{4}", year):
        return None
    candidates = exact_candidates(items, base, "tv")
    if not candidates:
        results = await context.media.search(base, source="tmdb", count=8)
        candidates = exact_candidates(results.get("items") or [], base, "tv")
    # Never expand ambiguous remakes into an unbounded detail search.
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    metadata = await context.media.detail("tmdb", {
        **candidate, "include_extensions": False, "include_library": False,
        "include_credits": False, "include_recommendations": False,
        "include_seasons": True,
    })
    targets = [entry for entry in metadata.get("seasons") or []
               if str(entry.get("season_number")) == str(season)]
    if len(targets) != 1:
        return None
    dates = detail_dates(targets[0])
    if hint is not None:
        confirmed = any(abs((value - hint).days) <= 1 for value in dates)
    else:
        confirmed = any(str(value.year) == year for value in dates)
    if not confirmed:
        return None
    return {**candidate, "_maoyan_verified_season": season}


async def _dated_candidates(context, row, candidates):
    hint = release_hint(row)
    detail = getattr(context.media, "detail", None)
    matches = []
    dated_candidates = []
    for candidate in candidates:
        metadata = candidate
        if callable(detail):
            try:
                metadata = await detail("tmdb", candidate)
            except Exception:
                # Search-card dates can still provide a deterministic newest-title fallback.
                metadata = candidate
        dates = detail_dates(metadata)
        latest = latest_release(dates, board_date=row.get("board_date") or "")
        if latest is not None:
            dated_candidates.append((latest, candidate))
        # Inclusive/exclusive day counting may differ by one day.
        if hint is not None and any(abs((value - hint).days) <= 1 for value in dates):
            matches.append(candidate)
    return matches, dated_candidates
