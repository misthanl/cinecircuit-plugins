"""Human-readable result text shared by ranking subscription plugins."""
import re

from .rank_statistics import REASONS

LABELS = {
    "subscribed": "已添加订阅", "already_subscribed": "已订阅，跳过",
    "in_library": "已入库，跳过", "duplicate": "已被其他任务订阅，跳过",
    "skipped": "已跳过", "unknown": "无法确认，暂缓并在下次重试",
    "not_recognized": "未确认媒体身份，下次重试", "preview": "仅预览，未添加订阅",
}


def result_text(result):
    label = LABELS.get(str(result.get("status") or ""), "结果待确认，请查看详情")
    code = str(result.get("reason") or "")
    reason = REASONS.get(code, code if re.search(r"[\u4e00-\u9fff]", code) else "")
    return f"{label}（{reason}）" if reason and reason != label else label
