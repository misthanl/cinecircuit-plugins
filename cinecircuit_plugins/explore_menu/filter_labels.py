"""Compact filter captions without changing any provider query values."""

from copy import deepcopy

LABELS = {
    "tencent": {"ipay": "资费", "producer": "出品", "characteristic": "规格", "anime_status": "状态",
                "item": "制式", "exclusive": "出品", "itrailer": "出品", "child_ip": "角色", "all": "主题",
                "one": "主题", "two": "主题", "three": "主题", "ten": "主题", "all_year": "主题"},
    "youku": {"status": "规格", "theatre": "剧场", "completed": "状态", "company": "出品",
              "show_label_type": "类型", "age": "年龄", "child_tags": "分类"},
    "iqiyi": {"category_32795": "类型", "category_28467": "出品", "category_20288": "年龄", "category_28982": "课程"},
}
SORT_LABELS = {"综合排序": "综合", "高分好评": "高分", "热度最高": "最热",
               "最新上架": "最新", "最新上线": "最新", "新上线": "最新",
               "热播榜": "热播", "好评榜": "好评", "最好评": "好评", "最多播放": "播放"}


def present_filters(source, definitions):
    result = deepcopy(definitions)
    for key, group in result.items():
        group["label"] = LABELS.get(source, {}).get(key, group.get("label", key))
        for choice in group.get("options", []):
            if key == "sort":
                choice["label"] = SORT_LABELS.get(choice["label"], choice["label"])
            elif str(choice.get("value", "")) in {"", "-1", "a1", "all"}:
                choice["label"] = "全部"
    return result
