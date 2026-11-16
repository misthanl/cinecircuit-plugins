"""Use the catalog CDN's advertised portrait size instead of its tiny default."""

import re
from urllib.parse import urlsplit, urlunsplit


def iqiyi_poster(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").casefold()
    if host != "iqiyipic.com" and not host.endswith(".iqiyipic.com"):
        return url
    path = re.sub(r"(?:_\d{2,4}_\d{2,4})?\.(jpg|jpeg|png|webp)$", r"_579_772.\1", parts.path, flags=re.I)
    return urlunsplit(("https", parts.netloc, path, parts.query, parts.fragment))
