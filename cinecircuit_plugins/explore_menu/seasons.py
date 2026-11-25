"""Confirm a provider's season against the metadata source's real episode order."""

from .titles import title_context


async def lookup_season(context, title, season, year, group=""):
    lookup = getattr(context.media, "search_source_identity", None)
    if not callable(lookup):
        return None
    evidence = {"season": season, "require_season_validation": True, "allow_undated_season": True}
    if group:
        evidence["episode_group_id"] = group
    try:
        return await lookup(source="tmdb", title=title, media_type="tv", year=year, episode_evidence=evidence)
    except (ValueError, RuntimeError, TimeoutError, OSError):
        return None


async def resolve_season(context, row, year, same_title, *, include_orders=True, skip_direct=False):
    title = title_context(row)
    if not title["season"]:
        return None
    direct = None if skip_direct else await lookup_season(context, title["series_title"], title["season"], year)
    if direct:
        return direct
    if not include_orders:
        return None
    orders = getattr(context.media, "series_orders", None)
    if not callable(orders):
        return None
    found = await context.media.search(title["series_title"], source="tmdb", count=24)
    candidates = [item for item in found.get("items", []) if item.get("media_type") == "tv"
                  and same_title(item, title["series_title"])][:3]
    matches = {}
    for candidate in candidates:
        for group in await orders(source="tmdb", source_id=str(candidate["source_id"])):
            if not any(s["season_number"] == title["season"] and s.get("episode_count") for s in group.get("seasons", [])):
                continue
            match = await lookup_season(context, title["series_title"], title["season"], year, group["id"])
            if match and str(match.get("source_id")) == str(candidate["source_id"]):
                match = {**match, "episode_order_name": group["name"]}
                matches[(str(match["source_id"]), group["id"])] = match
    return next(iter(matches.values())) if len(matches) == 1 else None
