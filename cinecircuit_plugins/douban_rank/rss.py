"""RSS admission requires a stable ID or a unique exact title/year match."""

import re
from typing import Any
from xml.etree import ElementTree as ET

from app.modules.plugins.runtime_services import http_client
from .media import normalized_media, subject_id, title_key


def _entry_text(entry: ET.Element, name: str) -> str:
    return str(entry.findtext(name) or entry.findtext("{*}" + name) or "").strip()


def _entry_id(entry: ET.Element) -> str:
    for child in entry:
        if child.tag.rsplit("}", 1)[-1] in {"link", "guid", "id"}:
            identity = subject_id(child.get("href") or child.text)
            if identity:
                return identity
    return ""


def _requested_identity(title: str) -> tuple[str, str, str]:
    year = re.search(r"[（(]((?:19|20)\d{2})[）)]", title)
    clean = re.sub(r"[（(](?:19|20)\d{2}[）)]", "", title)
    kind = "tv" if re.search(r"电视剧|剧集|综艺|\bTV\b", clean, re.I) else ""
    if not kind and re.search(r"电影", clean):
        kind = "movie"
    clean = re.sub(
        r"^[\[【]?(?:电影|电视剧|剧集|综艺|TV)[\]】]?\s*[:：]?\s*", "", clean, flags=re.I
    )
    return clean.strip(), year[1] if year else "", kind


def _matches(raw: dict[str, Any], title: str, year: str, kind: str) -> bool:
    names = [raw.get("title"), raw.get("original_title"), *(raw.get("alternate_titles") or [])]
    if title_key(title) not in {title_key(name) for name in names if name}:
        return False
    if year and str(raw.get("year") or "")[:4] != year:
        return False
    return not kind or raw.get("media_type") == kind


async def resolve_entry(media: Any, entry: ET.Element) -> dict[str, Any] | None:
    title, year, kind = _requested_identity(_entry_text(entry, "title"))
    identity = _entry_id(entry)
    if identity:
        if not kind:
            return await _resolve_untyped_id(media, identity, title)
        raw = await media.resolve_identity(source="douban", source_id=identity, media_type=kind)
        item = normalized_media(raw, kind) if isinstance(raw, dict) else None
        return item if item and item["source_id"] == identity else None
    if not title:
        return None
    result = await media.search(title, source="douban", count=20)
    choices = {}
    for raw in result.get("items") or []:
        item = normalized_media(raw) if isinstance(raw, dict) else None
        if item and _matches(item, title, year, kind):
            choices[item["source_id"]] = item
    return next(iter(choices.values())) if len(choices) == 1 else None


async def _resolve_untyped_id(media: Any, identity: str, title: str) -> dict[str, Any] | None:
    if not title:
        return None
    result = await media.search(title, source="douban", count=20)
    candidates = {}
    for raw in result.get("items") or []:
        item = normalized_media(raw) if isinstance(raw, dict) else None
        if item and item["source_id"] == identity:
            candidates[item["media_type"]] = item
    if len(candidates) != 1:
        return None
    kind = next(iter(candidates))
    raw = await media.resolve_identity(source="douban", source_id=identity, media_type=kind)
    item = normalized_media(raw, kind) if isinstance(raw, dict) else None
    return item if item and item["source_id"] == identity else None


async def read_rss(context: Any, addresses: list[str]) -> list[dict[str, Any]]:
    if not addresses:
        return []
    rsshub = str(context.config.get("rsshub") or "https://rsshub.app").rstrip("/")
    output = []
    async with http_client(
        timeout=25, follow_redirects=True, use_application_proxy=bool(context.config.get("proxy"))
    ) as client:
        for address in addresses:
            url = (
                address
                if address.startswith(("http://", "https://"))
                else f"{rsshub}/{address.lstrip('/')}"
            )
            response = await client.get(url)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for entry in list(root.findall(".//item")) + list(root.findall(".//{*}entry")):
                item = await resolve_entry(context.media, entry)
                if item:
                    output.append({**item, "board": "自定义 RSS 榜单"})
    return output
