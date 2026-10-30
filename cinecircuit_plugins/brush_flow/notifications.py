"""Task-scoped, best-effort notifications with quiet scheduled limit checks."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def opted_in(task: dict[str, Any]) -> bool:
    return task.get("enabled", True) is True and task.get("notification_enabled") is True


async def send(context: Any, task: dict[str, Any], text: str) -> bool:
    if not opted_in(task):
        return False
    try:
        result = await context.notifications.send(
            f"刷流任务：{task.get('name') or '未命名刷流任务'}", text,
            notification_type="plugin",
        )
        return isinstance(result, dict) and any(
            row.get("success") is True for row in result.get("results", [])
            if isinstance(row, dict)
        )
    except Exception:
        logger.warning("Brush-flow notification delivery failed")
        return False


async def notify_failure(context: Any, tasks: list[dict[str, Any]], reason: str) -> None:
    for task in tasks:
        await send(context, task, f"执行失败：{reason}。")


async def notify_outcomes(context: Any, tasks: list[dict[str, Any]], results: list[dict[str, Any]]) -> None:
    by_id = {str(task["id"]): task for task in tasks}
    store = getattr(context, "state", None)
    state = store.scoped("brush-notifications") if store is not None else None
    for result in results:
        task = by_id.get(str(result.get("task_id")))
        if task is None or not opted_in(task):
            continue
        key, reason = str(task["id"]), str(result.get("reason") or "")
        if reason:
            if (getattr(context, "trigger", "manual") == "scheduled"
                    and state is not None and state.get(key, "") == reason):
                continue
            if await send(context, task, f"本次未进种：{reason}。") and state is not None:
                state.set(key, reason)
        else:
            if state is not None:
                state.set(key, "")
            await send(context, task, f"匹配 {result.get('matched', 0)} 个，新增下载 {result.get('added', 0)} 个。"
                       f"失败 {result.get('failed', 0)} 个。")


def record_cleanup(summary: dict[str, Any], task_id: str, status: str) -> None:
    counts = summary.setdefault("task_results", {}).setdefault(str(task_id), {})
    counts[status] = counts.get(status, 0) + 1


async def notify_cleanup(context: Any, tasks: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    for task in tasks:
        counts = summary.get("task_results", {}).get(str(task["id"]), {})
        if counts:
            await send(context, task, f"清理检查完成：暂停 {counts.get('paused', 0)} 个，"
                       f"删除 {counts.get('deleted', 0)} 个，失败 {counts.get('failed', 0)} 个。")
