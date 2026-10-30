"""Read public wish entries; profile identifiers never become arbitrary URLs."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Any
from xml.etree import ElementTree as ET

from app.modules.plugins.runtime_services import http_client


def user_ids(value: Any) -> list[str]:
    parts = value if isinstance(value, list) else re.split(r"[\s,，]+", str(value or ""))
    users = list(dict.fromkeys(str(part).strip() for part in parts if str(part).strip()))
    if not users or len(users) > 30:
        raise ValueError("请填写 1–30 个豆瓣用户ID")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", user) for user in users):
        raise ValueError("豆瓣用户ID格式不正确，请填写ID而非网址")
    return users


def parse_feed(content: bytes, user: str, days: int, now: datetime) -> list[dict[str, Any]]:
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("豆瓣动态内容过大")
    root = ET.fromstring(content)
    if root.tag.rsplit("}", 1)[-1] not in {"rss", "RDF", "feed"}:
        raise ValueError("豆瓣动态未返回有效RSS")
    output = []
    entries = root.findall(".//{*}item") + root.findall(".//{*}entry")
    for entry in entries[:1000]:
        title = entry_text(entry, "title")
        if not title.startswith("想看"):
            continue
        link = entry_text(entry, "link")
        if not link:
            link = next((child.get("href", "") for child in entry if child.tag.rsplit("}", 1)[-1] == "link"), "")
        match = re.fullmatch(r"https?://(?:movie|www)\.douban\.com/subject/(\d+)/?(?:\?[^#]*)?", link)
        if not match or not recent(entry_text(entry, "pubDate") or entry_text(entry, "published") or entry_text(entry, "updated"), days, now):
            continue
        title = title[2:].strip(" ：:《》")
        if title:
            output.append({"title": title, "source_id": match[1], "account": user})
    return output


def entry_text(entry: ET.Element, name: str) -> str:
    return str(entry.findtext(name) or entry.findtext("{*}" + name) or "").strip()


def recent(value: Any, days: int, now: datetime) -> bool:
    try:
        raw = str(value or "")
        published = datetime.fromisoformat(raw.replace("Z", "+00:00")) if re.match(r"^\d{4}-\d{2}-\d{2}T", raw) else parsedate_to_datetime(raw)
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return now - timedelta(days=days) <= published <= now + timedelta(minutes=5)
    except (ValueError, TypeError, OverflowError):
        return False


async def read_user(user: str, days: int, *, proxy: bool) -> list[dict[str, Any]]:
    async with http_client(timeout=25, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0"}, use_application_proxy=proxy) as client:
        response = await client.get(f"https://www.douban.com/feed/people/{user}/interests")
        response.raise_for_status()
        return parse_feed(response.content, user, days, datetime.now(timezone.utc))


async def resolve_wish(media: Any, entry: dict[str, Any]) -> dict[str, Any] | None:
    # RSS already supplies an exact subject ID; keyword suggestions may omit it.
    detail = await media.detail("douban", {
        "source_id": entry["source_id"], "media_type": "movie",
        "include_extensions": False, "include_library": False,
        "include_credits": False, "include_recommendations": False,
    })
    if not isinstance(detail, dict) or detail.get("source_key") != "douban":
        return None
    if str(detail.get("source_id") or "") != entry["source_id"]:
        return None
    kind = detail.get("media_type")
    if kind not in ("movie", "tv") or not detail.get("title"):
        return None
    # This gateway follows the configured recognition source, which may be TMDB.
    identity = await media.resolve_identity(source="douban", source_id=entry["source_id"], media_type=kind)
    if not isinstance(identity, dict) or identity.get("media_type") != kind:
        return None
    if not all(identity.get(key) for key in ("source_key", "source_id", "title")):
        return None
    return {**identity, "account": entry["account"], "board": entry["account"]}
