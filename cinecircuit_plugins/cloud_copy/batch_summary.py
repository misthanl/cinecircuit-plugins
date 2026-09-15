"""User-facing batch outcomes derived from the actual file records."""
from collections import Counter
from .journal import records_from


def present_batch(task, state):
    records = [row for row in records_from(state) if not (
        task["status"] == "running" and row["status"] == "uncertain"
        and row.get("path") == task.get("current_file")
    )]
    counts = Counter(row["status"] for row in records)
    details = {
        "completed": counts["completed"], "skipped": counts["skipped"],
        "uncertain": counts["uncertain"], "conflicts": counts["conflict"],
        "awaiting_handoff": counts["copied"],
        "failed_files": sum(value for key, value in counts.items()
                            if key not in {"completed", "skipped", "uncertain", "conflict", "copied"}),
    }
    outcome = task["status"]
    if outcome == "completed" and any(key != "completed" for key in counts):
        outcome = "partial" if counts["completed"] else next(
            (status for status in ("uncertain", "conflict", "copied", "skipped")
             if counts[status] == len(records)), "failed"
        )
    notes = list(dict.fromkeys(reason_text(row) for row in records if row["status"] != "completed"))
    methods = list(dict.fromkeys(row["method"] for row in records if row.get("method")))
    inactive = task["status"] not in ("queued", "running")
    progress = state.get("progress") or {}
    retryable = any(not row.get("hidden") and row["status"] in ("failed", "uncertain", "conflict", "skipped", "copied") for row in records)
    return {**task, **details, "outcome": outcome, "notes": notes[:3], "methods": methods,
            "can_delete": inactive,
            "can_retry": inactive and bool(retryable or progress.get("pending") or progress.get("folders"))}


def reason_text(row):
    reasons = {
        "rapid_material_unavailable": "当前策略无法直接秒传，请选择读取源文件验证秒传或服务器中转上传。",
        "rapid_not_matched": "未命中秒传，文件未复制；可选择服务器中转上传。",
    }
    if row.get("reason") in reasons:
        return reasons[row["reason"]]
    return {
        "skipped": "文件已跳过，具体原因请查看运行日志。",
        "uncertain": "复制结果尚未确认，请先检查目标网盘中的文件。",
        "conflict": "目标存在同名冲突，请检查目标文件。",
        "copied": "文件已复制，后续处理尚未完成。",
    }.get(row["status"], "文件未处理成功，具体原因请查看运行日志。")


def result_message(task):
    labels = (("completed", "已复制"), ("skipped", "已跳过"), ("uncertain", "结果待确认"),
              ("conflicts", "同名冲突"), ("awaiting_handoff", "等待后续处理"), ("failed_files", "失败"))
    return "，".join(f"{label} {task.get(key, 0)}" for key, label in labels
                    if key == "completed" or task.get(key))
