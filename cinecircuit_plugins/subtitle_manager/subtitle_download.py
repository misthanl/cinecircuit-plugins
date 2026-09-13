"""Subtitle-source download protocols; no host-private services or file writes."""

import asyncio
import ipaddress
import socket
from pathlib import PurePosixPath
from typing import Any
from collections.abc import Sequence
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

from .subtitle_files import MAX_ARCHIVE

IPV6_VERSION = 6
PINNED_CONNECTION_PARTS = 3
FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")


def _same_origin(left: str, right: str) -> bool:
    try:
        first, second = urlsplit(left), urlsplit(right)
        return (
            first.scheme.casefold() == second.scheme.casefold()
            and first.hostname == second.hostname
            and (first.port or (443 if first.scheme == "https" else 80))
            == (second.port or (443 if second.scheme == "https" else 80))
        )
    except ValueError:
        return False


async def public_url(url: str) -> tuple[str, str, str]:
    """Validate and pin a public URL to the address that was inspected."""
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("字幕下载地址无效")
    addresses = await asyncio.get_running_loop().getaddrinfo(
        parsed.hostname,
        parsed.port or (443 if parsed.scheme == "https" else 80),
        type=socket.SOCK_STREAM,
    )
    resolved = [ipaddress.ip_address(row[4][0]) for row in addresses]
    try:
        literal_host = ipaddress.ip_address(str(parsed.hostname))
    except ValueError:
        literal_host = None
    allowed_fake_dns = literal_host is None and all(
        address.version == 4 and address in FAKE_IP_NETWORK for address in resolved
    )
    if not resolved or (
        not allowed_fake_dns and any(not address.is_global for address in resolved)
    ):
        raise ValueError("字幕下载不允许访问内部地址")
    address = resolved[0]
    address_text = f"[{address}]" if address.version == IPV6_VERSION else str(address)
    if parsed.port is not None:
        address_text += f":{parsed.port}"
    pinned = urlunsplit((parsed.scheme, address_text, parsed.path, parsed.query, parsed.fragment))
    host_header = str(parsed.hostname)
    if parsed.port is not None:
        host_header += f":{parsed.port}"
    return pinned, host_header, str(parsed.hostname)


async def fetch(client: Any, url: str, *, method: str = "GET", **kwargs: Any) -> tuple[bytes, str]:
    for _ in range(5):
        resolved = await public_url(url)
        request_url = url
        request_kwargs = dict(kwargs)
        if isinstance(resolved, tuple) and len(resolved) == PINNED_CONNECTION_PARTS:
            connect_url, host_header, sni_hostname = resolved
            transport = getattr(client, "_transport", None)
            if getattr(transport, "_outbound_security_transport", False):
                # The host transport validates and pins the logical URL itself.
                # Keeping the hostname here preserves its TLS SNI and proxy
                # routing when DNS is supplied by a transparent Fake-IP proxy.
                connect_url = request_url
            else:
                headers = dict(request_kwargs.pop("headers", {}) or {})
                headers.setdefault("Host", host_header)
                headers.setdefault("Connection", "close")
                extensions = dict(request_kwargs.pop("extensions", {}) or {})
                extensions["sni_hostname"] = sni_hostname
                request_kwargs.update(headers=headers, extensions=extensions)
        else:  # Compatibility for injected validators in plugin tests.
            connect_url = request_url
        async with client.stream(
            method, connect_url, follow_redirects=False, **request_kwargs
        ) as response:
            if response.is_redirect:
                redirect_url = urljoin(request_url, response.headers["location"])
                redirect_headers = (
                    dict(kwargs.get("headers", {}) or {})
                    if _same_origin(request_url, redirect_url)
                    else {}
                )
                url = redirect_url
                method, kwargs = (
                    "GET",
                    {"headers": redirect_headers} if redirect_headers else {},
                )  # Keep API headers on-host, but never forward them to download hosts.
                continue
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > MAX_ARCHIVE:
                    raise ValueError("字幕响应超过大小限制")
            return bytes(content), request_url
    raise ValueError("字幕下载重定向次数过多")


async def fetch_prefix(
    client: Any, url: str, *, limit: int = 1024, **kwargs: Any
) -> tuple[bytes, str]:
    """Read only enough of a public response to identify a broken payload."""
    limit = max(1, min(int(limit), 4096))
    for _ in range(5):
        resolved = await public_url(url)
        request_url = url
        request_kwargs = dict(kwargs)
        if isinstance(resolved, tuple) and len(resolved) == PINNED_CONNECTION_PARTS:
            connect_url, host_header, sni_hostname = resolved
            transport = getattr(client, "_transport", None)
            if getattr(transport, "_outbound_security_transport", False):
                connect_url = request_url
            else:
                headers = dict(request_kwargs.pop("headers", {}) or {})
                headers.setdefault("Host", host_header)
                headers.setdefault("Connection", "close")
                extensions = dict(request_kwargs.pop("extensions", {}) or {})
                extensions["sni_hostname"] = sni_hostname
                request_kwargs.update(headers=headers, extensions=extensions)
        else:
            connect_url = request_url
        async with client.stream(
            "GET", connect_url, follow_redirects=False, **request_kwargs
        ) as response:
            if response.is_redirect:
                redirect_url = urljoin(request_url, response.headers["location"])
                redirect_headers = (
                    dict(kwargs.get("headers", {}) or {})
                    if _same_origin(request_url, redirect_url)
                    else {}
                )
                url = redirect_url
                kwargs = {"headers": redirect_headers} if redirect_headers else {}
                continue
            response.raise_for_status()
            prefix = bytearray()
            async for chunk in response.aiter_bytes():
                prefix.extend(chunk[: limit - len(prefix)])
                if len(prefix) >= limit:
                    break
            return bytes(prefix), request_url
    raise ValueError("字幕下载重定向次数过多")


async def api_json(client: Any, url: str, **kwargs: Any) -> dict:
    import json

    content, _ = await fetch(client, url, **kwargs)
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError("字幕源响应无效")
    return result


async def fetch_links(
    client: Any,
    links: Sequence[tuple[str, str]],
    *,
    headers: dict[str, str] | None = None,
) -> list[tuple[str, bytes]]:
    if not links:
        raise ValueError("字幕源未提供可用下载地址，可能需要登录或验证码")
    result = []
    total = 0
    failed = False
    # Candidate references pass through the JSON-backed session gateway before
    # download. JSON restores tuple pairs as lists, which are not hashable and
    # therefore cannot be passed to ``dict.fromkeys`` directly.
    unique_links = list(dict.fromkeys((str(url), str(name or "")) for url, name in links))
    for url, name in unique_links[:8]:
        try:
            content, final_url = await fetch(client, url, headers=headers)
        except Exception:
            failed = True
            continue
        if total + len(content) > MAX_ARCHIVE:
            failed = True
            continue
        total += len(content)
        result.append((name or unquote(PurePosixPath(urlsplit(final_url).path).name), content))
    if not result:
        if failed:
            raise ValueError("字幕文件下载失败或超过大小限制")
        raise ValueError("字幕源未提供可用下载地址")
    return result
