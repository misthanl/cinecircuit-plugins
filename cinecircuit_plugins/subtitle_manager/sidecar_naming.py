"""Keep internal ranking categories separate from player language identifiers."""

_LABELS = {
    "zh-CN-en": ("zh", "简英双语"),
    "zh-TW-en": ("zh", "繁英雙語"),
    "zh-CN": ("zh-CN", "简体中文"),
    "zh-TW": ("zh-TW", "繁體中文"),
    "zh": ("zh", "中文"),
    "en": ("en", "English"),
}


def sidecar_metadata(language: str) -> dict[str, str]:
    code, title = _LABELS.get(language, (language, ""))
    return {"language": code, "title": title}


def sidecar_label(language: str) -> str:
    values = sidecar_metadata(language)
    code, title = values["language"], values["title"]
    return f"{code}({title})" if title else code
