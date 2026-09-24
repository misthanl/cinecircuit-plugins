"""Category hot-search boards from Youku's public search page."""

import hashlib
import json
import time

import httpx

from .requests import BoardRequestError
from .settings import CATEGORIES

APP_KEY = "23774304"  # Public PC website application identifier.
API = "mtop.youku.soku.yksearch"


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def request_data():
    return compact_json({
        "pg": "1", "pz": "12", "searchFrom": "home", "utdId": "homepage_empty_cna",
        "ykPid": "", "sdkver": 314, "pcKuFlixMode": 1,
        "appScene": "default_page", "appCaller": "youku-search-sdk",
    })


async def fetch(client, read_json):
    data = request_data()
    for handshake in range(2):
        token = next((cookie.value.split("_")[0] for cookie in client.cookies.jar
                      if cookie.name == "_m_h5_tk" and cookie.domain.endswith("youku.com")), "")
        stamp = str(int(time.time() * 1000))
        signature = hashlib.md5(
            f"{token}&{stamp}&{APP_KEY}&{data}".encode(), usedforsecurity=False,
        ).hexdigest()
        # Browser user agents receive only the aggregate tab; the API client
        # response includes the search page's category tabDataMap.
        payload = await read_json(client, f"https://acs.youku.com/h5/{API}/2.0/",
                                  headers={"User-Agent": f"python-httpx/{httpx.__version__}"}, params={
            "api": API, "appKey": APP_KEY, "v": "2.0", "type": "originaljson",
            "dataType": "json", "data": data, "t": stamp, "sign": signature,
        })
        codes = " ".join(payload.get("ret", []))
        if "SUCCESS::" in codes:
            return boards(payload)
        if handshake or not any(code in codes for code in (
            "TOKEN_EMPTY", "TOKEN_EXOIRED", "TOKEN_EXPIRED", "TOKEN_ILLEGAL",
        )):
            raise BoardRequestError("优酷热搜榜请求未获成功响应")
    raise BoardRequestError("优酷匿名会话初始化失败")


def nodes(root):
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(reversed(node.get("nodes", [])))


def boards(payload):
    result = {}
    for node in nodes(payload.get("data", {})):
        tabs = node.get("data", {}).get("tabDataMap", {})
        for label, root in tabs.items():
            if label not in CATEGORIES.values():
                continue
            entries = []
            for item in nodes(root):
                info = item.get("data", {})
                if not info.get("rank") or not info.get("showId"):
                    continue
                # keyword retains full season names when the display title is abbreviated.
                entries.append({"title": info.get("keyword") or info.get("title", ""),
                                "platform_id": str(info["showId"])})
                if len(entries) == 10:
                    break
            result[label] = entries
    return result
