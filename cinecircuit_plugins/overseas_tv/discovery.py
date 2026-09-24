"""Bounded discovery; each season is checked against its own premiere date."""

from datetime import date, timedelta

from .config import PLATFORMS


def date_window(config, today):
    return today - timedelta(days=int(config["past_days"])), today + timedelta(
        days=int(config["future_days"])
    )


def query_filters(config, network, today):
    lower, upper = date_window(config, today)
    excluded = [
        genre
        for key, ids in [("animation", [16]), ("documentary", [99]), ("reality", [10764, 10767])]
        if key not in config["include_types"]
        for genre in ids
    ]
    filters = {
        "with_networks": network,
        "air_date.gte": lower.isoformat(),
        "air_date.lte": upper.isoformat(),
        "vote_count.gte": 0,
    }
    if excluded:
        filters["without_genres"] = ",".join(map(str, excluded))
    if config["country"]:
        filters["with_origin_country"] = config["country"]
    return filters


def candidates(detail, config, today, platform):
    lower, upper = date_window(config, today)
    votes = int(detail.get("vote_count") or 0)
    if votes < int(config["min_votes"]):
        if not config["allow_unrated"]:
            return [], "评价人数不足"
    elif float(detail.get("rating") or 0) < float(config["min_rating"]):
        return [], "低于最低评分"
    source_id = str(detail.get("tmdb_id") or detail.get("source_id") or "")
    if not source_id.isdigit():
        raise ValueError("TMDB 媒体身份不完整")
    result = []
    for season in detail.get("seasons") or []:
        number = int(season.get("season_number") or 0)
        if number <= 0:
            continue
        try:
            premiere = date.fromisoformat(str(season.get("air_date") or ""))
        except ValueError:
            continue
        modes = config["modes"]
        if not lower <= premiere <= upper or not (
            "popular" in modes or ("new" if number == 1 else "returning") in modes
        ):
            continue
        result.append(
            {
                "title": str(detail.get("title") or ""),
                "source": "tmdb",
                "source_key": "tmdb",
                "source_id": source_id,
                "tmdb_id": source_id,
                "media_type": "tv",
                "year": str(detail.get("year") or ""),
                "season": f"S{number:02d}",
                "total_episode": int(season.get("episode_count") or 0),
                "poster": detail.get("poster") or "",
                "subscription_origin": "TMDB",
                "rank_source": {
                    "platform": platform,
                    "board": platform,
                    "release_info": f"S{number:02d} · {premiere}",
                    "media_type": "tv",
                },
            }
        )
    return result, "目标季不在时间范围内或开播日期待补全"


async def platform_rows(context, config, today, network, limit):
    scanned = 0
    for page in range(1, (limit + 19) // 20 + 1):
        response = await context.media.discover(
            {
                "source": "tmdb",
                "media_type": "tv",
                "page": page,
                "count": 20,
                "sort": "popularity.desc",
                "language": config["language"],
                "filters": query_filters(config, network, today),
            }
        )
        status = response.get("source_status") or {}
        if status.get("mode") in {
            "error",
            "unconfigured",
            "disabled",
            "fallback",
            "missing_config",
        }:
            raise RuntimeError("TMDB 数据源不可用，请检查主程序元数据配置")
        for row in response.get("items") or []:
            yield row
            scanned += 1
            if scanned >= limit:
                break
        if scanned >= limit or not response.get("has_more"):
            break


async def discover(context, config, today, errors=None):
    seen = set()
    succeeded = 0
    for key, label, network in PLATFORMS:
        if not config[f"{key}_enabled"]:
            continue
        try:
            async for row in platform_rows(
                context, config, today, network, int(config[f"{key}_num"])
            ):
                source_id = str(
                    row.get("source_id") or row.get("tmdb_id") or row.get("media_id") or ""
                )
                if source_id in seen:
                    continue
                seen.add(source_id)
                yield row, source_id, label
            succeeded += 1
        except Exception:
            if errors is not None:
                errors.append(
                    {
                        "title": label,
                        "board": label,
                        "status": "unknown",
                        "reason": "平台数据读取失败，下次重试",
                    }
                )
            context.logger.warning("%s 平台数据读取失败，下次重试", label)
    if not succeeded:
        raise RuntimeError("所选平台全部获取失败，请检查 TMDB 配置和网络")
