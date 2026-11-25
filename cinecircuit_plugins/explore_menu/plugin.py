"""Platform channel catalogs presented through the host's exploration outlet."""

from __future__ import annotations

import asyncio
import re
import hashlib
import json
import time
import httpx

from app.modules.plugins.contracts import (
    PluginApiRequest,
    PluginBase,
    PluginContext,
    PluginManifest,
)
from app.modules.plugins.permissions import PluginPermission
from app.modules.plugins.runtime_services import http_client

from . import catalog
from .identity import canonical as canonical, resolve
from .filter_labels import present_filters
from .settings import CATEGORIES, PLATFORMS
from .titles import annotate


class ExploreMenuPlugin(PluginBase):
    api_action_timeouts = {"explore": 58}

    manifest = PluginManifest(
        id="explore-menu",
        name="探索菜单扩展",
        version="1.0.0",
        api_version=2,
        entrypoint="plugin:ExploreMenuPlugin",
        description="在探索中浏览腾讯视频、优酷、爱奇艺和芒果 TV 频道片库，各平台独立控制显示。",
        icon="mdi-compass-outline",
        permissions=(PluginPermission.MEDIA_DISCOVER,),
        capabilities=("explore_source", "configuration_only"),
        config_schema={
            "description_display": "hidden",
            "layout": {"columns": 2, "row_gap": 14, "column_gap": 16},
            "fields": [
                field
                for index, (key, label) in enumerate(PLATFORMS.items(), 1)
                for field in [
                    {
                        "key": key + "_visible",
                        "input_type": "switch",
                        "label": label,
                        "default": True,
                    },
                    {
                        "key": key + "_order",
                        "input_type": "number",
                        "label": label + "顺序",
                        "default": index,
                        "validation": {"min": 0, "max": 999},
                    },
                ]
            ],
        },
        explore_sources=tuple(
            {
                "key": key,
                "label": label,
                "visibility_config_key": key + "_visible",
                "order_config_key": key + "_order",
                "catalog_types": [{"value": value, "label": title} for value, title in CATEGORIES.items()],
            }
            for key, label in PLATFORMS.items()
        ),
    )

    async def run(self, context: PluginContext) -> dict:
        return {"status": "success", "message": "请在探索页面选择平台浏览，无需定时执行"}

    async def handle_api(self, request: PluginApiRequest, context: PluginContext) -> dict:
        if request.action != "explore" or request.method != "POST":
            raise KeyError("不支持的探索操作")
        source = str(request.payload.get("source") or "")
        if source not in PLATFORMS or context.config.get(source + "_visible", True) is not True:
            raise ValueError("该平台已隐藏或不存在")
        kind = str(request.payload.get("media_type") or "movie")
        if kind not in CATEGORIES:
            raise ValueError("请选择有效的片库频道")
        if request.payload.get("operation") == "resolve":
            return await self._resolve(request, context, source, kind)
        page = max(1, min(500, int(request.payload.get("page") or 1)))
        filters = request.payload.get("filters") or {}
        if not isinstance(filters, dict) or len(filters) > 24:
            raise ValueError("筛选条件无效")
        if any(not re.fullmatch(r"[A-Za-z_0-9]{1,64}", str(k)) or not isinstance(v, str) or len(v) > 128
               for k, v in filters.items()):
            raise ValueError("筛选条件无效")
        try:
            async with asyncio.timeout(26):
                data = await self._catalog(context, source, kind, page, filters)
            data = {**data, "filters": present_filters(source, data["filters"])}
            rows = []
            for original in data["items"]:
                row = annotate(original)
                identity = f"plugin:{self.manifest.id}:{source}"
                row.update(id=identity + ":" + row["platform_id"], source_key=identity,
                           source_id=row["platform_id"], catalog_source=identity,
                           source_label=PLATFORMS[source],
                           media_identity={"source": identity, "id": row["platform_id"]},
                           media_type="movie" if kind == "movie" else "tv", catalog_type=kind,
                           type_label=CATEGORIES[kind], identity_pending=True)
                rows.append(row)
            return response(rows, page, "频道片库，筛选和排序由平台处理", data=data)
        except (ValueError, RuntimeError, TimeoutError, OSError, httpx.HTTPError, TypeError, KeyError):
            return response([], page, "该平台片库暂不可用，请稍后重试", mode="error")

    async def _resolve(self, request, context, source, kind):
        item = request.payload.get("item")
        if not isinstance(item, dict) or item.get("source_key") != f"plugin:{self.manifest.id}:{source}":
            raise ValueError("媒体来源无效")
        try:
            async with asyncio.timeout(54):
                matched = await resolve(context, item, kind)
        except TimeoutError:
            matched = None
        if not matched:
            return response([], 1, "未能唯一匹配 TMDB 作品，请在媒体搜索中确认后订阅", mode="unmatched")
        # Retain the platform presentation, but only use a confirmed canonical identity for actions.
        resolved = {key: value for key, value in {**item, **matched}.items()
                    if not key.startswith(("include_", "_include_"))}
        for key in ("poster", "overview", "rating"):
            if item.get(key):
                resolved[key] = item[key]
        resolved["catalog_title"] = item.get("catalog_title") or item.get("title")
        resolved["catalog_year"] = item.get("catalog_year") or item.get("year")
        if matched.get("season_identity"):
            resolved["season_year"] = matched["season_identity"].get("year") or ""
        if resolved.get("requested_season") and resolved.get("media_type") == "tv":
            resolved["series_title"] = matched.get("title") or resolved["title"]
        if matched.get("season_identity") and not matched["season_identity"].get("year"):
            resolved["identity_warnings"] = ["目标季缺少完整播出年份，已按唯一作品及真实季集资料选中，请确认。"]
        resolved["identity_pending"] = False
        resolved["media_identity"] = {"source": matched["source_key"], "id": matched["source_id"]}
        return response([resolved], 1, "已匹配 TMDB 媒体身份")

    async def _catalog(self, context, source, kind, page, filters):
        signature = hashlib.sha256(json.dumps([source, kind, filters], sort_keys=True).encode()).hexdigest()
        cache_key = "channel-catalog:v2:" + signature + ":" + str(page)
        cached = context.state.get(cache_key, {})
        if cached and time.time() - cached.get("time", 0) < 600:
            return cached["data"]
        previous = context.state.get("channel-catalog:v2:" + signature + ":" + str(page - 1), {})
        cursor = previous.get("data", {}).get("cursor") if time.time() - previous.get("time", 0) < 600 else None
        async with http_client(timeout=12, follow_redirects=True) as client:
            options = await self._channel_options(context, client, source, kind)
            data = await getattr(catalog, source)(client, kind, page, filters, cursor, **options)
        if not data["filters"] and previous:
            data["filters"] = previous.get("data", {}).get("filters", {})
        context.state.set(cache_key, {"time": time.time(), "data": data})
        return data

    async def _channel_options(self, context, client, source, kind):
        if source not in {"iqiyi", "mango"}:
            return {}
        key = "channel-options:v1:" + source + ":" + kind
        cached = context.state.get(key, {})
        if cached and time.time() - cached.get("time", 0) < 3600:
            return {"config": cached["data"]}
        data = await getattr(catalog, source + "_config")(client, kind)
        context.state.set(key, {"time": time.time(), "data": data})
        return {"config": data}


def response(items, page, message, *, mode="live", data=None):
    data = data or {}
    return {
        "items": items, "page": page, "count": len(items), "total": len(items),
        "has_more": bool(data.get("has_more")),
        "options": {"catalog_filters": data["filters"]} if "filters" in data else {},
        "source_status": {"mode": mode, "message": message},
    }
