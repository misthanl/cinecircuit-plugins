def field(key, label, kind="text", default=None, **options):
    return {"key": key, "label": label, "input_type": kind, "default": default, **options}


FIELDS = [
    field("enabled", "启用自动辅种", "switch", False),
    field("onlyonce", "立即执行一次", "switch", False, visible=False),
    field("notification_enabled", "发送通知", "switch", False),
    field("cron", "执行周期", "cron", ""),
    field("token", "IYUU Token", "text", "", secret=True),
    field(
        "downloaders",
        "来源下载器",
        "resource_multi_select",
        [],
        resource_kind="downloader",
        required_capabilities=["read"],
    ),
    field(
        "auto_downloader",
        "独立辅种下载器",
        "resource_select",
        "",
        resource_kind="downloader",
        required_capabilities=["add"],
    ),
    field(
        "sites",
        "辅种站点",
        "resource_multi_select",
        [],
        resource_kind="site",
        required_capabilities=[],
    ),
    field("nolabels", "不辅种标签", "text", ""),
    field("nopaths", "不辅种数据目录", "textarea", ""),
    field("size", "最小辅种体积（GiB）", "number", 0, validation={"minimum": 0}),
    field("labelsafterseed", "辅种后增加标签", "text", "辅种"),
    field("categoryafterseed", "辅种分类", "text", ""),
    field("addhosttotag", "将站点名加入标签", "switch", False),
    field("auto_category", "复用原分类（仅 qB）", "switch", False),
    field("reuse_save_path", "沿用原种保存路径（仅 qB）", "switch", True),
    field(
        "skipverify",
        "跳过校验（仅 qB）",
        "switch",
        False,
        description="默认校验现有数据；跳过校验需自行确认文件完整。",
    ),
    field("auto_start", "跳过校验后自动开始", "switch", False),
    field("clearcache", "清除成功和失败缓存", "switch", False),
]


def schema():
    return {
        "editor_width": 920,
        "description_display": "hidden",
        "layout": {"columns": 2, "row_gap": 14, "column_gap": 16},
        "fields": FIELDS,
    }
