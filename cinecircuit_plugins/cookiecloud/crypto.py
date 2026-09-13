from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7


SUPPORTED_CRYPTO_TYPES = frozenset({"legacy", "aes-128-cbc-fixed"})


def decrypt_snapshot(uuid: str, password: str, encrypted: str, crypto_type: str) -> dict[str, Any]:
    normalized_type = str(crypto_type or "legacy").strip().casefold()
    if normalized_type not in SUPPORTED_CRYPTO_TYPES:
        raise ValueError("CookieCloud 加密算法不受支持")
    try:
        ciphertext = base64.b64decode(str(encrypted or ""), validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("CookieCloud 密文格式无效") from error
    passphrase = hashlib.md5(f"{uuid}-{password}".encode()).hexdigest()[:16].encode()
    if normalized_type == "aes-128-cbc-fixed":
        plaintext = _decrypt_aes(ciphertext, passphrase, bytes(16))
    else:
        plaintext = _decrypt_legacy(ciphertext, passphrase)
    try:
        value = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("CookieCloud 用户 KEY 或加密密码不正确") from error
    if not isinstance(value, dict) or not isinstance(value.get("cookie_data"), dict):
        raise ValueError("CookieCloud 快照缺少 Cookie 数据")
    return value


def _decrypt_legacy(payload: bytes, passphrase: bytes) -> bytes:
    if len(payload) < 16 or payload[:8] != b"Salted__":
        raise ValueError("CookieCloud legacy 密文格式无效")
    key_iv = _evp_bytes_to_key(passphrase, payload[8:16], 48)
    return _decrypt_aes(payload[16:], key_iv[:32], key_iv[32:48])


def _evp_bytes_to_key(passphrase: bytes, salt: bytes, length: int) -> bytes:
    result = b""
    previous = b""
    while len(result) < length:
        previous = hashlib.md5(previous + passphrase + salt).digest()
        result += previous
    return result[:length]


def _decrypt_aes(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = PKCS7(128).unpadder()
    try:
        return unpadder.update(padded) + unpadder.finalize()
    except ValueError as error:
        raise ValueError("CookieCloud 用户 KEY 或加密密码不正确") from error
