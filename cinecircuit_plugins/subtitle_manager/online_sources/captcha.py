"""Serializable CAPTCHA challenge data shared by page-based subtitle sources."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class CaptchaChallenge:
    """A user-solvable CAPTCHA produced by an online source.

    Source adapters fill the public fields plus cookies and context. The plugin
    stores this value in serializable plugin state and only returns the public
    fields to the page, so session cookies and resume context never leak into
    browser-visible payloads.
    """

    provider: str
    site: str
    image: str = ""
    instruction: str = ""
    verification_url: str = ""
    submit_url: str = ""
    method: str = "GET"
    payload: dict[str, Any] = field(default_factory=dict)
    code_encoding: str = "plain"
    resume_url: str = ""
    cookies: tuple[dict[str, str], ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "site": self.site,
            "image": self.image,
            "instruction": self.instruction,
            "verification_url": self.verification_url,
            "submit_url": self.submit_url,
            "method": self.method,
            "payload": self.payload,
            "code_encoding": self.code_encoding,
            "resume_url": self.resume_url,
            "cookies": list(self.cookies),
            "context": self.context,
        }

    def public_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "site": self.site,
            "image": self.image,
            "instruction": self.instruction,
        }


def bmp_data_url(raw: str) -> str:
    value = str(raw or "").strip()
    if value.startswith("data:"):
        return value
    if value:
        return f"data:image/bmp;base64,{value}"
    return ""


def svg_data_url(svg: str) -> str:
    value = str(svg or "").strip()
    if not value:
        return ""
    if value.casefold().startswith("data:"):
        return value
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def cookie_snapshot(client: Any) -> tuple[dict[str, str], ...]:
    cookies = getattr(client, "cookies", None)
    jar = getattr(cookies, "jar", None)
    if jar is None:
        return ()
    result: list[dict[str, str]] = []
    for cookie in jar:
        if not getattr(cookie, "name", ""):
            continue
        result.append(
            {
                "name": str(getattr(cookie, "name", "")),
                "value": str(getattr(cookie, "value", "")),
                "domain": str(getattr(cookie, "domain", "")),
                "path": str(getattr(cookie, "path", "") or "/"),
            }
        )
    return tuple(result)


def cookies_from_snapshot(
    snapshot: tuple[dict[str, str], ...] | list[dict[str, str]],
) -> httpx.Cookies:
    cookies = httpx.Cookies()
    for item in snapshot or ():
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        cookies.set(
            name,
            str(item.get("value") or ""),
            domain=str(item.get("domain") or ""),
            path=str(item.get("path") or "/"),
        )
    return cookies


def encode_captcha_code(code: str, encoding: str) -> str:
    value = str(code or "").strip()
    if str(encoding or "plain").casefold() == "hex":
        return "".join(f"{ord(char):x}" for char in value)
    return value
