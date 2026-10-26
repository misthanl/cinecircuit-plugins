"""Shared lifecycle for independently installed seed-management plugins."""

from datetime import datetime
from hashlib import sha256
from pathlib import PurePosixPath
import re
from time import time
from zoneinfo import ZoneInfo


def labels(raw):
    return {
        str(v).strip()
        for v in (raw if isinstance(raw, list) else str(raw or "").replace("，", ",").split(","))
        if str(v).strip()
    }


def complete(task):
    return bool(
        task
        and float(task.get("progress") or 0) >= 100
        and int(task.get("amount_left") or 0) == 0
        and not task.get("errored")
        and not str(task.get("state", "")).lower().startswith("check")
        and str(task.get("state", "")) not in {"1", "2"}
    )


def under(path, prefix):
    path, prefix = PurePosixPath(str(path)), PurePosixPath(str(prefix))
    return path == prefix or prefix in path.parents


def excluded(task, config):
    # Brush sources are intentionally outside this release's selected workflow.
    if "刷流" in labels(task.get("tags")):
        return True
    if labels(task.get("tags")) & labels(config.get("nolabels")):
        return True
    return any(
        under(task.get("save_path", ""), line.strip())
        for line in str(config.get("nopaths") or "").splitlines()
        if line.strip()
    )


def map_path(path, old, new):
    old_lines = [v.strip() for v in str(old or "").splitlines() if v.strip()]
    new_lines = [v.strip() for v in str(new or "").splitlines() if v.strip()]
    if not old_lines and not new_lines:
        return str(path)
    if len(old_lines) != len(new_lines):
        raise ValueError("源目录和目标目录映射行数不一致")
    for source, target in sorted(
        zip(old_lines, new_lines), key=lambda pair: len(pair[0]), reverse=True
    ):
        if under(path, source):
            return str(PurePosixPath(target) / PurePosixPath(path).relative_to(source))
    raise ValueError("保存目录未命中路径映射")


async def inventory(sdk, uid):
    items = []
    for offset in range(0, 100001, 500):
        page = await sdk.inventory(uid, offset=offset, limit=500, completed_only=True)
        items.extend(page["items"])
        if len(items) >= page["total"]:
            return items
    raise ValueError("下载器任务数量超过分页上限")


def key_for(*values):
    return sha256(str(values).encode()).hexdigest()


def rows(context, status):
    result: list[dict] = []
    while True:
        page = context.items.list(500, offset=len(result), status=status)
        result.extend(page)
        if len(page) < 500:
            return result


def error_text(error):
    # URLs can contain tracker passkeys. Never persist them in a job receipt.
    return re.sub(r"https?://\S+", "[url]", str(error))[:240]


def record(context, key, status, payload, result):
    return context.items.record(
        key, status, payload=payload, result={**result, "timestamp": time()}
    )


def payload_for(source):
    return {k: source.get(k) for k in ("name", "hash", "downloader_id", "added_on", "save_path")}


def due(context):
    once = context.sdk.require("configuration", min_version=1).consume_switch("onlyonce")
    if once:
        return True
    if getattr(context, "trigger", "manual") != "scheduled":
        return True
    if not context.config.get("enabled", False):
        return False
    expression = str(context.config.get("cron") or "").strip()
    if not expression:
        return False
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("执行周期必须是 5 位 Cron 表达式")
    current = datetime.now(ZoneInfo("Asia/Shanghai"))

    allowed = [
        cron_values(f, *bounds)
        for f, bounds in zip(fields, ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7)))
    ]
    if 7 in allowed[4]:
        allowed[4].add(0)
    if not all(
        v in a
        for v, a in zip(
            (current.minute, current.hour, current.day, current.month, (current.weekday() + 1) % 7),
            allowed,
        )
    ):
        return False
    state = context.state.scoped("schedule")
    minute = current.strftime("%Y-%m-%d %H:%M")
    if state.get("last_minute") == minute:
        return False
    state.set("last_minute", minute)
    return True


async def queue(
    context, sdk, key, source, receipt, *, auto_start, remove_source=False, skip_checking=False
):
    data = {
        "receipt": receipt,
        "source": payload_for(source),
        "auto_start": bool(auto_start),
        "remove_source": bool(remove_source),
        "skip_checking": bool(skip_checking),
    }
    record(context, key, "submitted", payload_for(source), data)
    if not receipt.get("ownership_verified"):
        record(
            context,
            key,
            "attention",
            payload_for(source),
            {**data, "error": "下载器未确认新任务归属，请人工检查"},
        )
        return
    if not skip_checking:
        await sdk.operate(
            receipt["downloader_id"], receipt["hash"], "recheck", added_on=receipt["task_added_on"]
        )
    record(context, key, "checking" if not skip_checking else "ready", payload_for(source), data)


async def check_queue(context, sdk):
    counts = {"checked": 0, "started": 0, "source_removed": 0, "errors": 0}
    seen = set()
    for status in ("submitted", "checking", "ready"):
        for row in rows(context, status):
            if row["item_key"] in seen:
                continue
            seen.add(row["item_key"])
            data = row["result"]
            receipt = data.get("receipt") or {}
            if not receipt.get("ownership_verified"):
                continue
            counts["checked"] += 1
            try:
                await check_row(context, sdk, row, counts)
            except Exception as error:
                counts["errors"] += 1
                next_status = "attention" if "重新添加" in str(error) else row["status"]
                record(
                    context,
                    row["item_key"],
                    next_status,
                    row.get("payload"),
                    {**data, "error": error_text(error)},
                )
    return counts


async def statistics(context):
    counts = {
        status: len(rows(context, status))
        for status in (
            "submitted",
            "checking",
            "ready",
            "seeding",
            "paused",
            "failed",
            "attention",
            "duplicate",
            "missing",
        )
    }
    history = context.items.list(200)
    return {
        "counts": counts,
        "items": [
            {
                "id": r["item_key"],
                "name": r.get("payload", {}).get("name") or "—",
                "status": r["status"],
                "hash": r.get("payload", {}).get("hash", ""),
                "error": r.get("result", {}).get("error", ""),
                "timestamp": r.get("result", {}).get("timestamp", 0),
            }
            for r in history
        ],
    }


async def notify(context, name, result):
    if context.config.get("notification_enabled", False):
        await context.notifications.send(
            name,
            f"成功 {result.get('added', 0)}，跳过 {result.get('skipped', 0)}，失败 {result.get('failed', 0)}",
            notification_type="plugin",
        )


def cron_values(text, low, high):
    found: set[int] = set()
    for chunk in text.split(","):
        if not re.fullmatch(r"(?:\*|\d+(?:-\d+)?)(?:/\d+)?", chunk):
            raise ValueError("无效的 Cron 表达式")
        base, slash, step = chunk.partition("/")
        step = int(step) if slash else 1
        start, end = (
            (low, high)
            if base == "*"
            else (
                tuple(map(int, base.split("-")))
                if "-" in base
                else (int(base), high if slash else int(base))
            )
        )
        if step < 1 or start < low or end > high or start > end:
            raise ValueError("无效的 Cron 范围")
        found.update(range(start, end + 1, step))
    return found


async def check_row(context, sdk, row, counts):
    status = row["status"]
    data = row["result"]
    receipt = data.get("receipt") or {}
    source = data.get("source") or {}
    if status == "submitted" and not data.get("skip_checking"):
        await sdk.operate(
            receipt["downloader_id"],
            receipt["hash"],
            "recheck",
            added_on=receipt["task_added_on"],
        )
        record(context, row["item_key"], "checking", row.get("payload"), data)
        return
    target = await sdk.inspect(
        receipt["downloader_id"], receipt["hash"], added_on=receipt["task_added_on"]
    )
    if target is None:
        record(context, row["item_key"], "missing", row.get("payload"), data)
        return
    if not complete(target):
        return
    if data.get("auto_start"):
        await sdk.operate(
            receipt["downloader_id"],
            receipt["hash"],
            "start",
            added_on=receipt["task_added_on"],
        )
        counts["started"] += 1
    if data.get("remove_source"):
        await sdk.operate(
            source["downloader_id"],
            source["hash"],
            "remove",
            added_on=source["added_on"],
        )
        counts["source_removed"] += 1
    record(
        context,
        row["item_key"],
        "seeding" if data.get("auto_start") else "paused",
        row.get("payload"),
        data,
    )
