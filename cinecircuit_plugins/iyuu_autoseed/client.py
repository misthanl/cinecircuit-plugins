"""IYUU reseed protocol adapted from MoviePilot's public IyuuHelper (GPL-3.0)."""

from hashlib import sha1
import json
from time import time
from app.modules.plugins.runtime_services import http_client


class IyuuClient:
    base = "https://2025.iyuu.cn"
    version = "8.2.0"

    def __init__(self, token):
        if not str(token).strip():
            raise ValueError("请配置 IYUU Token")
        self.token = str(token)
        self.sid_sha1 = ""
        self.sites = []

    async def request(self, path, payload=None):
        async with http_client(
            use_application_proxy=True, timeout=30, follow_redirects=False
        ) as client:
            response = await client.request(
                "POST" if payload is not None else "GET",
                self.base + path,
                headers={"token": self.token},
                **({"json": payload} if payload is not None else {}),
            )
            response.raise_for_status()
            try:
                result = response.json()
            except ValueError:
                raise ValueError("IYUU 返回无效 JSON，请稍后重试") from None
        if not isinstance(result, dict):
            raise ValueError("IYUU 返回数据格式无效")
        if result.get("code") != 0:
            message = str(result.get("msg") or "未知错误").replace(self.token, "[redacted]")
            raise ValueError("IYUU 请求失败：" + message[:180])
        return result.get("data") or {}

    async def initialize(self):
        data = await self.request("/reseed/sites/index")
        self.sites = data.get("sites", [])
        await self.report_sites()

    async def report_sites(self):
        data = await self.request(
            "/reseed/sites/reportExisting", {"sid_list": [s["id"] for s in self.sites]}
        )
        self.sid_sha1 = data.get("sid_sha1") or ""
        if not self.sid_sha1:
            raise ValueError("IYUU 未返回有效站点列表签名")

    async def query(self, hashes):
        encoded = json.dumps(sorted(set(hashes)), separators=(",", ":"), ensure_ascii=False)
        for attempt in range(2):
            try:
                return await self.request(
                    "/reseed/index/index",
                    {
                        "hash": encoded,
                        "sha1": sha1(encoded.encode()).hexdigest(),
                        "sid_sha1": self.sid_sha1,
                        "timestamp": int(time()),
                        "version": self.version,
                    },
                )
            except ValueError as error:
                if attempt or "站点哈希值" not in str(error):
                    raise
                await self.report_sites()

    def site(self, sid):
        return next((site for site in self.sites if str(site.get("id")) == str(sid)), None)
