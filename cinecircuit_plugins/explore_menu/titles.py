"""Keep provider presentation separate from work and season identities."""

import re
import unicodedata

from app.modules.plugins.runtime_services import split_series_title

_EDITION = re.compile(r"\s*(?:[\[（(【]\s*)?(普通话版|国语版|粤语版|英语版|原声版|配音版|中文版)\s*[\]）)】]?\s*$")


def title_context(row):
    original = str(row.get("catalog_title") or row.get("title") or "").strip()
    raw = unicodedata.normalize("NFKC", original)
    match = _EDITION.search(raw)
    clean = raw[:match.start()].strip() if match else raw
    parsed = split_series_title(clean)
    return {"catalog_title": original, "title": clean, "edition": match[1] if match else "",
            "series_title": parsed[0] if parsed else clean, "season": parsed[1] if parsed else 0}


def annotate(row):
    context = title_context(row)
    return {**row, "catalog_title": context["catalog_title"], "catalog_year": row.get("year") or "",
            "title": context["title"], "edition": context["edition"],
            **({"series_title": context["series_title"], "requested_season": context["season"]} if context["season"] else {})}
