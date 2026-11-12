"""Keep internal ranking categories separate from player language identifiers."""

import inspect
from collections.abc import Callable

_LABELS = {
    "zh-CN-en": ("zh", "简英双语"),
    "zh-TW-en": ("zh", "繁英雙語"),
    "zh-CN": ("zh-CN", "简体中文"),
    "zh-TW": ("zh-TW", "繁體中文"),
    "zh": ("zh", "中文"),
    "en": ("en", "English"),
}


def sidecar_metadata(language: str, *, writer: Callable[..., object] | None = None) -> dict[str, str]:
    if writer is not None:
        try:
            parameters = inspect.signature(writer).parameters.values()
            supports_title = any(
                p.name == "title" or p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters
            )
        except (TypeError, ValueError):
            supports_title = False
        if not supports_title:
            # Older hosts use the original language suffix. Decide before the
            # write; never retry a possibly successful write after TypeError.
            return {"language": language}
    code, title = _LABELS.get(language, (language, ""))
    return {"language": code, "title": title}


def sidecar_label(language: str) -> str:
    values = sidecar_metadata(language)
    code, title = values["language"], values["title"]
    return f"{title}.{code}" if title else code
