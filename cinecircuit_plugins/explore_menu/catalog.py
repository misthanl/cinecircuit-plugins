"""Official channel catalog adapters. No search rankings or metadata substitution."""

import json
from typing import Any
import re
from datetime import date
from urllib.parse import urlencode

from .transport import read_json
from .images import iqiyi_poster
from .settings import CATEGORIES

TENCENT_CHANNELS = {"movie": "100173", "tv": "100113", "anime": "100119", "kids": "100150", "variety": "100109", "documentary": "100105"}
IQIYI_CHANNELS = {"movie": 1, "tv": 2, "anime": 4, "kids": 15, "variety": 6, "documentary": 3}
MANGO_CHANNELS = {"movie": 3, "tv": 2, "anime": 50, "kids": 10, "variety": 1, "documentary": 51}
KIDS_THEMES = {"-1": "all", "1": "one", "2": "two", "3": "three", "4": "ten", "7": "all_year"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def definition(label, options, default=""):
    return {"label": label, "default": default, "options": options}


def option(label, value):
    return {"label": str(label), "value": str(value or "")}


def card(platform_id, title, poster, *, year="", overview="", url="", rating=0):
    return {
        "platform_id": str(platform_id), "title": title, "poster": https(poster),
        "year": str(year or "")[:4], "overview": overview or "",
        "platform_url": https(url), "rating": float(rating or 0),
    }


def https(url):
    return "https:" + url if str(url).startswith("//") else str(url).replace("http://", "https://", 1)


def result(items, filters, more, cursor=None):
    return {"items": items, "filters": filters, "has_more": bool(more), "cursor": cursor}


def walk_cards(value):
    if isinstance(value, dict):
        if "type" in value and "params" in value:
            yield value
        for child in value.values():
            yield from walk_cards(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_cards(child)


async def tencent(client, kind, page, filters, cursor=None):
    if kind == "kids":
        theme = KIDS_THEMES.get(filters.get("iyear") or "-1")
        filters = {key: value for key, value in filters.items() if key not in KIDS_THEMES.values() or key == theme}
    body = {"page_params": {
        "channel_id": TENCENT_CHANNELS[kind],
        "filter_params": urlencode(filters), "page_id": "channel_list", "page_type": "operation",
    }}
    if page > 1:
        if not cursor:
            raise ValueError("分页会话已过期，请重新加载第一页")
        body["page_context"] = cursor
    data = await read_json(
        client,
        "https://pbaccess.video.qq.com/trpc.multi_vector_layout.mvl_controller.MVLPageHTTPService/getMVLPage?vversion_platform=2",
        method="POST", json=body,
        headers={**HEADERS, "Referer": "https://v.qq.com/", "Origin": "https://v.qq.com"},
    )
    data = data["data"]
    choices: dict[str, Any] = {}
    rows = []
    for entry in walk_cards(data.get("modules", {})):
        p = entry["params"]
        if entry["type"] == "searchlist_filter_card":
            key = p.get("filter_key")
            if key:
                group = choices.setdefault(key, definition(p.get("index_name", key), []))
                group["options"].append(option(p.get("option_name"), p.get("option_value")))
                if p.get("is_default_val") == "1":
                    group["default"] = str(p.get("option_value", ""))
        if entry["type"] == "searchlist_poster_card" and p.get("cid"):
            marks = json.loads(p.get("latest_mark_label") or "{}")
            rating = marks.get("4", {}).get("info", {}).get("text", "")
            rows.append(card(
                p["cid"], p.get("title", ""), p.get("new_pic_vt") or p.get("new_pic_hz", ""),
                year=p.get("year"), overview=p.get("sub_title"),
                url="https://v.qq.com/x/cover/" + p["cid"] + ".html",
                rating=rating if re.fullmatch(r"\d+(\.\d+)?", rating) else 0,
            ))
    return result(rows, choices, data.get("has_next_page"), data.get("page_context"))


async def youku(client, kind, page, filters, cursor=None):
    params = {"type": CATEGORIES[kind], **filters}
    query = {"params": json.dumps(params, ensure_ascii=False, separators=(",", ":")),
             "optionRefresh": 1, "pageNo": page}
    if page > 1:
        if not cursor:
            raise ValueError("分页会话已过期，请重新加载第一页")
        query.pop("optionRefresh")
        query["session"] = json.dumps(cursor, ensure_ascii=False, separators=(",", ":"))
    data = await read_json(
        client, "https://www.youku.com/category/data",
        params=query,
        headers={**HEADERS, "Referer": "https://www.youku.com/channel/webmovie/list"},
    )
    if not data.get("success"):
        raise ValueError("优酷片库请求失败")
    data = data["data"]["filterData"]
    choices = {}
    labels = {"main_area": "地区", "tags": "类型", "source": "规格", "year": "年份",
              "pay_type": "资费", "sort": "排序", "movie_theatre": "影厅", "brand": "出品", "tag_label_name": "推荐"}
    for group in data.get("filter", {}).get("filterData", []):
        entries = group.get("subFilter", [])
        if not entries:
            continue
        key = entries[0].get("filterType")
        if key == "type" or not key:
            continue
        choices[key] = definition(labels.get(key, entries[0].get("title", key)), [
            option(p.get("title", ""), p.get("value")) for p in entries
        ])
    rows = []
    for row in data.get("listData", []):
        url = row.get("videoLink", "")
        identity = re.search(r"(?:id_|[?&]s=)([A-Za-z0-9=]+)", url)
        if identity:
            rows.append(card(identity[1], row.get("title", ""), row.get("img", ""),
                             overview=row.get("subTitle"), url=url))
    return result(rows, choices, data.get("hasMore"), data.get("session"))


async def iqiyi_config(client, kind):
    return await read_json(client, "https://pcw-api.iqiyi.com/search/category/categoryinfo",
                           params={"channel_id": IQIYI_CHANNELS[kind], "brand": "IQIYI", "locale": "zh"},
                           headers={**HEADERS, "Referer": "https://list.iqiyi.com/"})


async def iqiyi(client, kind, page, filters, cursor=None, *, config=None):
    channel = IQIYI_CHANNELS[kind]
    headers = {**HEADERS, "Referer": "https://list.iqiyi.com/"}
    if config is None:
        config = await iqiyi_config(client, kind)
    choices = {}
    for group in config["data"]:
        key = "category_" + str(group["id"])
        choices[key] = definition(group["name"], [option("全部", "")] + [
            option(p["name"], p["id"]) for p in group.get("child", [])
        ])
    choices["sort"] = definition("排序", [option("综合排序", "24"), option("热播榜", "11"),
                                               option("好评榜", "8"), option("新上线", "4")], "24")
    choices["year"] = year_choices()
    choices["pay"] = definition("资费", [option("全部", ""), option("免费", "0"), option("付费", "1")])
    if kind in {"tv", "anime"}:
        choices["finished"] = definition("状态", [option("全部", ""), option("已完结", "1"), option("更新中", "0")])
    params = {"channel_id": channel, "ret_num": 30, "page_id": page,
              "mode": filters.get("sort") or "24", "data_type": 1}
    categories = [value + ";must" for key, value in filters.items() if key.startswith("category_") and value]
    if categories:
        params["three_category_id"] = ",".join(categories)
    for key, target in [("year", "market_release_date_level"), ("pay", "is_purchase"), ("finished", "is_album_finished")]:
        if filters.get(key, "") != "":
            params[target] = filters[key]
    if cursor:
        params["session"] = cursor
    payload = await read_json(client, "https://pcw-api.iqiyi.com/search/recommend/list", params=params, headers=headers)
    if payload.get("code") != "A00000":
        raise ValueError("爱奇艺片库请求失败")
    data = payload["data"]
    rows = [card(p.get("albumId") or p.get("tvId"), p.get("albumName") or p.get("name", ""),
                 iqiyi_poster(p.get("albumImageUrl") or p.get("imageUrl", "")), year=p.get("period"),
                 overview=p.get("description"), url=p.get("playUrl", ""), rating=p.get("score"))
            for p in data.get("list", [])]
    return result(rows, choices, data.get("has_next"), data.get("session"))


def year_choices():
    return definition("年份", [option("全部", "")]
                      + [option(str(y), str(y)) for y in range(date.today().year, 2016, -1)]
                      + [option("2016–2011", "2011-2016"), option("2010–2000", "2000-2010"),
                         option("90 年代", "1990-1999"), option("80 年代", "1980-1989"),
                         option("更早", "1964-1979")])


async def mango_config(client, kind):
    return await read_json(client, "https://pianku.api.mgtv.com/rider/config/channel/v1",
                           params={"channelId": MANGO_CHANNELS[kind], "platform": "pcweb"},
                           headers={**HEADERS, "Referer": "https://list.mgtv.com/"})


async def mango(client, kind, page, filters, cursor=None, *, config=None):
    channel = MANGO_CHANNELS[kind]
    headers = {**HEADERS, "Referer": "https://list.mgtv.com/"}
    if config is None:
        config = await mango_config(client, kind)
    choices = {}
    for group in config["data"]["listItems"]:
        choices[group["eName"]] = definition(group["typeName"], [
            option(p["tagName"], p["tagId"]) for p in group.get("items", [])
        ], next((p["tagId"] for p in group.get("items", []) if p.get("picked")), ""))
    payload = await read_json(client, "https://pianku.api.mgtv.com/rider/list/pcweb/v3",
                              params={"platform": "pcweb", "channelId": channel, "pn": page,
                                      "pc": 30, "hudong": 1, "_support": "10000000", **filters}, headers=headers)
    if payload.get("code") != 200:
        raise ValueError("芒果片库请求失败")
    data = payload["data"]
    rows = [card(p["clipId"], p.get("title", ""), p.get("img") or p.get("imgV", ""),
                 year=p.get("year"), overview=p.get("story"),
                 url=p.get("playUrl") or f"https://www.mgtv.com/b/{p['clipId']}/{p.get('playPartId', '')}.html",
                 rating=p.get("zhihuScore")) for p in data.get("hitDocs", [])]
    return result(rows, choices, data.get("hasMore"))
