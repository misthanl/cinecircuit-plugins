"""Only act on verified submission receipts owned by this plugin and rule."""

from __future__ import annotations

from typing import Any
import re
import logging

from .ownership import same_generation
from .deletion_rules import configured, matches, value, promotion_expired

logger = logging.getLogger(__name__)


def number(raw: Any) -> float:
    return value(raw) or 0


def eligible(rule: dict[str, Any], task: dict[str, Any], payload: dict[str, Any] | None = None) -> bool:
    if tag_set(rule.get("exclude_tags", "CineCircuit,H&R")) & tag_set(task.get("tags")):
        return False
    progress, remaining = value(task.get("progress")), value(task.get("amount_left"))
    if (progress is not None and progress < 100) or (remaining is not None and remaining > 0):
        return (rule.get("delete_expired_promotion") is True and promotion_expired(payload or {})) or matches(
            {key: rule.get(key) for key in ("delete_download_hours", "delete_inactive_hours", "delete_avg_upload_kib")}, task
        )
    if progress is None:
        return False
    return matches(rule, task)


def tag_set(raw: Any) -> set[str]:
    values = raw if isinstance(raw, (list, tuple, set)) else [raw]
    return {tag.strip().casefold() for value in values
            for tag in re.split(r"[,，\n]", str(value or "")) if tag.strip()}


def added_records(context: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    while True:
        page = context.items.list(500, offset=len(records), status="added")
        records.extend(page)
        if len(page) < 500:
            return records


async def check_downloads(context: Any, rules: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status": "completed",
        "checked": 0,
        "paused": 0,
        "deleted": 0,
        "skipped": 0,
        "errors": [],
    }
    rules = [rule for rule in rules if rule.get("cleanup_enabled", context.config.get("cleanup_enabled", False))]
    if not context.config.get("enabled", True) or not rules:
        return {**summary, "status": "disabled"}
    if not callable(getattr(context.downloads, "task", None)):
        return {**summary, "status": "unsupported", "errors": ["请更新主程序以安全检查刷流任务"]}
    active = {str(rule["id"]): rule for rule in rules if rule.get("enabled", True)}
    seen: set[tuple[str, str]] = set()
    for record in added_records(context):
        receipt = record.get("result") or {}
        rule = active.get(str(receipt.get("brush_task_id") or ""))
        pair = (str(receipt.get("downloader_id") or ""), str(receipt.get("hash") or ""))
        if not rule or not receipt.get("ownership_verified") or not all(pair) or pair in seen:
            summary["skipped"] += 1
            continue
        seen.add(pair)
        if not configured(rule):
            continue
        try:
            await check_record(context, record, receipt, rule, pair, summary)
        except Exception as error:
            summary["errors"].append({"task_id": rule["id"], "error": str(error)})
    return summary


async def check_record(
    context: Any,
    record: dict[str, Any],
    receipt: dict[str, Any],
    rule: dict[str, Any],
    pair: tuple[str, str],
    summary: dict[str, Any],
) -> None:
    task = await context.downloads.task(*pair, ownership_tag=str(receipt.get("ownership_tag") or ""))
    summary["checked"] += 1
    key = str(record.get("item_key") or "")
    if not key:
        summary["skipped"] += 1
        return
    if task is None:
        context.items.record(key, "missing", payload=record.get("payload"), result=receipt)
        return
    if (
        str(task.get("hash") or "").casefold() != pair[1].casefold()
        or str(task.get("downloader_id") or "") != pair[0]
        or not same_generation(receipt, task)
    ):
        summary["skipped"] += 1
        return
    from .statistics import capture
    try:
        capture(context, receipt, task)
    except Exception:
        # Keep authorized cleanup running; avoid logging receipt credentials or URLs.
        logger.warning("Brush-flow statistics capture failed; cleanup will continue")
    if not eligible(rule, task, record.get("payload") or {}):
        return
    if rule.get("delete_task", False):
        await context.downloads.delete(
            *pair, delete_files=bool(rule.get("allow_delete_files", context.config.get("allow_delete_files", False)))
        )
        status = "deleted"
    else:
        if not task.get("paused"):
            await context.downloads.pause(*pair)
        status = "paused"
    context.items.record(key, status, payload=record.get("payload"), result=receipt)
    summary[status] += 1
    from .statistics import record_execution
    record_execution(context, rule, cleaned=1, reason="已清理" if status == "deleted" else "已暂停")
