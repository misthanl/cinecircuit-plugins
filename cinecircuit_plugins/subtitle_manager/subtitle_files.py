"""Bounded in-memory unpacking and conservative media/subtitle matching."""

import re
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile, is_zipfile

from .video_hash import matches_file

MAX_FILE = 10 * 1024 * 1024
MAX_ARCHIVE = 20 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 64
FORMATS = {"srt", "ass", "ssa", "vtt", "webvtt", "sbv", "sub"}
EPISODE = re.compile(r"s(\d{1,3})[ ._-]*e(\d{1,4})(?!\d)", re.I)


def unpack(content: bytes, filename: str) -> list[tuple[str, bytes]]:
    if not content or len(content) > MAX_ARCHIVE:
        raise ValueError("字幕下载为空或超过大小限制")
    if not is_zipfile(BytesIO(content)):
        return _unpacked_file(content, filename)
    with ZipFile(BytesIO(content)) as archive:
        entries = archive.infolist()
        if (
            len(entries) > MAX_ARCHIVE_ENTRIES
            or sum(item.file_size for item in entries) > MAX_ARCHIVE
        ):
            raise ValueError("字幕压缩包超过安全限制")
        files = []
        for item in entries:
            path = PurePosixPath(item.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or ":" in str(path):
                raise ValueError("字幕压缩包包含非法路径")
            if item.is_dir() or path.suffix.lstrip(".").lower() not in FORMATS:
                continue
            if item.flag_bits & 1 or item.file_size > MAX_FILE:
                raise ValueError("不支持加密或超大字幕")
            files.append((path.name, archive.read(item)))
        return files


def _unpacked_file(content: bytes, filename: str) -> list[tuple[str, bytes]]:
    if len(content) > MAX_FILE:
        return []
    extension = PurePosixPath(filename).suffix.lstrip(".").lower()
    if extension not in FORMATS:
        detected = _detect_text_format(content)
        if detected:
            filename = f"{filename.rstrip('.')}.{detected}"
    return [(filename, content)]


def _detect_text_format(content: bytes) -> str:
    """Recover a missing extension without accepting HTML/XML error bodies."""
    text = ""
    for encoding in ("utf-8-sig", "utf-16", "gb18030", "big5"):
        try:
            text = content.decode(encoding)
            if "\x00" not in text:
                break
        except UnicodeError:
            continue
    lowered = text.casefold().lstrip()
    if not lowered or lowered.startswith(("<?xml", "<html", "<!doctype")):
        return ""
    if "[events]" in lowered and "dialogue:" in lowered:
        return "ass"
    if lowered.startswith("webvtt"):
        return "vtt"
    if re.search(r"\d{1,2}:\d{2}(?::\d{2})?[,.]\d{1,3}\s+-->\s+\d", text):
        return "srt"
    return ""


def subtitle_text(content: bytes, extension: str) -> str:
    from .text_formats import UnsupportedSubtitle, convert

    if extension == "sub" and content.startswith(b"\x00\x00\x01"):
        raise UnsupportedSubtitle("暂不支持图片 SUB/IDX 字幕")
    text = ""
    for encoding in (
        "utf-8-sig",
        "utf-16" if content[:2] in {b"\xff\xfe", b"\xfe\xff"} else "utf-8",
        "gb18030",
        "big5",
    ):
        try:
            text = content.decode(encoding)
            break
        except UnicodeError:
            continue
    if not text or "\x00" in text or re.search(
        r"<(?:\?xml|!doctype|html|script)\b", text, re.I
    ):
        raise ValueError("下载内容不是有效文本字幕")
    if extension in {"sbv", "sub"}:
        return convert(text, extension)
    if extension in {"ass", "ssa"}:
        lowered = text.casefold()
        valid = "[events]" in lowered and "dialogue:" in lowered
    else:
        valid = bool(re.search(r"\d{1,2}:\d{2}(?::\d{2})?[,.]\d{1,3}\s+-->\s+\d", text))
    if not valid:
        raise ValueError("未找到有效字幕时间轴")
    return text


def output_format(extension: str) -> str:
    return {"webvtt": "vtt", "sbv": "srt", "sub": "srt"}.get(extension, extension)


def _normalize(value: object) -> str:
    return re.sub(r"[\W_]+", "", str(value).casefold())


def _target_titles(target: dict) -> list[str]:
    values = [
        target.get("title", ""),
        target.get("english_title", ""),
        target.get("original_title", ""),
        *(target.get("aliases") or []),
    ]
    return [str(title) for title in values if str(title).strip()]


def _episode_matches(target: dict, candidate: dict, filename: str) -> bool:
    expected = EPISODE.search(target["keyword"])
    actual = EPISODE.search(filename)
    if not expected:
        return not (target.get("season") or target.get("episode") or actual)
    expected_pair = tuple(map(int, expected.groups()))
    candidate_season = candidate.get("season")
    candidate_episode = candidate.get("episode")
    structured_pair = (
        (int(candidate_season), int(candidate_episode))
        if candidate_season is not None and candidate_episode is not None
        else None
    )
    matched_episode = (
        tuple(map(int, actual.groups())) == expected_pair
        if actual
        else bool(candidate.get("_single_payload") and structured_pair == expected_pair)
    )
    return matched_episode and not re.search(r"e\d+[- ._]*e\d+", filename, re.I)


def matches(target: dict[str, str], candidate: dict, filename: str) -> bool:
    if matches_file(candidate.get("_file_match"), target.get("media_path", "")):
        actual = EPISODE.search(filename)
        expected = EPISODE.search(target.get("keyword", ""))
        return not actual or bool(expected and actual.groups() == expected.groups())
    identity_match = candidate.get("_identity_match")
    if isinstance(identity_match, dict):
        kind = str(identity_match.get("kind") or "")
        value = str(identity_match.get("value") or "")
        if kind in {"tmdb_id", "imdb_id", "douban_id"} and value and value == str(target.get(kind) or ""):
            return _episode_matches(target, candidate, filename)
    titles = _target_titles(target)
    if titles and not any(
        _normalize(title) in _normalize(candidate.get("title", "")) for title in titles
    ):
        return False
    year = str(target.get("year") or "")
    years = re.findall(r"\b(?:19|20)\d{2}\b", str(candidate.get("title", "")) + " " + filename)
    candidate_year = str(candidate.get("year") or "")
    if year:
        if candidate_year and candidate_year != year:
            return False
        if years and year not in years:
            return False
    if not _episode_matches(target, candidate, filename):
        return False
    media_stem = PurePosixPath(target["media_path"].replace("\\", "/")).stem
    return bool(titles or _normalize(media_stem) in _normalize(filename))


def language_tag(filename: str, candidate: dict, text: str) -> str:
    value = str(candidate.get("language") or "").casefold()
    aliases = {
        "zh-cn": "zh-CN",
        "zh-hans": "zh-CN",
        "zh-tw": "zh-TW",
        "zh-hant": "zh-TW",
        "en": "en",
        "eng": "en",
        "ja": "ja",
        "ko": "ko",
        "zh": "zh",
    }
    name = filename.casefold()
    if re.search(r"简体|简中|chs|zh[._-](?:cn|hans)", name):
        return "zh-CN"
    if re.search(r"繁体|繁中|cht|zh[._-](?:tw|hant)", name):
        return "zh-TW"
    if value in aliases:
        return aliases[value]
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    return "und"
