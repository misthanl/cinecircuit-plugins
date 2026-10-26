"""A display label bounds live brush inventory; receipts still prove ownership."""

BRUSH_TAG = "刷流"


def brush_tagged(task):
    raw = task.get("tags") or ""
    tags = raw if isinstance(raw, (list, tuple, set)) else str(raw).split(",")
    return BRUSH_TAG in {str(tag).strip() for tag in tags}


async def tagged_downloads(context):
    if getattr(context, "sdk", None) is not None:
        context.sdk.require("downloads", min_version=2)
    result = {}
    for offset in range(0, 10001, 200):
        page = await context.downloads.list_tagged_tasks(BRUSH_TAG, offset=offset, limit=200)
        if page.get("errors"):
            raise RuntimeError("刷流任务列表读取失败，暂不计算限额或执行清理")
        items = page.get("items") or []
        for task in items:
            if brush_tagged(task):
                result[
                    (str(task.get("downloader_id") or ""), str(task.get("hash") or "").casefold())
                ] = task
        if len(items) < 200:
            return result
    raise RuntimeError("刷流任务列表超过安全分页范围，暂不执行")
