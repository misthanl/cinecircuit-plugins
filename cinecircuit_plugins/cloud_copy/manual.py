"""User-selected batches, persisted independently of the automatic rule."""

from copy import copy
from pathlib import PurePosixPath
import math
import re
import time
from typing import Any

from .statistics import records_from


async def catalog(storage, source, target=None):
    rows = (await storage.configurations()).get("items", [])
    for identity, capability in [(source, "file_copy_source"), (target, "file_copy_target")]:
        if identity is not None and not any(
            row.get("id") == identity
            and row.get("enabled", True)
            and capability in row.get("capabilities", [])
            for row in rows
        ):
            raise ValueError("请选择可用的源网盘与目标网盘")


def task_id(value):
    value = str(value or "")
    if not re.fullmatch(r"[a-f0-9-]{36}", value):
        raise ValueError("批次标识无效")
    return value


async def api(plugin, request, context):
    storage = context.sdk.require("storage", min_version=2)
    index = context.state.scoped("manual-batches")
    if request.action == "browse" and request.method == "GET":
        return await browse(storage, request.query)
    if request.action == "batches" and request.method == "GET":
        return list_batches(index)
    if request.action == "batch" and request.method == "GET":
        identity = task_id(request.query.get("id"))
        task = index.get("task-" + identity)
        if not task:
            raise ValueError("批次不存在")
        records = list(records_from(context.state.scoped("manual-" + identity)))
        return {
            **task,
            "records": sorted(records, key=lambda row: row.get("updated_at", 0), reverse=True)[
                :100
            ],
        }
    if request.action == "batch-retry" and request.method == "POST":
        return retry(context, index, request.payload)
    if request.action != "submit" or request.method != "POST":
        raise KeyError("未知操作")
    return await submit(storage, index, context, request.payload)


def retry(context, index, data):
    identity = task_id(data.get("id"))
    task = index.get("task-" + identity)
    if not task or task["status"] != "failed":
        raise ValueError("只有执行失败的批次可以重试")
    state = context.state.scoped("manual-" + identity)
    for group in state.list(prefix="records-", limit=500):
        records = group["value"]
        for record in records.values():
            if record["status"] == "uncertain":
                record.update(status="retry", recovering=True)
        state.set(group["key"], records)
    task.update(status="queued", error="")
    index.set("task-" + identity, task)
    return task


async def browse(storage, query):
    identity = str(query.get("storage") or "")
    # A target can also be browsed when it only advertises the target capability.
    rows = (await storage.configurations()).get("items", [])
    if not any(
        row.get("id") == identity
        and row.get("enabled", True)
        and any(
            cap in row.get("capabilities", []) for cap in ("file_copy_source", "file_copy_target")
        )
        for row in rows
    ):
        raise ValueError("网盘不可用")
    return await storage.file_page(
        identity, str(query.get("parent") or "0"), query.get("cursor") or None
    )


def list_batches(index):
    rows: list[dict[str, Any]] = []
    after = ""
    while True:
        page = index.list(prefix="task-", limit=500, after=after)
        rows.extend(row["value"] for row in page)
        if len(page) < 500:
            break
        after = page[-1]["key"]
    rows.sort(key=lambda row: row["created_at"], reverse=True)
    return {"items": rows[:50]}


def copy_options(data):
    policy, followup = data.get("policy", "metadata"), data.get("followup", "none")
    if policy not in ("metadata", "verify", "relay") or followup not in (
        "none",
        "organize",
        "sync",
    ):
        raise ValueError("复制策略无效")
    max_gib = float(data.get("max_gib", 10))
    if not math.isfinite(max_gib) or max_gib <= 0:
        raise ValueError("临时空间上限必须大于 0")
    return policy, followup, max_gib


async def submit(storage, index, context, data):
    identity = task_id(data.get("id"))
    previous = index.get("task-" + identity)
    if previous:
        return previous
    source, target = str(data.get("source") or ""), str(data.get("target") or "")
    root, destination = str(data.get("source_root") or "0"), str(data.get("target_root") or "0")
    await catalog(storage, source, target)
    selected = data.get("selected")
    if not isinstance(selected, list) or not selected or len(selected) > 500:
        raise ValueError("请选择 1 至 500 个文件或文件夹")
    selected = {str(value) for value in selected}
    policy, followup, max_gib = copy_options(data)
    items = await selected_items(storage, source, root, selected)
    same = await storage.same_account(source, target)
    if same and root == destination:
        raise ValueError("不能复制到原目录")
    for item in items:
        name = str(item["name"])
        if not name or name in (".", "..") or PurePosixPath(name).name != name or "\\" in name:
            raise ValueError("源文件名称无效")
        if (
            same
            and item.get("directory")
            and (
                str(item["file_id"]) == destination
                or await storage.file_relative_to(target, str(item["file_id"]), destination)
            )
        ):
            raise ValueError("目标目录不能位于所选文件夹内")
    # Validate that the selected destination is still a readable directory before accepting the batch.
    await storage.file_page(target, destination, None)
    config = {
        "source": source,
        "source_root": root,
        "target": target,
        "target_root": destination,
        "policy": policy,
        "followup": followup,
        "max_gib": max_gib,
    }
    return create_manual_batch(context, index, identity, config, items)


def create_manual_batch(context, index, identity, config, items):
    state = context.state.scoped("manual-" + identity)
    state.set(
        "progress",
        {
            "folders": [
                {"id": str(item["file_id"]), "prefix": item["name"], "cursor": None}
                for item in items
                if item.get("directory")
            ],
            "pending": [
                {**item, "relative_path": item["name"]}
                for item in items
                if not item.get("directory")
            ],
        },
    )
    task = {
        "id": identity,
        "config": config,
        "status": "queued",
        "selected": len(items),
        "names": [item["name"] for item in items][:5],
        "created_at": time.time(),
        "processed": 0,
    }
    index.set("task-" + identity, task)
    return task


async def selected_items(storage, source, root, selected):
    # Re-read the current source directory: names, types and checksums are never trusted from the browser.
    items: list[dict[str, Any]] = []
    cursor = None
    while True:
        page = await storage.file_page(source, root, cursor)
        items.extend(item for item in page["items"] if str(item["file_id"]) in selected)
        next_cursor = page.get("cursor")
        if next_cursor is None:
            break
        if next_cursor == cursor:
            raise ValueError("目录分页没有前进")
        cursor = next_cursor
    if {str(item["file_id"]) for item in items} != selected:
        raise ValueError("所选文件已变化，请刷新目录后重新选择")
    return items


def next_pending(index):
    after = ""
    while True:
        rows = index.list(prefix="task-", limit=500, after=after)
        for row in rows:
            if row["value"]["status"] in ("queued", "running"):
                return row["value"]
        if len(rows) < 500:
            return None
        after = rows[-1]["key"]


async def run_one(plugin, context):
    index = context.state.scoped("manual-batches")
    task = next_pending(index)
    if not task:
        return
    identity = task["id"]
    state = context.state.scoped("manual-" + identity)
    progress = state.get("progress")
    batch_context = copy(context)
    batch_context.config = task["config"]
    source, target, destination = (
        task["config"][key] for key in ("source", "target", "target_root")
    )
    storage = context.sdk.require("storage", min_version=2)
    try:
        await plugin.scan_page(
            storage,
            state,
            progress,
            source,
            target,
            destination,
            await storage.same_account(source, target),
        )
        processed = 0
        while progress["pending"] and processed < 20:
            await plugin.copy_one(
                batch_context, storage, state, source, target, destination, progress["pending"][0]
            )
            progress["pending"].pop(0)
            state.set("progress", progress)
            processed += 1
        records = list(records_from(state))
        task.update(
            processed=len(records),
            pending=len(progress["pending"]),
            directories=len(progress["folders"]),
            completed=sum(row["status"] == "completed" for row in records),
            attention=sum(row["status"] != "completed" for row in records),
        )
        task["status"] = "running" if progress["pending"] or progress["folders"] else "completed"
    except Exception as exc:
        task.update(status="failed", error=str(exc))
    task["updated_at"] = time.time()
    index.set("task-" + identity, task)
