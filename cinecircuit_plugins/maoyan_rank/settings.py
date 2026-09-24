"""Ranking configuration, including migration of the former Maoyan categories."""
CATEGORIES = {"movie": "电影", "tv": "电视剧", "anime": "动漫", "variety": "综艺", "documentary": "纪录片"}
PLATFORMS = {"tx": "腾讯视频", "iqy": "爱奇艺", "mg": "芒果 TV", "yk": "优酷"}


def normalized(config):
    result = dict(config)
    old = config.get("type", ["movie"])
    if not isinstance(old, list):
        old = str(old).replace("，", ",").split(",")
    result.setdefault("movie_enabled", "movie" in old)
    result.setdefault("platform_types", [key for key, names in (("tv", ("web-heat", "web-tv")), ("variety", ("zongyi",))) if any(name in old for name in names)])
    selected = result["platform_types"]
    if not isinstance(selected, list):
        selected = str(selected).replace("，", ",").split(",")
    result["platform_types"] = [key for key in CATEGORIES if key in selected]
    for key in PLATFORMS:
        if config.get("all_enabled") and "platform_types" not in config:
            result[f"{key}_enabled"] = True
        else:
            result.setdefault(f"{key}_enabled", False)
    return result


def count_field(key, label):
    return {"key": key, "input_type": "select", "label": label, "default": "10",
            "options": [{"value": str(n), "label": str(n)} for n in (1, 2, 3, 5, 7, 10)]}


CONFIG_SCHEMA = {
    "description_display": "hidden", "layout": {"columns": 2, "row_gap": 14, "column_gap": 16},
    "fields": [
        {"key": "clear", "input_type": "switch", "label": "清理历史记录", "default": False},
        {"key": "cron", "input_type": "cron", "label": "执行周期", "default": "", "placeholder": "5位cron表达式，留空自动"},
        {"key": "movie_enabled", "input_type": "switch", "label": "猫眼电影票房榜", "default": True},
        count_field("num", "电影票房榜条数"),
        {"key": "platform_types", "input_type": "select", "multiple": True, "label": "媒体分类", "default": [],
         "description": "芒果 TV 的搜索榜不提供纪录片分类。",
         "options": [{"value": key, "label": label} for key, label in CATEGORIES.items()]},
        *[field for key, label in PLATFORMS.items() for field in (
            {"key": f"{key}_enabled", "input_type": "switch",
             "label": f"{label}热搜榜", "default": False},
            count_field(f"{key}_num", f"{label}每类条数"),
        )],
    ],
}
