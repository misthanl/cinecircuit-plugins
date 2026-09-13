"""Task-local settings and cadence; persistence is accessed only through the SDK."""
from datetime import datetime
from time import time
from zoneinfo import ZoneInfo
from typing import Any
import re

from .cleanup import added_records, same_generation


def task_defaults(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    inherited = {key: config.get(key, False) for key in (
        "cleanup_enabled", "notification_enabled", "allow_delete_files",
    )}
    return {**inherited, "exclude_tags": "CineCircuit,H&R", "promotion": "free", "exclude_hr": True, "cron": config.get("cron", ""), "interval_minutes": 10,
            "task_limit": 0, "check_interval_minutes": 5, "intake_time_range": "", **task, "cleanup_enabled": True, "allow_delete_files": True, "delete_task": True}


def intake_allowed(task: dict[str, Any], timestamp: float | None = None) -> bool:
    value = str(task.get("intake_time_range") or "").strip()
    if not value:
        return True
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)", value)
    if not match:
        raise ValueError("进种时间段请填写 HH:mm-HH:mm，例如 00:00-08:00")
    start_hour, start_minute, end_hour, end_minute = map(int, match.groups())
    start, end = start_hour * 60 + start_minute, end_hour * 60 + end_minute
    if start == end:
        raise ValueError("进种时间段的开始与结束时间不能相同；全天进种请留空")
    current = datetime.fromtimestamp(time() if timestamp is None else timestamp, ZoneInfo("Asia/Shanghai"))
    minute = current.hour * 60 + current.minute
    return start <= minute < end if start < end else minute >= start or minute < end


def cron_values(field: str, minimum: int, maximum: int) -> set[int]:
    result: set[int] = set()
    for part in field.split(","):
        if not re.fullmatch(r"(?:\*|\d+(?:-\d+)?)(?:/\d+)?", part):
            raise ValueError("执行周期包含无效的 Cron 字段")
        base, slash, step_text = part.partition("/")
        step = int(step_text) if slash else 1
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            start, end = map(int, base.split("-", 1))
        else:
            start = int(base)
            end = maximum if slash else start
        if step <= 0 or start < minimum or end > maximum or start > end:
            raise ValueError("执行周期包含无效的 Cron 字段")
        result.update(range(start, end + 1, step))
    return result


def cron_matches(expression: str, timestamp: float) -> bool:
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("执行周期必须是 5 位 Cron 表达式")
    current = datetime.fromtimestamp(timestamp, ZoneInfo("Asia/Shanghai"))
    values = [cron_values(field, *limits) for field, limits in zip(
        fields, ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
    )]
    if 7 in values[4]:
        values[4].add(0)
    return all(value in allowed for value, allowed in zip(
        (current.minute, current.hour, current.day, current.month, (current.weekday() + 1) % 7), values
    ))


def due_tasks(context: Any, tasks: list[dict[str, Any]], *, check: bool = False) -> list[dict[str, Any]]:
    if getattr(context, "trigger", "manual") != "scheduled":
        return tasks
    state = context.state.scoped("brush-task-check-schedule" if check else "brush-task-schedule")
    now = time()
    selected = []
    for task in tasks:
        if not task.get("enabled", True):
            continue
        previous = float(state.get(str(task["id"]), 0) or 0)
        cron = "" if check else str(task.get("cron") or "").strip()
        due = (int(previous // 60) != int(now // 60) and cron_matches(cron, now)) if cron else (
            now - previous >= max(1, int(task.get("check_interval_minutes" if check else "interval_minutes") or (5 if check else 10))) * 60
        )
        if due:
            selected.append(task)
            state.set(str(task["id"]), now)
    return selected


def task_capacity(context: Any, rule: dict[str, Any], downloads: list[dict[str, Any]]) -> int:
    limit = max(0, int(rule.get("task_limit") or 0))
    if not limit:
        return max(1, int(rule.get("max_add") or 3))
    owned = {(str(receipt.get("downloader_id")), str(receipt.get("hash"))): receipt
             for row in added_records(context)
             if (receipt := row.get("result") or {}).get("ownership_verified")
             and str(receipt.get("brush_task_id")) == str(rule["id"])}
    active = sum(1 for task in downloads
                 if (receipt := owned.get((str(task.get("downloader_id")), str(task.get("hash")))))
                 and same_generation(receipt, task))
    return max(0, limit - active)
