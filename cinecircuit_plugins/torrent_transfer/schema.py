def field(key, label, kind="text", default=None, **options):
    return {"key": key, "label": label, "input_type": kind, "default": default, **options}


FIELDS = [
    field("enabled", "启用自动转移", "switch", False),
    field("notification_enabled", "发送通知", "switch", False),
    field("transferemptylabel", "转移无标签种子", "switch", False),
    field("cron", "执行周期", "cron", ""),
    field(
        "fromdownloader",
        "源下载器",
        "resource_select",
        "",
        resource_kind="downloader",
        required_capabilities=["read"],
    ),
    field(
        "todownloader",
        "目标下载器",
        "resource_select",
        "",
        resource_kind="downloader",
        required_capabilities=["add"],
    ),
    field(
        "fromtorrentpath",
        "源种子文件目录",
        "text",
        "",
    ),
    field(
        "path_mappings",
        "保存目录映射",
        "textarea",
        "",
        placeholder="每行一组：源目录#目标目录；留空沿用原路径。",
    ),
    field("frompath", "源保存目录映射", "textarea", "", visible=False),
    field("topath", "目标保存目录映射", "textarea", "", visible=False),
    field(
        "includelabels",
        "转移做种标签",
        "text",
        "",
    ),
    field("includecategory", "转移分类", "text", ""),
    field("nolabels", "不转移做种标签", "text", ""),
    field("nopaths", "不转移数据目录", "textarea", ""),
    field("add_torrent_tags", "目标新增标签", "text", "转移做种"),
    field("remainoldcat", "保留源分类", "switch", False),
    field("remainoldtag", "保留源标签", "switch", False),
    field(
        "skipverify",
        "跳过校验（仅 qB）",
        "switch",
        False,
    ),
    field("autostart", "校验完成后自动开始", "switch", False),
    field(
        "deletesource",
        "转移成功后删除源任务",
        "switch",
        False,
    ),
    field(
        "deleteduplicate",
        "目标重复时删除源任务",
        "switch",
        False,
    ),
    field("onlyonce", "立即执行一次", "switch", False, visible=False),
]


def schema():
    return {
        "editor_width": 920,
        "description_display": "hidden",
        "layout": {"columns": 2, "row_gap": 14, "column_gap": 16},
        "fields": FIELDS,
    }
