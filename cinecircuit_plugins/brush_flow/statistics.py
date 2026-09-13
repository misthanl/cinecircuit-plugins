"""Plugin-owned transfer observations and execution history, using SDK gateways."""
from hashlib import sha256
from math import isfinite
from time import time
from uuid import uuid4

from app.modules.plugins.contracts import PluginStateConflict

from .ownership import same_generation


def number(value):
    try:
        result = float(value)
        return result if isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def identity(receipt):
    values = [receipt.get(key) for key in ("downloader_id", "hash", "task_added_on", "ownership_tag")]
    return sha256(str(values).encode()).hexdigest()


def ledger(context):
    state = getattr(context, "state", None)
    return state.scoped("brush-transfer-observations") if state is not None else None


def capture(context, receipt, task):
    """Keep high-water counters per verified torrent generation, before cleanup."""
    scope = ledger(context)
    values = {"uploaded": number(task.get("uploaded_bytes")), "downloaded": number(task.get("downloaded"))}
    if scope is None:
        return values
    key = identity(receipt)
    for _ in range(3):
        record = scope.get_record(key) if callable(getattr(scope, "get_record", None)) else None
        previous = (record["value"] if record else scope.get(key, {})) or {}
        merged = {field: max(filter(lambda v: v is not None, [previous.get(field), value]), default=None)
                  for field, value in values.items()}
        if merged == previous:
            return merged
        try:
            options = {"expected_version": record["version"] if record else 0} if callable(getattr(scope, "get_record", None)) else {}
            scope.set(key, merged, **options)
            return merged
        except PluginStateConflict:
            continue
    raise ValueError("统计快照写入冲突，请稍后重试")


def record_execution(context, task, *, added=0, matched=0, skipped=0, failed=0, cleaned=0, reason="成功"):
    if not callable(getattr(context.items, "record", None)):
        return
    context.items.record(
        f"brush-execution:{uuid4().hex}", "execution",
        payload={"task_id": str(task["id"]), "name": task.get("name") or "未命名刷流任务", "site_id": task.get("site_id", "")},
        result={"timestamp": time(), "added": added, "matched": matched, "skipped": skipped,
                "failed": failed, "cleaned": cleaned, "reason": reason},
    )


def records(context):
    rows = []
    for status in ("added", "paused", "deleted", "missing"):
        offset = 0
        while True:
            page = context.items.list(500, offset=offset, status=status)
            rows.extend(page)
            if len(page) < 500:
                break
            offset += len(page)
    return rows


def _task_row(task):
    return {"id": task["id"], "name": task.get("name") or "未命名刷流任务", "site_id": task.get("site_id", ""),
            "downloader_id": task.get("downloader_id", ""), "enabled": task.get("enabled", True),
            "seeding_limit_gib": task.get("seeding_limit_gib", 0), "cron": task.get("cron", ""),
            "interval_minutes": task.get("interval_minutes", 10), "download_count": 0, "seed_count": 0,
            "upload_speed": 0, "download_speed": 0, "size": 0, "uploaded": 0, "downloaded": 0,
            "available": True, "history_complete": True}


def _add_counters(row, counters):
    for key in ("uploaded", "downloaded"):
        value = counters.get(key)
        if value is None:
            row["history_complete"] = False
        else:
            row[key] += value


def _live(row, task):
    complete = number(task.get("progress"))
    if not task.get("paused") and complete is not None:
        row["seed_count" if complete >= 100 else "download_count"] += 1
    for key in ("upload_speed", "download_speed", "size"):
        value = number(task.get(key))
        if value is None:
            row["available"] = False
        else:
            row[key] += value


def _verified(receipt, task):
    return (str(task.get("hash", "")).casefold() == str(receipt.get("hash", "")).casefold()
            and task.get("downloader_id") == receipt.get("downloader_id") and same_generation(receipt, task))


async def _observe(context, record, row):
    receipt = record["result"]
    scope = ledger(context)
    counters = (scope.get(identity(receipt), {}) or {}) if scope is not None else {}
    if record.get("status") in {"added", "paused"}:
        try:
            task = await context.downloads.task(str(receipt["downloader_id"]), str(receipt["hash"]), ownership_tag=str(receipt["ownership_tag"]))
            if task is not None and _verified(receipt, task):
                counters = capture(context, receipt, task)
                _live(row, task)
        except Exception:
            row["available"] = False
    _add_counters(row, counters)


async def build_statistics(context, tasks):
    rows = {str(task["id"]): _task_row(task) for task in tasks}
    seen = set()
    history = [{**(r.get("payload") or {}), **(r.get("result") or {}), "id": r.get("item_key", "")}
               for r in context.items.list(200, status="execution")]
    for record in records(context):
        receipt = record.get("result") or {}
        task_id = str(receipt.get("brush_task_id") or "")
        if not receipt.get("ownership_verified") or not all(receipt.get(k) for k in ("hash", "downloader_id", "ownership_tag", "task_added_on")):
            continue
        key = identity(receipt)
        if key in seen:
            continue
        seen.add(key)
        if task_id not in rows:
            rows[task_id] = _task_row({"id": task_id, "name": receipt.get("brush_task_name") or "已移除任务", "enabled": False, "site_id": receipt.get("brush_site_id", "")})
            rows[task_id]["removed"] = True
        await _observe(context, record, rows[task_id])
    return {"tasks": list(rows.values()), "history": sorted(history, key=lambda row: row.get("timestamp", 0), reverse=True)[:200], "updated_at": time(), "enabled": context.config.get("enabled", True)}
