"""User-selected batches, persisted independently of the automatic rule."""

from copy import copy
from pathlib import PurePosixPath
import math
import re
import time
from typing import Any

from .journal import records_from, all_batches
from .batch_summary import present_batch, result_message


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
        return list_batches(index, context)
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


def list_batches(index, context=None):
    rows = [row for row in all_batches(index) if not row.get("hidden")]
    return {"items": [present_batch(row, context.state.scoped("manual-" + row["id"]))
                      if context else row for row in rows[:50]]}


def require_temporary_directory(data):
    directory = str(data.get("temporary_directory") or "").strip()
    if data.get("policy", "metadata") != "metadata" and not directory:
        raise ValueError("请先在插件配置中设置临时目录，再使用读取源文件验证秒传或服务器中转上传")
    return directory


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
    temporary_directory = require_temporary_directory({**data, "temporary_directory": context.config.get("temporary_directory", "")})
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
        "temporary_directory": temporary_directory,
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
    batch_context.config = {**task["config"], "temporary_directory": context.config.get("temporary_directory", "")}
    source, target, destination = (
        task["config"][key] for key in ("source", "target", "target_root")
    )
    storage = context.sdk.require("storage", min_version=2)
    task.update(status="running", phase="正在扫描所选目录", current_file="", updated_at=time.time())
    index.set("task-" + identity, task)
    context.logger.info("手动复制批次 %s 开始：%s → %s", identity, source, target)
    try:
        require_temporary_directory(batch_context.config)
        await plugin.scan_page(
            storage,
            state,
            progress,
            source,
            target,
            destination,
            await storage.same_account(source, target),
        )
        await process_pending(plugin, batch_context, storage, state, index, task, progress)
        refresh_counts(task, state, progress)
        task["status"] = "running" if progress["pending"] or progress["folders"] else "completed"
    except Exception as exc:
        task.update(status="failed", error=str(exc))
        context.logger.exception("手动复制批次 %s 执行失败", identity)
    task.update(current_file="", phase="等待下一轮处理" if task["status"] == "running" else "", updated_at=time.time())
    index.set("task-" + identity, task)
    summary = present_batch(task, state)
    message = f"手动复制批次 {identity}：{result_message(summary)}"
    context.logger.info("%s，状态=%s", message, summary["outcome"])
    result_status = {"completed": "success", "running": "success"}.get(summary["outcome"], summary["outcome"])
    return {"status": result_status, "message": message, "batch_id": identity, "error": task.get("error", "")}


def refresh_counts(task, state, progress):
    records = list(records_from(state))
    task.update(processed=len(records), completed=sum(row["status"] == "completed" for row in records), attention=sum(row["status"] != "completed" for row in records), pending=len(progress["pending"]), directories=len(progress["folders"]), updated_at=time.time())


async def process_pending(plugin, context, storage, state, index, task, progress):
    identity = task["id"]
    source, target, destination = (task["config"][key] for key in ("source", "target", "target_root"))
    for _ in range(20):
        if not progress["pending"]:
            break
        item = progress["pending"][0]
        path = item.get("relative_path") or item["name"]
        phase = "正在校验并尝试秒传" if task["config"]["policy"] == "verify" else "正在复制"
        task.update(current_file=path, phase=phase, updated_at=time.time())
        index.set("task-" + identity, task)
        context.logger.info("手动复制批次 %s：开始处理 %s", identity, path)
        await plugin.copy_one(context, storage, state, source, target, destination, item)
        progress["pending"].pop(0)
        state.set("progress", progress)
        refresh_counts(task, state, progress)
        index.set("task-" + identity, task)
        record: dict[str, Any] = next((row for row in records_from(state) if row["path"] == path), {})
        context.logger.info("手动复制批次 %s：%s，结果=%s，原因=%s", identity, path, record.get("status", "unknown"), record.get("reason") or "无")
