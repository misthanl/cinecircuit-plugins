"""Name/season matching for feed titles, entirely local to this plugin."""
import re
import unicodedata

SEASON = re.compile(r"(?i)(?<![a-z0-9])S(\d{1,3})(?:E\d+)?|第\s*([一二三四五六七八九十\d]+)\s*季")
TECH = re.compile(r"(?i)(?:[ ._\-\[]+)(?:19\d{2}|20\d{2}|2160p|1080[pi]|720p|4k|web[- .]?dl|webrip|bluray|bdrip|hdtv|remux|x26[45]|h[ .]?26[45])\b")


def number(value):
    if value.isdigit():
        return int(value)
    digits = {c: i for i, c in enumerate("零一二三四五六七八九")}
    if "十" in value:
        left, right = value.split("十", 1)
        return digits.get(left, 1) * 10 + digits.get(right, 0)
    return digits.get(value, 0)


def normalized(value):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", str(value)).casefold())


def title_parts(value):
    title = unicodedata.normalize("NFKC", str(value or "")).strip()
    title = re.sub(r"^\[[^\]]+\]\s*", "", title)
    seasons = {number(match[1] or match[2]) for match in SEASON.finditer(title)}
    match = SEASON.search(title)
    if match:
        title = title[:match.start()]
    technical = TECH.search(title)
    if technical:
        title = title[:technical.start()]
    return normalized(title), seasons


class SubscriptionIndex:
    def __init__(self, rows):
        self.movies = set()
        self.series: set[tuple[str, int]] = set()
        for row in rows:
            aliases = row.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [aliases]
            names = [row.get(key) for key in ("title", "name", "original_title")] + aliases
            explicit = re.fullmatch(r"(?i)S?(\d{1,3})", str(row.get("season") or ""))
            for name in names:
                if not name:
                    continue
                title, seasons = title_parts(name)
                if not title:
                    continue
                if row.get("media_type") == "movie":
                    self.movies.add(title)
                elif row.get("media_type") in {"tv", "series"}:
                    if explicit:
                        seasons = {int(explicit[1])}
                    self.series.update((title, season) for season in seasons if season > 0)

    def matches(self, item):
        if re.search(r"(?i)S\d+\s*[-~至]\s*S?\d+", str(item.get("title") or "")):
            return False
        title, seasons = title_parts(item.get("title"))
        if seasons:
            return all((title, season) in self.series for season in seasons)
        return title in self.movies


async def load_index(context, tasks):
    if not any(task.get("enabled", True) and task.get("exclude_subscriptions") for task in tasks):
        return None
    catalog = context.sdk.require("subscription_catalog", min_version=1)
    return SubscriptionIndex(await catalog.list_summaries())
