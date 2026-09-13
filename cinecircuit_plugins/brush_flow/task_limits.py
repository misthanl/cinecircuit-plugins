"""Task-owned torrent volume and per-torrent rate settings."""
from math import isfinite
from typing import Any
from .cleanup import added_records, same_generation


def transfer_limits(task: dict[str, Any]) -> dict[str, int]:
    result = {}
    for key in ("upload_limit_kib", "download_limit_kib"):
        value = float(task.get(key) or 0)
        if not isfinite(value) or not value.is_integer() or not 0 <= value <= 2097151:
            raise ValueError("单种限速须为非负整数（KiB/s）")
        if value:
            result[key] = int(value)
    return result


def size_bytes(item: dict[str, Any]) -> int | None:
    try:
        raw = item.get("size")
        if raw is None:
            return None
        value = float(raw)
        return int(value) if isfinite(value) and value > 0 else None
    except (ValueError, TypeError):
        return None


async def volume_remaining(context: Any, rule: dict[str, Any], downloads: list[dict[str, Any]], *, complete: bool = False) -> int | None:
    limit = float(rule.get("seeding_limit_gib") or 0)
    if not isfinite(limit) or limit < 0:
        raise ValueError("保种总体积上限须为非负数")
    if not limit:
        return None
    owned = {(str(receipt.get("downloader_id")), str(receipt.get("hash"))): receipt
             for row in added_records(context)
             if (receipt := row.get("result") or {}).get("ownership_verified")
             and str(receipt.get("brush_task_id")) == str(rule["id"])}
    current = {(str(task.get("downloader_id")), str(task.get("hash"))): task for task in downloads}
    used = 0
    for pair, receipt in owned.items():
        task = current.get(pair)
        if task is None and not complete:
            # The overview is paginated; older owned torrents need an exact lookup.
            lookup = getattr(context.downloads, "task", None)
            if not callable(lookup):
                return 0
            try:
                task = await lookup(*pair, ownership_tag=str(receipt.get("ownership_tag") or ""))
            except Exception:
                return 0
        if task is None or not same_generation(receipt, task):
            continue
        size = size_bytes(task)
        if size is None:
            return 0
        used += size
    return max(0, int(limit * 1024 ** 3) - used)


async def owned_downloads(context: Any) -> list[dict[str, Any]]:
    """Resolve verified receipts once; failed queries abort intake safely."""
    queried, owned = {}, {}
    for row in added_records(context):
        receipt = row.get("result") or {}
        pair = (str(receipt.get("downloader_id") or ""), str(receipt.get("hash") or ""))
        marker = str(receipt.get("ownership_tag") or "")
        if not receipt.get("ownership_verified") or not all(pair) or not marker:
            continue
        lookup_key = (*pair, marker)
        if lookup_key not in queried:
            queried[lookup_key] = await context.downloads.task(*pair, ownership_tag=marker)
        task = queried[lookup_key]
        if (task is not None and str(task.get("hash")) == pair[1]
                and str(task.get("downloader_id")) == pair[0] and same_generation(receipt, task)):
            owned[pair] = task
    return list(owned.values())
