"""Deletion thresholds and unit conversions shared by automatic checks."""

import math
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any


LIMITS = (
    ("delete_ratio", "ratio", 1),
    ("delete_seed_hours", "seed_hours", 1),
    ("delete_upload_gib", "uploaded_bytes", 1024**3),
    ("delete_download_hours", "download_hours", 1),
    ("delete_inactive_hours", "inactive_hours", 1),
    ("delete_avg_upload_kib", "avg_upload_kib_s", 1),
)


def value(raw: Any) -> float | None:
    try:
        result = float(raw)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def configured(rule: dict[str, Any]) -> bool:
    return rule.get("delete_expired_promotion") is True or any(value(rule.get(key)) for key, _, _ in LIMITS)


def promotion_expired(payload: dict[str, Any]) -> bool:
    raw = payload.get("promotion_expires_at")
    if not raw:
        return False
    try:
        expires = datetime.fromisoformat(str(raw).replace("/", "-").replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return expires <= datetime.now(expires.tzinfo)
    except (ValueError, TypeError, OverflowError):
        return False


def matches(rule: dict[str, Any], task: dict[str, Any]) -> bool:
    for key, metric, multiplier in LIMITS:
        threshold, measured = value(rule.get(key)), value(task.get(metric))
        if not threshold or measured is None:
            continue
        if key == "delete_avg_upload_kib":
            if measured < threshold:
                return True
        elif measured >= threshold * multiplier:
            return True
    return False
