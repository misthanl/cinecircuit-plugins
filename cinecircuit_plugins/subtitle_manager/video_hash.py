"""Video fingerprints used by file-based subtitle services."""

import base64
import hashlib
import re


def identity_value(identity, name, default=""):
    return identity.get(name, default) if isinstance(identity, dict) else getattr(identity, name, default)


def sample_ranges(provider: str) -> list[dict]:
    if provider == "shooter":
        return [
            {"offset": 4096, "length": 4096},
            {"numerator": 2, "denominator": 3, "length": 4096},
            {"numerator": 1, "denominator": 3, "length": 4096},
            {"numerator": 1, "offset": -8192, "length": 4096},
        ]
    return [
        {"length": 20480},
        {"numerator": 1, "denominator": 3, "length": 20480},
        {"numerator": 1, "offset": -20480, "length": 20480},
    ]


def fingerprint(provider: str, payload: dict) -> str:
    ranges = sample_ranges(provider)
    rows = payload.get("samples", [])
    if payload.get("size", 0) < 61440 or len(rows) != len(ranges):
        raise ValueError("视频文件过小或采样不完整")
    chunks = [base64.b64decode(row["content_base64"], validate=True) for row in rows]
    if any(len(chunk) != spec["length"] for chunk, spec in zip(chunks, ranges)):
        raise ValueError("视频采样长度不正确")
    if provider == "shooter":
        return ";".join(hashlib.md5(chunk).hexdigest() for chunk in chunks)
    return hashlib.sha1(b"".join(chunks)).hexdigest().upper()


def matches_file(evidence: object, media_path: str) -> bool:
    if not isinstance(evidence, dict) or not media_path or evidence.get("media_path") != media_path:
        return False
    patterns = {"shooter": r"[a-f0-9]{32}(;[a-f0-9]{32}){3}", "xunlei": r"[A-F0-9]{40}"}
    algorithm = evidence.get("algorithm")
    pattern = patterns.get(algorithm) if isinstance(algorithm, str) else None
    return bool(pattern and re.fullmatch(pattern, str(evidence.get("hash", ""))))
