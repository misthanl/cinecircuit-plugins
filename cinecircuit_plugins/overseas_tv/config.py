"""Overseas TV settings rendered entirely by the host SchemaFields component."""

from typing import Any

PLATFORMS = (
    ("netflix", "Netflix", "213"),
    ("hbo", "HBO", "49"),
    ("disney", "Disney+", "2739"),
    ("apple", "Apple TV", "2552"),
    ("amazon", "Prime Video", "1024"),
    ("hulu", "Hulu", "453"),
)


def field(key, label, kind="select", default=None, options=None, **extra):
    result = {"key": key, "label": label, "input_type": kind, "default": default, **extra}
    if options is not None:
        result["options"] = [{"value": str(value), "label": str(title)} for value, title in options]
    return result


def numbers(*values):
    return [(str(value), str(value)) for value in values]


SCHEMA: dict[str, Any] = {
    "description_display": "hidden",
    "layout": {"columns": 2, "row_gap": 14, "column_gap": 16},
    "fields": [
        field("clear", "清理历史记录", "switch", False),
        field("cron", "执行周期", "cron", "", description="留空每 6 小时执行；按剧集和季号去重。"),
        field("max_new", "每轮新增季数", default="10", options=numbers(1, 3, 5, 10, 20)),
        field(
            "modes",
            "订阅类型",
            default=["new", "returning"],
            multiple=True,
            required=True,
            options=[
                ("new", "新剧首播"),
                ("returning", "老剧新季"),
                ("popular", "近期热门（TMDB 热度）"),
            ],
        ),
        field("past_days", "回溯天数", default="30", options=numbers(7, 14, 30, 60, 90)),
        field("future_days", "提前订阅天数", default="14", options=numbers(0, 7, 14, 30)),
        field("min_rating", "最低评分", default="7", options=numbers(0, 6, 7, 7.5, 8, 8.5, 9)),
        field("min_votes", "最低评价人数", default="50", options=numbers(10, 30, 50, 100, 300)),
        field("allow_unrated", "允许评价不足的新剧／新季", "switch", True),
        field(
            "country",
            "出品国家",
            default="",
            options=[
                ("", "全部国家"),
                ("US", "美国"),
                ("GB", "英国"),
                ("KR", "韩国"),
                ("JP", "日本"),
            ],
        ),
        field(
            "language",
            "原始语言",
            default="",
            options=[
                ("", "全部语言"),
                ("en", "英语"),
                ("ko", "韩语"),
                ("ja", "日语"),
                ("es", "西班牙语"),
            ],
        ),
        field(
            "include_types",
            "包含类型",
            default=[],
            multiple=True,
            options=[
                ("animation", "动画"),
                ("documentary", "纪录片"),
                ("reality", "真人秀／脱口秀"),
            ],
        ),
        *[
            item
            for key, label, _ in PLATFORMS
            for item in (
                field(f"{key}_enabled", f"{label} 自动订阅", "switch", True),
                field(
                    f"{key}_num",
                    f"{label} 候选剧集上限",
                    default="10",
                    options=numbers(10, 20, 40, 60),
                ),
            )
        ],
    ],
}


def normalized(config):
    result = {item["key"]: item["default"] for item in SCHEMA["fields"]}
    result.update({key: value for key, value in config.items() if key in result})
    if "include_types" not in config:
        result["include_types"] = [
            key for key in ("animation", "documentary", "reality") if config.get(key) is True
        ]
    for item in SCHEMA["fields"]:
        value = result[item["key"]]
        if item["input_type"] == "switch" and not isinstance(value, bool):
            raise ValueError(f"{item['label']}必须为开关值")
        if item.get("options"):
            values = value if item.get("multiple") else [value]
            allowed = {option["value"] for option in item["options"]}
            if not isinstance(values, list) or any(str(v) not in allowed for v in values):
                raise ValueError(f"{item['label']}选项无效")
    if not result["modes"] or not any(result[f"{key}_enabled"] for key, _, _ in PLATFORMS):
        raise ValueError("请至少选择一种订阅类型和一个平台")
    return result
