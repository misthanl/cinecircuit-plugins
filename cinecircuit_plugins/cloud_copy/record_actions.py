"""Record visibility and targeted retries; never remove remote files."""

from hashlib import sha256
from pathlib import PurePosixPath
import time
from typing import Any

from . import manual
from .journal import records_from

RETRYABLE = {"failed", "uncertain", "conflict", "skipped", "copied"}


def identity(value):
    value = str(value or "")
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("复制记录标识无效")
    return value


async def source_item(storage, config, record, key):
    saved = record.get("source_item")
    if saved:
        if sha256(str(saved["file_id"]).encode()).hexdigest() != key:
            raise ValueError("源文件标识不一致")
        return dict(saved)
    # Older journals only contain the relative path. Resolve that exact path,
    # checking the original file identity instead of rescanning unrelated files.
    path = PurePosixPath(record.get("path") or "")
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("原始文件路径无效")
    parent = str(config.get("source_root") or "0")
    for position, name in enumerate(path.parts):
        item = await unique_child(storage, config["source"], parent, name)
        if position < len(path.parts) - 1:
            if not item.get("directory"):
                raise ValueError("原始目录不可用")
            parent = str(item["file_id"])
        elif item.get("directory") or sha256(str(item["file_id"]).encode()).hexdigest() != key:
            raise ValueError("源文件已被替换，无法重试旧记录")
    return {**item, "relative_path": str(path)}


async def unique_child(storage, source, parent, name):
    cursor, seen = None, set()
    match: dict[str, Any] | None = None
    while True:
        page = await storage.file_page(source, parent, cursor)
        for row in page["items"]:
            if row["name"] != name:
                continue
            if match is not None:
                raise ValueError("原始文件不存在或路径不唯一，无法重试")
            match = row
        cursor = page.get("cursor")
        if not cursor:
            break
        if cursor in seen:
            raise ValueError("目录分页没有前进")
        seen.add(cursor)
    if match is None:
        raise ValueError("原始文件不存在或路径不唯一，无法重试")
    return match


def action_scope(plugin, request, context):
    payload = request.payload
    batch_action = request.action.startswith("batch-")
    origin = "manual" if batch_action else payload.get("origin", "rule")
    index = context.state.scoped("manual-batches")
    task = None
    if origin == "manual":
        batch_id = manual.task_id(payload.get("id") if batch_action else payload.get("batch_id"))
        task = index.get("task-" + batch_id)
        if not task or task.get("hidden"):
            raise ValueError("批次不存在")
        if task["status"] in ("queued", "running"):
            raise ValueError("任务尚未结束，暂时不能重试或删除记录")
        state = context.state.scoped("manual-" + batch_id)
        config = {
            **task["config"],
            "temporary_directory": context.config.get("temporary_directory", ""),
        }
    elif origin == "rule" and not batch_action:
        _, _, _, _, rule = plugin.settings(context, validate_policy=False)
        state, config = context.state.scoped("copy-" + rule), context.config
        progress = state.get("progress") or {}
        if progress.get("pending") or progress.get("folders") or state.get("rescan_requested"):
            raise ValueError("规则任务尚未结束，暂时不能重试或删除记录")
    else:
        raise ValueError("记录来源无效")
    return batch_action, index, task, state, config


def select_records(state, payload, batch_action):
    if batch_action:
        return [
            row
            for row in records_from(state)
            if not row.get("hidden") and row.get("status") in RETRYABLE
        ]
    key = identity(payload.get("identity"))
    row = state.get("records-" + key[:3], {}).get(key)
    if not row or row.get("hidden"):
        raise ValueError("复制记录不存在")
    return [{**row, "identity": key}]


def delete_records(index, task, state, selected, batch_action):
    if batch_action:
        if task is None:
            raise ValueError("批次不存在")
        task.update(hidden=True)
        index.set("task-" + task["id"], task)
        return {"deleted": True}
    row = selected[0]
    key = "records-" + row["identity"][:3]
    rows = state.get(key, {})
    rows[row["identity"]]["hidden"] = True
    state.set(key, rows)
    return {"deleted": True}


def check_retry_state(index, task, state):
    if task:
        latest = index.get("task-" + task["id"])
        if not latest or latest.get("hidden") or latest["status"] in ("queued", "running"):
            raise ValueError("任务状态已变化，请刷新记录")
    elif (
        (state.get("progress") or {}).get("pending")
        or (state.get("progress") or {}).get("folders")
        or state.get("rescan_requested")
    ):
        raise ValueError("任务状态已变化，请刷新记录")


def retry_progress(state, task, selected, pending, batch_action):
    progress = state.get("progress") or {"folders": [], "pending": [], "last_scan": 0}
    if batch_action:
        # Failed batches may have stopped before a journal entry was created.
        pending.extend(
            item
            for item in progress.get("pending", [])
            if not any(str(other["file_id"]) == str(item["file_id"]) for other in pending)
        )
    elif task and (
        progress.get("folders")
        or any(
            sha256(str(item["file_id"]).encode()).hexdigest() != selected[0]["identity"]
            for item in progress.get("pending", [])
        )
    ):
        raise ValueError("批次还有未处理文件或目录，请在复制记录中重试整个批次")
    folders = progress.get("folders", []) if batch_action else []
    if not pending and not folders:
        raise ValueError("没有可以重试的记录")
    progress.update(pending=pending, folders=folders)
    return progress


def queue_retry(index, task, state, selected, progress):
    for row in selected:
        current = state.get("records-" + row["identity"][:3], {}).get(row["identity"])
        if not current or current.get("hidden") or current.get("status") != row["status"]:
            raise ValueError("记录状态已变化，请刷新记录")
    for row in selected:
        key = "records-" + row["identity"][:3]
        rows = state.get(key, {})
        rows[row["identity"]].update(
            status="copied" if row["status"] == "copied" else "retry",
            recovering=True,
            updated_at=time.time(),
        )
        state.set(key, rows)
    # A single-record retry never queues other files or an entire scan.
    state.set("progress", progress)
    if task:
        task.update(
            status="queued", error="", current_file="", phase="", pending=len(progress["pending"])
        )
        index.set("task-" + task["id"], task)
    else:
        state.set("paused", False)
    return {"queued": True}


async def action(plugin, request, context):
    batch_action, index, task, state, config = action_scope(plugin, request, context)
    deleting = request.action.endswith("delete")
    selected = (
        [] if batch_action and deleting else select_records(state, request.payload, batch_action)
    )
    if deleting:
        return delete_records(index, task, state, selected, batch_action)
    manual.require_temporary_directory(config)
    if any(row["status"] not in RETRYABLE for row in selected):
        raise ValueError("该记录无需重试")
    storage = context.sdk.require("storage", min_version=2)
    pending = [await source_item(storage, config, row, row["identity"]) for row in selected]
    # Directory lookups yield to other requests. Check again before queueing;
    # keep validation and journal/progress submission in one non-yielding step.
    check_retry_state(index, task, state)
    progress = retry_progress(state, task, selected, pending, batch_action)
    return queue_retry(index, task, state, selected, progress)
