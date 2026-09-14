"""Decode historical filename bytes without destroying Chinese before parsing."""

from html import unescape
from pathlib import PurePosixPath
import re
from urllib.parse import unquote_to_bytes


def decode_name_bytes(value: bytes) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")


def legacy_subtitle_name(value: str) -> str:
    # JSON is parsed with surrogateescape so raw legacy bytes survive until
    # each filename can be decoded independently of other response records.
    value = decode_name_bytes(value.encode("utf-8", errors="surrogateescape"))
    value = re.sub(
        r"(?:%[0-9a-fA-F]{2})+",
        lambda match: decode_name_bytes(unquote_to_bytes(match.group())),
        value,
    )
    value = unescape(value).replace("\\", "/")
    return PurePosixPath(value).name or "subtitle.srt"
