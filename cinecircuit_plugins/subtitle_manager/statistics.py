"""Versioned presentation data recorded in the existing plugin execution result."""

from typing import Any


def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "version": 1,
        "media": len(items),
        "saved": 0,
        "skipped": 0,
        "failed": 0,
        "completed_media": 0,
        "bilingual": 0,
        "converted": 0,
        "rows": [],
    }
    reasons = {
        "chinese_media": "按设置跳过中文原声媒体",
        "media_path_unavailable": "媒体路径不可访问",
    }
    for item in items:
        media = str(
            item.get("title")
            or str(item.get("media_path") or "").replace("\\", "/").rsplit("/", 1)[-1]
            or "未知媒体"
        )
        count = len(item.get("saved") or [])
        summary["saved"] += count
        if count:
            summary["completed_media"] += 1
            for row in item.get("details") or []:
                summary["bilingual"] += int(bool(row.get("bilingual")))
                summary["converted"] += int(bool(row.get("converted")))
                summary["rows"].append({**row, "media": media})
        else:
            failed = bool(item.get("failed"))
            summary["failed" if failed else "skipped"] += 1
            reason = reasons.get(str(item.get("reason") or "")) or (
                "字幕候选下载、校验或保存失败，请查看运行与审计"
                if failed
                else "没有找到字幕候选"
                if not item.get("candidate_count")
                else "未保存：已有同名字幕或没有匹配的有效字幕"
            )
            summary["rows"].append(
                {
                    "media": media,
                    "status": "failed" if failed else "skipped",
                    "reason": reason,
                }
            )
    summary["total_rows"] = len(summary["rows"])
    summary["rows"] = summary["rows"][:500]
    return summary
