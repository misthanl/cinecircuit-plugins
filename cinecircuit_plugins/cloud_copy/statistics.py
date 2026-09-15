"""Read persisted journals with a bounded display window, without remote scans."""

from heapq import nsmallest
from pathlib import PurePosixPath
import time

from .journal import records_from, iter_batches

PAGE_SIZE = 8
WINDOW_SIZE = 256


def rule_scope(plugin, context):
    try:
        source, _, target, _, rule = plugin.settings(context, validate_policy=False)
    except ValueError as exc:
        return None, "", "", str(exc)
    return context.state.scoped("copy-" + rule), source, target, ""


def record_scopes(context, rule):
    state, source, target, _ = rule
    if state is not None:
        progress = state.get("progress") or {}
        active = bool(
            progress.get("pending") or progress.get("folders") or state.get("rescan_requested")
        )
        yield state, progress, "rule", source, target, "", active
    for task in iter_batches(context.state.scoped("manual-batches")):
        if task.get("hidden"):
            continue
        state = context.state.scoped("manual-" + task["id"])
        config = task["config"]
        active = task.get("status") in ("queued", "running")
        yield (
            state,
            state.get("progress") or {},
            "manual",
            config["source"],
            config["target"],
            task["id"],
            active,
        )


def matches(row, query):
    search = str(query.get("search") or "").casefold()
    return (not search or search in str(row.get("path", "")).casefold()) and all(
        not query.get(field) or row.get(field) == query[field]
        for field in ("status", "method", "origin")
    )


def visible_records(scope):
    state, _, origin, source, target, batch_id, active = scope
    return (
        present_record(row, origin, source, target, batch_id, active)
        for row in records_from(state)
        if not row.get("hidden")
    )


def summarize(context, rule, query):
    counts = {"completed": 0, "skipped": 0, "attention": 0, "pending": 0}
    buckets = {
        "completed": "completed",
        "copied": "completed",
        "skipped": "skipped",
        "conflict": "attention",
        "uncertain": "attention",
        "retry": "attention",
        "failed": "attention",
    }
    total, directories, configured = 0, 0, False
    for scope in record_scopes(context, rule):
        configured = True
        _, progress, origin, _, _, _, active = scope
        if origin == "rule" or active:
            counts["pending"] += len(progress.get("pending", []))
            directories += len(progress.get("folders", []))
        for row in visible_records(scope):
            bucket = buckets.get(row.get("status"))
            if bucket:
                counts[bucket] += 1
            total += bool(matches(row, query))
    return counts, total, directories, configured


def order_key(row):
    return -float(row.get("updated_at") or 0), row["row_key"]


def filtered_records(context, rule, query, after):
    for scope in record_scopes(context, rule):
        for row in visible_records(scope):
            if matches(row, query) and (after is None or order_key(row) > after):
                yield row


def page_records(context, rule, query, page):
    # The state SDK exposes key scans, not sorted field queries. Keep at most
    # 256 rows; unusually deep pages rescan in bounded windows instead of
    # materializing every journal. Common pages require only one display scan.
    remaining, after = page * PAGE_SIZE, None
    while remaining:
        size = min(remaining, WINDOW_SIZE)
        window = nsmallest(size, filtered_records(context, rule, query, after), key=order_key)
        if remaining <= WINDOW_SIZE:
            return window[max(0, size - PAGE_SIZE) :]
        if len(window) < size:
            return []
        after = order_key(window[-1])
        remaining -= size
    return []


def page_number(query, pages):
    try:
        return min(pages, max(1, int(query.get("page") or 1)))
    except (ValueError, TypeError):
        return 1


async def snapshot(plugin, request, context):
    rule = rule_scope(plugin, context)
    state, _, _, configuration_message = rule
    counts, total, directories, configured = summarize(context, rule, request.query)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = page_number(request.query, pages)
    records = page_records(context, rule, request.query, page) if total else []
    catalog = (
        await context.sdk.require("storage", min_version=2).configurations() if records else {}
    )
    names = {row["id"]: row["name"] for row in catalog.get("items", [])}
    return {
        "configured": configured,
        "rule_configured": state is not None,
        "configuration_message": configuration_message,
        "counts": counts,
        "records": [
            {
                **row,
                "name": PurePosixPath(row.get("path") or "").name,
                "source_name": names.get(row["source"], row["source"]),
                "target_storage_name": names.get(row["target"], row["target"]),
            }
            for row in records
        ],
        "total": total,
        "page": page,
        "pages": pages,
        "next_cursor": None,
        "pending": counts["pending"],
        "directories": directories,
        "paused": bool(state and state.get("paused", False)),
        "updated_at": time.time(),
    }


def present_record(row, origin, source, target, batch_id="", active=False):
    return {
        **row,
        "origin": origin,
        "batch_id": batch_id,
        "source": source,
        "target": target,
        "row_key": f"{origin}:{batch_id}:{row['identity']}",
        "can_retry": not active
        and row.get("status") in ("failed", "uncertain", "conflict", "skipped", "copied"),
        "can_delete": not active,
    }
