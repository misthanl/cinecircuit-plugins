"""Language selection based on subtitle dialogue, not style names or headers."""

import re
from functools import lru_cache

DEFAULT_ORDER = ["zh-CN-en", "zh-TW-en", "zh-CN", "zh-TW", "zh", "en"]
LEGACY_ORDER = ["zh-Hans", "zh-CN", "zh-Hant", "zh", "en"]
ASS_DIALOGUE_FIELDS = 10
ENGLISH_WORD_THRESHOLD = 3


@lru_cache(maxsize=2)
def converter(mode: str):
    from ._vendor.opencc import OpenCC

    return OpenCC(mode)


def dialogue(text: str, extension: str) -> str:
    lines = []
    timed_text = "-->" in text and extension not in {"ass", "ssa"}
    in_cue = False
    for line in text.splitlines():
        if timed_text:
            if "-->" in line:
                in_cue = True
                continue
            if not line.strip():
                in_cue = False
            if not in_cue:
                continue
        if extension in {"ass", "ssa"}:
            if not line.startswith("Dialogue:"):
                continue
            parts = line.split(",", 9)
            if len(parts) != ASS_DIALOGUE_FIELDS:
                continue
            line = parts[9]
        elif (
            not line.strip() or line.strip().isdigit() or "-->" in line or line.startswith("WEBVTT")
        ):
            continue
        line = re.sub(r"\{[^}]*\}|<[^>]*>", "", line)
        lines.append(line.replace("\\N", "\n").replace("\\n", "\n"))
    return "\n".join(lines)


def bilingual(text: str, extension: str) -> bool:
    body = dialogue(text, extension)
    # Require Chinese dialogue plus an English phrase; isolated names do not suffice.
    return bool(
        re.search(r"[\u4e00-\u9fff]", body)
        and re.search(r"\b[A-Za-z]+(?:['’][A-Za-z]+)?[ \t]+[A-Za-z]+\b", body)
    )


def language_kind(language: str, text: str = "", extension: str = "srt") -> str:
    aliases = {
        "zh-hans": "zh-CN",
        "zh-cn": "zh-CN",
        "zh-hant": "zh-TW",
        "zh-tw": "zh-TW",
        "eng": "en",
    }
    language = aliases.get(language.casefold(), language)
    body = dialogue(text, extension)
    if language == "zh" and body:
        if converter("t2s").convert(body) != body:
            language = "zh-TW"
        elif converter("s2t").convert(body) != body:
            language = "zh-CN"
    if language in {"zh-CN", "zh-TW"} and bilingual(text, extension):
        return language + "-en"
    return language


def detect_language(filename: str, text: str, extension: str) -> str:
    """Infer supported tags conservatively; unknown text needs user input."""
    body = dialogue(text, extension)
    if re.search(r"[\u3040-\u30ff]", body):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", body):
        return "ko"
    if re.search(r"[\u4e00-\u9fff]", body):
        kind = language_kind("zh", text, extension)
        return kind.removesuffix("-en")
    # Latin script alone does not identify English (French/German/etc. also use it).
    if re.search(r"(?:^|[._ -])(?:en|eng)(?:[._ -]|$)", filename, re.I) and re.search(
        r"[A-Za-z]", body
    ):
        return "en"
    words = set(re.findall(r"[a-z]+", body.casefold()))
    if (
        len(
            words
            & {
                "the",
                "you",
                "your",
                "this",
                "that",
                "with",
                "what",
                "where",
                "have",
                "hello",
                "welcome",
                "there",
                "are",
                "is",
                "and",
            }
        )
        >= ENGLISH_WORD_THRESHOLD
    ):
        return "en"
    return "und"


def priority(config: dict, kind: str) -> int:
    order = config.get("auto_subtitle_language_priority")
    if not order or order in (LEGACY_ORDER, ["zh-CN", "zh-TW", "zh", "en"]):
        order = DEFAULT_ORDER
    aliases = {"zh-hans": "zh-cn", "zh-hant": "zh-tw", "eng": "en"}
    normalized = aliases.get(kind.casefold(), kind.casefold())
    for index, value in enumerate(order):
        value = str(value).casefold()
        if aliases.get(value, value) == normalized:
            return index
    return 99


def file_priority(config: dict, item: tuple) -> tuple[int, int]:
    extension, language, content = item
    formats = config.get("auto_subtitle_format_priority") or [
        "ass",
        "ssa",
        "srt",
        "vtt",
    ]
    return (
        priority(config, language_kind(language, content.decode("utf-8"), extension)),
        formats.index(extension) if extension in formats else len(formats),
    )
