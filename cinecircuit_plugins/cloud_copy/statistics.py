"""Read journal records without remote directory requests."""
from pathlib import PurePosixPath
import time


def records_from(state):
    after = ""
    while True:
        groups = state.list(prefix="records-", limit=500, after=after)
        for group in groups:
            for identity, record in (group.get("value") or {}).items():
                yield {**record, "identity": identity}
        if len(groups) < 500:
            return
        next_after = groups[-1]["key"]
        if next_after <= after:
            raise ValueError("复制记录分页没有前进")
        after = next_after


async def snapshot(plugin, request, context):
    empty = {"configured": False, "records": [], "total": 0, "page": 1,
             "pages": 1, "counts": {}, "pending": 0, "directories": 0, "paused": False}
    try:
        source, _, target, _, rule = plugin.settings(context)
    except ValueError as exc:
        return {**empty, "configuration_message": str(exc), "next_cursor": None}
    state = context.state.scoped("copy-" + rule)
    progress = state.get("progress") or {}
    catalog = await context.sdk.require("storage", min_version=2).configurations()
    names = {row["id"]: row["name"] for row in catalog.get("items", [])}
    records = list(records_from(state))
    counts = {"completed": 0, "skipped": 0, "attention": 0, "pending": len(progress.get("pending", []))}
    for row in records:
        status = row.get("status")
        if status in ("completed", "copied"):
            counts["completed"] += 1
        elif status == "skipped":
            counts["skipped"] += 1
        elif status in ("conflict", "uncertain", "retry", "failed"):
            counts["attention"] += 1
    query = request.query
    search = str(query.get("search") or "").casefold()
    status, method = query.get("status"), query.get("method")
    records = [row for row in records if
               (not search or search in str(row.get("path", "")).casefold()) and
               (not status or row.get("status") == status) and
               (not method or row.get("method") == method)]
    records.sort(key=lambda row: (-float(row.get("updated_at") or 0), row["identity"]))
    pages = max(1, (len(records) + 7) // 8)
    try:
        page = min(pages, max(1, int(query.get("page") or 1)))
    except (ValueError, TypeError):
        page = 1
    return {"configured": True, "counts": counts, "records": [
        {**row, "name": PurePosixPath(row.get("path") or "").name,
         "source_name": names.get(source, source), "target_storage_name": names.get(target, target)}
        for row in records[(page-1)*8:page*8]], "total": len(records), "page": page, "pages": pages,
        "pending": counts["pending"], "directories": len(progress.get("folders", [])),
        "paused": bool(state.get("paused", False)), "updated_at": time.time()}
