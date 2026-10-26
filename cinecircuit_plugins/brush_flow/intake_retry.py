"""Keep successful receipts deduplicated while retrying transient intake failures."""

from time import time


def retryable(error):
    text = str(error).casefold()
    return any(
        marker in text
        for marker in (
            "请求失败",
            "出站请求",
            "超时",
            "timeout",
            "timed out",
            "connection",
            "http 429",
            "http 500",
            "http 502",
            "http 503",
            "http 504",
            # These failures came from the old media-only submission route.
            "未识别到媒体信息",
        )
    )


def ready(record, *, now=None):
    if not record:
        return True
    if record.get("status") != "failed":
        return False
    result = record.get("result") or {}
    if not result.get("retryable", retryable(result.get("error"))):
        return False
    return (time() if now is None else now) >= float(result.get("retry_at") or 0)


def failure(error, previous=None):
    count = int(((previous or {}).get("result") or {}).get("retry_count") or 0)
    return {
        "error": str(error),
        "retryable": retryable(error),
        "retry_count": count + 1,
        "retry_at": time() + min(3600, 60 * 2 ** min(count, 6)),
    }
