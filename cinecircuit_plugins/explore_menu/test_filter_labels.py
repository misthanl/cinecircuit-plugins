from copy import deepcopy

import pytest

from .filter_labels import present_filters


@pytest.mark.parametrize("source,key,label,expected,sentinel", [
    ("tencent", "ipay", "免费/VIP", "资费", "-1"),
    ("tencent", "producer", "出品方", "出品", "-1"),
    ("tencent", "characteristic", "院线/网络", "规格", "-1"),
    ("youku", "status", "全部规格", "规格", ""),
    ("youku", "theatre", "全部剧场", "剧场", ""),
    ("iqiyi", "category_18000", "地区", "地区", ""),
    ("mango", "feature", "状态", "状态", "all"),
    ("tencent", "child_ip", "动画明星", "角色", "-1"),
    ("tencent", "one", "0-3岁", "主题", "-1"),
    ("tencent", "two", "4-6岁", "主题", "-1"),
    ("tencent", "three", "7-9岁", "主题", "-1"),
    ("tencent", "ten", "10岁以上", "主题", "-1"),
    ("tencent", "all_year", "全龄向", "主题", "-1"),
    ("youku", "age", "全部年龄", "年龄", ""),
    ("youku", "show_label_type", "全部类型", "类型", ""),
    ("youku", "child_tags", "全部分类", "分类", ""),
    ("iqiyi", "category_20288", "年龄段", "年龄", ""),
    ("iqiyi", "category_28982", "课程类型", "课程", ""),
])
def test_compact_labels_and_all_option_preserve_filter_protocol(source, key, label, expected, sentinel):
    original = {key: {"label": label, "default": sentinel,
                      "options": [{"label": label, "value": sentinel}, {"label": "已完结", "value": "0"}]}}
    before = deepcopy(original)
    result = present_filters(source, original)[key]
    assert result["label"] == expected and len(result["label"]) == 2
    assert result["options"][0] == {"label": "全部", "value": sentinel}
    assert result["options"][1] == original[key]["options"][1]
    assert result["default"] == sentinel
    assert original == before


def test_default_sort_keeps_its_actual_meaning():
    value = {"sort": {"label": "排序", "default": "", "options": [{"label": "综合排序", "value": ""}]}}
    assert present_filters("youku", value)["sort"]["options"] == [{"label": "综合", "value": ""}]
