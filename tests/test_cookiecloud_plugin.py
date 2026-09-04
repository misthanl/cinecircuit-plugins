from __future__ import annotations

import asyncio
import base64
import gzip
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlencode

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from starlette.requests import Request

from cinecircuit_plugins.cookiecloud.http_api import _check_key, _upload_payload
from cinecircuit_plugins.cookiecloud.crypto import decrypt_snapshot
from cinecircuit_plugins.cookiecloud.plugin import CookieCloudPlugin, _cookie_header
from cinecircuit_plugins.cookiecloud.snapshot import store_snapshot


class MemoryState:
    def __init__(self, values: dict[str, object] | None = None, prefix: str = "") -> None:
        self.values = values if values is not None else {}
        self.prefix = prefix

    def scoped(self, namespace: str) -> "MemoryState":
        return MemoryState(self.values, f"{namespace}:")

    def get(self, key: str, default: object = None) -> object:
        return self.values.get(f"{self.prefix}{key}", default)

    def set(self, key: str, value: object) -> dict[str, object]:
        self.values[f"{self.prefix}{key}"] = value
        return {"key": key, "value": value}

    def delete(self, key: str) -> bool:
        return self.values.pop(f"{self.prefix}{key}", None) is not None


def _encrypt(uuid: str, password: str, payload: dict[str, object], crypto_type: str) -> str:
    plaintext = json.dumps(payload).encode()
    passphrase = hashlib.md5(f"{uuid}-{password}".encode()).hexdigest()[:16].encode()
    padder = PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    if crypto_type == "aes-128-cbc-fixed":
        key, iv, prefix = passphrase, bytes(16), b""
    else:
        salt = b"12345678"
        material = b""
        previous = b""
        while len(material) < 48:
            previous = hashlib.md5(previous + passphrase + salt).digest()
            material += previous
        key, iv, prefix = material[:32], material[32:48], b"Salted__" + salt
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return base64.b64encode(prefix + encryptor.update(padded) + encryptor.finalize()).decode()


def _request(body: bytes) -> Request:
    delivered = False

    async def receive() -> dict[str, object]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {"type": "http", "method": "POST", "path": "/cookiecloud/update", "headers": []}, receive
    )


@pytest.mark.parametrize("crypto_type", ["legacy", "aes-128-cbc-fixed"])
def test_cookiecloud_decrypts_official_crypto_formats(crypto_type: str) -> None:
    payload = {"cookie_data": {"example.com": [{"name": "sid", "value": "value"}]}}
    encrypted = _encrypt("user-key", "password", payload, crypto_type)

    assert decrypt_snapshot("user-key", "password", encrypted, crypto_type) == payload


@pytest.mark.parametrize("encoding", ["json-gzip", "form"])
def test_cookiecloud_accepts_official_upload_encodings(encoding: str) -> None:
    payload = {
        "uuid": "user-key",
        "encrypted": "encrypted-value",
        "crypto_type": "aes-128-cbc-fixed",
    }
    body = (
        gzip.compress(json.dumps(payload).encode())
        if encoding == "json-gzip"
        else urlencode(payload).encode()
    )

    assert _upload_payload(body) == payload


def test_cookiecloud_public_endpoint_uses_unobservable_key_mismatch() -> None:
    plugins = Mock()
    plugins.get.return_value = {
        "enabled": True,
        "config": {"user_key": "configured-key"},
    }

    with pytest.raises(Exception) as missing:
        _check_key(plugins.get.return_value["config"], "wrong-key")

    assert getattr(missing.value, "status_code", None) == 404


def test_cookiecloud_schedule_is_a_fixed_period_selector() -> None:
    schedule = next(
        field
        for field in CookieCloudPlugin.manifest.config_schema["fields"]
        if field["key"] == "cron"
    )

    assert schedule["input_type"] == "select"
    assert schedule["default"] == ""
    assert schedule["options"] == [
        {"value": "0 */6 * * *", "label": "每 6 小时"},
        {"value": "0 */12 * * *", "label": "每 12 小时"},
        {"value": "", "label": "每天"},
        {"value": "0 0 * * 1", "label": "每周"},
        {"value": "0 0 1 * *", "label": "每月"},
    ]


def test_cookiecloud_settings_and_schedule_share_one_page() -> None:
    schema = CookieCloudPlugin.manifest.config_schema

    assert schema["description"] == "接收浏览器 CookieCloud 快照，定时验证并更新或添加受支持的 PT 站点。"
    assert [section["key"] for section in schema["sections"]] == ["connection"]
    assert {field["section"] for field in schema["fields"]} == {"connection"}
    assert next(field for field in schema["fields"] if field["key"] == "user_key")["secret"] is True


def test_cookie_header_uses_only_supported_domain_and_most_specific_cookie() -> None:
    cookies = [
        {"name": "sid", "value": "parent", "domain": ".example.com", "path": "/"},
        {"name": "sid", "value": "specific", "domain": "pt.example.com", "path": "/"},
        {"name": "other", "value": "ignored", "domain": "unrelated.test", "path": "/"},
    ]

    assert _cookie_header(cookies, ["pt.example.com"]) == "sid=specific"


@pytest.mark.parametrize(
    "engine", ["nexusphp", "html_tracker", "tracker_api", "future_cookie_engine"]
)
def test_cookiecloud_updates_only_after_current_cookie_fails(engine) -> None:
    state = MemoryState()
    encrypted = _encrypt(
        "user-key",
        "password",
        {
            "cookie_data": {
                "example.com": [
                    {"name": "sid", "value": "fresh", "domain": ".example.com", "path": "/"}
                ]
            }
        },
        "aes-128-cbc-fixed",
    )
    store_snapshot(state, uuid="user-key", encrypted=encrypted, crypto_type="aes-128-cbc-fixed")
    sites = SimpleNamespace(
        supported_catalog=AsyncMock(
            return_value={
                "items": [
                    {
                        "id": "example",
                        "name": "示例站点",
                        "engine": engine,
                        "credential_imports": ["cookie"],
                        "domains": ["example.com"],
                        "site_id": "site-1",
                    }
                ]
            }
        ),
        check=AsyncMock(return_value={"ok": False, "message": "登录失效"}),
        apply_cookie=AsyncMock(
            return_value={"ok": True, "applied": True, "created": False, "message": "Cookie 已更新"}
        ),
    )
    logger = Mock()
    context = SimpleNamespace(
        config={"enabled": True, "user_key": "user-key", "password": "password"},
        state=state,
        sites=sites,
        logger=logger,
    )

    result = asyncio.run(CookieCloudPlugin().run(context))

    assert result["updated"] == 1
    sites.apply_cookie.assert_awaited_once_with("example", "sid=fresh", site_id="site-1")
    assert ("CookieCloud 已%s站点%s：%s", "更新", "示例站点", "Cookie 已更新") in [
        call.args for call in logger.info.call_args_list
    ]
    assert any(
        call.args and str(call.args[0]).startswith("CookieCloud 站点检查完成")
        for call in logger.info.call_args_list
    )


def test_cookiecloud_logs_added_site_name_without_exposing_cookie() -> None:
    sites = SimpleNamespace(
        check=AsyncMock(),
        apply_cookie=AsyncMock(
            return_value={"ok": True, "applied": True, "created": True, "message": "站点已添加"}
        ),
    )
    logger = Mock()
    context = SimpleNamespace(sites=sites, logger=logger)
    summary = {"checked": 1, "valid": 0, "updated": 0, "added": 0, "ignored": 0, "failed": 0}

    asyncio.run(
        CookieCloudPlugin._sync_site(
            context,
            {"id": "new-site", "name": "新增站点", "site_id": ""},
            "sid=secret-cookie-value",
            summary,
        )
    )

    assert summary["added"] == 1
    assert logger.info.call_args.args == (
        "CookieCloud 已%s站点%s：%s",
        "添加",
        "新增站点",
        "站点已添加",
    )
    assert "secret-cookie-value" not in repr(logger.method_calls)


def test_cookiecloud_logs_valid_site_name() -> None:
    sites = SimpleNamespace(
        check=AsyncMock(return_value={"ok": True, "message": "登录有效"}),
        apply_cookie=AsyncMock(),
    )
    logger = Mock()
    context = SimpleNamespace(sites=sites, logger=logger)
    summary = {"checked": 1, "valid": 0, "updated": 0, "added": 0, "ignored": 0, "failed": 0}

    asyncio.run(
        CookieCloudPlugin._sync_site(
            context,
            {"id": "active-site", "name": "有效站点", "site_id": "site-1"},
            "sid=secret-cookie-value",
            summary,
        )
    )

    assert summary["valid"] == 1
    sites.apply_cookie.assert_not_awaited()
    logger.info.assert_called_once_with("CookieCloud 站点 Cookie 保持有效：%s", "有效站点")
    assert "secret-cookie-value" not in repr(logger.method_calls)
