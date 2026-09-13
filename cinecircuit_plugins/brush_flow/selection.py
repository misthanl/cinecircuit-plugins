"""Local candidate filters; no metadata requests are needed per torrent."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import math
import re


def bounds(value):
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    if not re.fullmatch(r"\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?", text):
        raise ValueError("范围须为非负数字或最小值-最大值")
    parts = [float(part) for part in text.split("-")]
    low, high = (parts[0], parts[-1])
    if low > high or not math.isfinite(high):
        raise ValueError("范围最小值不能大于最大值")
    return low, high


def in_range(value, rule):
    limits = bounds(rule)
    if limits is None:
        return True
    try:
        return limits[0] <= float(value) <= limits[1]
    except (TypeError, ValueError):
        return False


def published_minutes(item, offset, now):
    raw = str(item.get("publish_time") or item.get("published_at") or "")
    try:
        try:
            published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            published = parsedate_to_datetime(raw)
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc) - timedelta(hours=float(offset or 0))
        return (now - published).total_seconds() / 60
    except (ValueError, TypeError, OverflowError):
        return None


def _matches_text(item, task):
    title = str(item.get("title") or "")
    for key, reject_match in (("include", False), ("exclude", True)):
        pattern = str(task.get(key) or "").strip()
        if pattern and bool(re.search(pattern, title, re.I)) == reject_match:
            return False
    return True


def _matches_promotion(item, task):
    promotion = str(item.get("promotion") or "").upper()
    requested = task.get("promotion", "free")
    if requested == "free" and not (item.get("free") is True or promotion in {"FREE", "2XFREE"}):
        return False
    if requested == "2xfree" and promotion != "2XFREE":
        return False
    if requested not in {"all", "free", "2xfree"}:
        return False
    return True


def matches(item, task, *, now=None):
    if not _matches_text(item, task) or not _matches_promotion(item, task):
        return False
    if task.get("exclude_hr", True) and (task.get("site_hr") or item.get("hit_and_run")):
        return False
    size = item.get("size_bytes", item.get("size"))
    try:
        size = float(size) / 1024**3
    except (TypeError, ValueError):
        size = None
    size_rule = task.get("size_range")
    if size_rule is None:
        minimum, maximum = float(task.get("min_size") or 0), float(task.get("max_size") or 0)
        if (minimum or maximum) and (size is None or size < minimum or (maximum and size > maximum)):
            return False
    if not in_range(size, size_rule):
        return False
    seeders = item.get("seeders") if item.get("seeders_known") is not False else None
    if not in_range(seeders, task.get("seeders_range")):
        return False
    if bounds(task.get("publish_range")) is not None:
        age = published_minutes(item, task.get("timezone_offset"), now or datetime.now(timezone.utc))
        if not in_range(age, task["publish_range"]):
            return False
    return True
