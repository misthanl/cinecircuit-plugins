from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, unquote, urljoin

from app.core.http_client import outbound_async_client

from app.modules.plugins.contracts import (
    PluginApiRequest,
    PluginBase,
    PluginContext,
    PluginManifest,
)
from app.modules.plugins.permissions import PluginPermission


class SubtitleWorkspacePlugin(PluginBase):
    """Manual sidecar subtitle workspace backed by successful organizer history."""

    manifest = PluginManifest(
        entrypoint="plugin:SubtitleWorkspacePlugin",
        id="subtitle-manager",
        name="字幕管理助手",
        version="1.0.0",
        description="在线搜索、手动上传、自动匹配、规范改名与字幕管理工作台。",
        icon="mdi-subtitles-outline",
        permissions=(
            PluginPermission.ORGANIZER_HISTORY,
            PluginPermission.MEDIA_FILES_READ,
            PluginPermission.MEDIA_FILES_WRITE_SIDECAR,
            PluginPermission.NOTIFICATION_SEND,
        ),
        capabilities=("plugin_page", "subtitle_sidecar", "online_subtitle", "transfer_assistant"),
        frontend_module="frontend.js",
        navigation={
            "title": "字幕管理",
            "icon": "mdi-subtitles-outline",
            "section": "tools",
            "order": 65,
        },
        config_schema={
            "sections": [
                {
                    "key": "general",
                    "title": "基础设置",
                    "description": "控制字幕页面和文件写入行为。",
                },
                {
                    "key": "automatic",
                    "title": "自动匹配",
                    "description": "整理完成后按语言与格式优先级寻找字幕。",
                },
                {
                    "key": "online",
                    "title": "在线字幕源",
                    "description": "配置 SubHD、字幕库、ASSRT 和 OpenSubtitles。",
                },
                {
                    "key": "timeline",
                    "title": "智能调轴",
                    "description": "设置可接受的时间偏移范围和语音检测方式。",
                },
            ],
            "fields": [
                {
                    "key": "enabled",
                    "input_type": "switch",
                    "label": "启用字幕插件",
                    "default": True,
                    "section": "general",
                },
                {
                    "key": "notification_enabled",
                    "input_type": "switch",
                    "label": "发送通知",
                    "default": False,
                    "description": "开启后发送字幕检查和文件操作结果。",
                    "icon": "mdi-bell-outline",
                    "section": "general",
                },
                {
                    "key": "show_sidebar_nav",
                    "input_type": "switch",
                    "label": "显示侧边栏入口",
                    "default": True,
                    "section": "general",
                },
                {
                    "key": "default_language",
                    "input_type": "select",
                    "label": "默认字幕语言",
                    "default": "zh-CN",
                    "icon": "mdi-translate",
                    "description": "用于生成媒体同名字幕文件的语言标记。",
                    "section": "general",
                    "options": [
                        {"value": "zh-CN", "label": "简体中文（zh-CN）"},
                        {"value": "zh-TW", "label": "繁体中文（zh-TW）"},
                        {"value": "zh", "label": "中文（zh）"},
                        {"value": "en", "label": "英语（en）"},
                        {"value": "ja", "label": "日语（ja）"},
                        {"value": "ko", "label": "韩语（ko）"},
                    ],
                },
                {
                    "key": "overwrite_existing",
                    "input_type": "switch",
                    "label": "允许覆盖同名字幕",
                    "default": False,
                    "icon": "mdi-file-replace-outline",
                    "description": "默认关闭，避免意外覆盖已经校对的字幕。",
                    "section": "general",
                },
                {
                    "key": "traditional_to_simplified",
                    "input_type": "switch",
                    "label": "繁体字幕转简体",
                    "default": False,
                    "section": "automatic",
                },
                {
                    "key": "auto_search_on_transfer",
                    "input_type": "switch",
                    "label": "整理完成后自动搜索",
                    "default": False,
                    "section": "automatic",
                },
                {
                    "key": "auto_skip_chinese_media_on_transfer",
                    "input_type": "switch",
                    "label": "自动跳过中文媒体",
                    "default": True,
                    "section": "automatic",
                },
                {
                    "key": "auto_transfer_subtitle_strategy",
                    "input_type": "select",
                    "label": "自动字幕策略",
                    "default": "online_then_ai_source",
                    "section": "automatic",
                    "options": [
                        {"value": "online_then_ai_source", "label": "在线优先，失败后 AI"},
                        {"value": "online_source_only", "label": "仅在线字幕"},
                        {"value": "ai_source_only", "label": "仅 AI 字幕"},
                    ],
                },
                {
                    "key": "auto_multi_subtitle_mode",
                    "input_type": "select",
                    "label": "多字幕处理",
                    "default": "best",
                    "section": "automatic",
                    "options": [
                        {"value": "best", "label": "仅最佳字幕"},
                        {"value": "chinese_all", "label": "全部中文字幕"},
                        {"value": "all", "label": "全部字幕"},
                    ],
                },
                {
                    "key": "auto_subtitle_language_priority",
                    "input_type": "textarea",
                    "label": "语言优先级",
                    "default": ["zh-Hans", "zh-CN", "zh-Hant", "zh", "en"],
                    "visible": False,
                },
                {
                    "key": "auto_subtitle_format_priority",
                    "input_type": "textarea",
                    "label": "格式优先级",
                    "default": ["ass", "ssa", "srt"],
                    "visible": False,
                },
                {
                    "key": "online_providers",
                    "input_type": "select",
                    "multiple": True,
                    "label": "启用字幕源",
                    "default": ["subhd", "zimuku"],
                    "section": "online",
                    "options": [
                        {"value": "subhd", "label": "SubHD"},
                        {"value": "zimuku", "label": "字幕库"},
                        {"value": "assrt", "label": "ASSRT"},
                        {"value": "opensubtitles", "label": "OpenSubtitles"},
                    ],
                },
                {
                    "key": "online_use_proxy",
                    "input_type": "switch",
                    "label": "在线搜索使用代理",
                    "default": False,
                    "section": "online",
                },
                {
                    "key": "subhd_url",
                    "input_type": "url",
                    "label": "SubHD 地址",
                    "default": "https://subhd.tv",
                    "section": "online",
                },
                {
                    "key": "zimuku_url",
                    "input_type": "url",
                    "label": "字幕库地址",
                    "default": "https://zmk.pw",
                    "section": "online",
                },
                {
                    "key": "assrt_api_key",
                    "input_type": "password",
                    "label": "ASSRT API Key",
                    "default": "",
                    "secret": True,
                    "encrypted": True,
                    "section": "online",
                },
                {
                    "key": "assrt_api_url",
                    "input_type": "url",
                    "label": "ASSRT API 地址",
                    "default": "https://api.assrt.net/v1",
                    "section": "online",
                },
                {
                    "key": "opensubtitles_api_key",
                    "input_type": "password",
                    "label": "OpenSubtitles API Key",
                    "default": "",
                    "secret": True,
                    "encrypted": True,
                    "section": "online",
                },
                {
                    "key": "opensubtitles_api_url",
                    "input_type": "url",
                    "label": "OpenSubtitles API 地址",
                    "default": "https://api.opensubtitles.com/api/v1",
                    "section": "online",
                },
                {
                    "key": "opensubtitles_username",
                    "input_type": "text",
                    "label": "OpenSubtitles 用户名",
                    "default": "",
                    "section": "online",
                },
                {
                    "key": "opensubtitles_password",
                    "input_type": "password",
                    "label": "OpenSubtitles 密码",
                    "default": "",
                    "secret": True,
                    "encrypted": True,
                    "section": "online",
                },
                {
                    "key": "ai_link_enabled",
                    "input_type": "switch",
                    "label": "启用 AI 字幕联动",
                    "default": True,
                    "section": "automatic",
                },
                {
                    "key": "timeline_max_offset_seconds",
                    "input_type": "number",
                    "label": "最大调轴偏移（秒）",
                    "default": 120,
                    "validation": {"minimum": 1, "maximum": 300},
                    "section": "timeline",
                },
                {
                    "key": "timeline_min_offset_seconds",
                    "input_type": "number",
                    "label": "最小调轴偏移（秒）",
                    "default": 0.2,
                    "validation": {"minimum": 0.01, "maximum": 1},
                    "section": "timeline",
                },
                {
                    "key": "timeline_vad_mode",
                    "input_type": "select",
                    "label": "语音检测方式",
                    "default": "webrtc",
                    "section": "timeline",
                    "options": [
                        {"value": "webrtc", "label": "WebRTC VAD"},
                        {"value": "rms", "label": "RMS 音量"},
                    ],
                },
                {
                    "key": "timeline_allow_risky_offset",
                    "input_type": "switch",
                    "label": "允许低可信偏移",
                    "default": False,
                    "section": "timeline",
                },
            ],
        },
    )

    async def run(self, context: PluginContext) -> dict[str, Any]:
        catalog = await self._catalog(context, query="", limit=200)
        subtitle_count = sum(len(item.get("subtitles") or []) for item in catalog["items"])
        context.logger.info(
            "字幕目录检查完成：媒体 %s，外挂字幕 %s",
            len(catalog["items"]),
            subtitle_count,
        )
        if bool(context.config.get("notification_enabled")):
            await context.notifications.send(
                "字幕目录检查完成",
                f"检查媒体 {len(catalog['items'])} 个，发现外挂字幕 {subtitle_count} 个。",
                notification_type="plugin",
            )
        return {"media_count": len(catalog["items"]), "subtitle_count": subtitle_count}

    async def handle_api(
        self,
        request: PluginApiRequest,
        context: PluginContext,
    ) -> dict[str, Any]:
        if request.action == "catalog" and request.method == "GET":
            return await self._catalog(
                context,
                query=request.query.get("query", ""),
                limit=min(200, max(1, int(request.query.get("limit", "80") or 80))),
            )
        if request.action == "inventory" and request.method == "GET":
            return await context.media_files.subtitles(request.query.get("media_path", ""))
        if request.action == "upload" and request.method == "POST":
            return await self._upload_subtitle(request, context)
        if request.action == "delete" and request.method == "POST":
            result = await context.media_files.delete_subtitle(
                str(request.payload.get("media_path") or ""),
                str(request.payload.get("subtitle_name") or ""),
            )
            await self._notify_file_action(context, "字幕已删除", result)
            return result
        if request.action == "adjust" and request.method == "POST":
            return await self._adjust_subtitle(request, context)
        if request.action == "online" and request.method == "GET":
            keyword = request.query.get("query", "").strip()
            if not keyword:
                raise ValueError("请输入字幕搜索词")
            return {"items": await self._online_search(context.config, keyword)}
        raise KeyError("字幕插件页面操作不存在")

    @staticmethod
    async def _upload_subtitle(request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        media_path = request.query.get("media_path", "")
        if not await context.organizer.has_successful_destination(media_path):
            raise ValueError("只能为成功整理记录中的媒体上传字幕")
        filename = unquote(str(request.filename or "")).strip()
        extension = Path(filename).suffix.casefold().lstrip(".")
        language = request.query.get("language") or str(
            context.config.get("default_language") or "zh-CN"
        )
        overwrite = request.query.get("overwrite", "").casefold() in {"1", "true", "yes"}
        if "overwrite" not in request.query:
            overwrite = bool(context.config.get("overwrite_existing", False))
        result = await context.media_files.write_subtitle(
            media_path,
            request.content,
            extension=extension,
            language=language,
            overwrite=overwrite,
        )
        await SubtitleWorkspacePlugin._notify_file_action(context, "字幕已保存", result)
        return result

    @staticmethod
    async def _adjust_subtitle(request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        offset_seconds = float(request.payload.get("offset_seconds") or 0)
        configured_limit = float(context.config.get("timeline_max_offset_seconds") or 120)
        if abs(offset_seconds) > min(300, max(1, configured_limit)):
            raise ValueError(f"字幕时间偏移不能超过当前设置的 {configured_limit:g} 秒")
        result = await context.media_files.adjust_subtitle(
            str(request.payload.get("media_path") or ""),
            str(request.payload.get("subtitle_name") or ""),
            offset_seconds=offset_seconds,
        )
        await SubtitleWorkspacePlugin._notify_file_action(context, "字幕调轴完成", result)
        return result

    @staticmethod
    async def _notify_file_action(
        context: PluginContext,
        title: str,
        result: dict[str, Any],
    ) -> None:
        config = getattr(context, "config", {})
        if not isinstance(config, dict) or not bool(config.get("notification_enabled")):
            return
        target = str(result.get("subtitle_path") or result.get("subtitle_name") or "")
        await context.notifications.send(
            title,
            target,
            notification_type="plugin",
        )

    async def _online_search(self, config: dict[str, Any], keyword: str) -> list[dict[str, Any]]:
        enabled = config.get("online_providers")
        providers = (
            [str(item) for item in enabled] if isinstance(enabled, list) else ["subhd", "zimuku"]
        )
        results: list[dict[str, Any]] = []
        async with outbound_async_client(None, timeout=20, follow_redirects=True) as client:
            for provider in providers:
                try:
                    if provider == "assrt" and config.get("assrt_api_key"):
                        results.extend(await self._assrt_subtitles(client, config, keyword))
                    elif provider == "opensubtitles" and config.get("opensubtitles_api_key"):
                        results.extend(await self._opensubtitles(client, config, keyword))
                    elif provider in {"subhd", "zimuku"}:
                        results.extend(
                            await self._html_provider_subtitles(client, config, keyword, provider)
                        )
                except Exception:
                    continue
        return results

    @staticmethod
    async def _assrt_subtitles(
        client: Any, config: dict[str, Any], keyword: str
    ) -> list[dict[str, Any]]:
        base = str(config.get("assrt_api_url") or "https://api.assrt.net/v1").rstrip("/")
        response = await client.get(
            f"{base}/sub/search",
            params={"q": keyword, "token": config["assrt_api_key"]},
        )
        response.raise_for_status()
        rows = (response.json().get("sub") or {}).get("subs") or []
        return [
            {
                "provider": "ASSRT",
                "title": str(row.get("native_name") or row.get("videoname") or keyword),
                "language": str(row.get("lang") or ""),
                "url": str(row.get("url") or ""),
            }
            for row in rows[:20]
        ]

    @staticmethod
    async def _opensubtitles(
        client: Any, config: dict[str, Any], keyword: str
    ) -> list[dict[str, Any]]:
        base = str(
            config.get("opensubtitles_api_url") or "https://api.opensubtitles.com/api/v1"
        ).rstrip("/")
        response = await client.get(
            f"{base}/subtitles",
            params={"query": keyword},
            headers={"Api-Key": str(config["opensubtitles_api_key"])},
        )
        response.raise_for_status()
        rows: list[dict[str, Any]] = []
        for item in list(response.json().get("data") or [])[:20]:
            attrs = item.get("attributes") or {}
            rows.append(
                {
                    "provider": "OpenSubtitles",
                    "title": str(
                        attrs.get("release")
                        or attrs.get("feature_details", {}).get("title")
                        or keyword
                    ),
                    "language": str(attrs.get("language") or ""),
                    "url": str(attrs.get("url") or ""),
                }
            )
        return rows

    @staticmethod
    async def _html_provider_subtitles(
        client: Any,
        config: dict[str, Any],
        keyword: str,
        provider: str,
    ) -> list[dict[str, Any]]:
        root = str(
            config.get(f"{provider}_url")
            or ("https://subhd.tv" if provider == "subhd" else "https://zmk.pw")
        ).rstrip("/")
        path = (
            f"/search/{quote_plus(keyword)}"
            if provider == "subhd"
            else f"/search?q={quote_plus(keyword)}"
        )
        response = await client.get(root + path)
        response.raise_for_status()
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(response.text, "html.parser")
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for anchor in soup.select("a[href]"):
            title = anchor.get_text(" ", strip=True)
            href = urljoin(root + "/", str(anchor.get("href") or ""))
            if len(title) < 2 or keyword.casefold() not in title.casefold() or href in seen:
                continue
            seen.add(href)
            rows.append(
                {
                    "provider": "SubHD" if provider == "subhd" else "字幕库",
                    "title": title,
                    "language": "",
                    "url": href,
                }
            )
            if len(seen) >= 20:
                break
        return rows

    async def _catalog(
        self,
        context: PluginContext,
        *,
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        history = await context.organizer.history(query=str(query or ""), limit=limit)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in list(history.get("items") or []):
            path = str(row.get("path") or "")
            if not path or path in seen:
                continue
            seen.add(path)
            try:
                inventory = await context.media_files.subtitles(path)
            except (FileNotFoundError, OSError, ValueError):
                continue
            items.append({**row, "subtitles": list(inventory.get("items") or [])})
        return {"items": items, "count": len(items)}


Plugin = SubtitleWorkspacePlugin
PLUGIN = SubtitleWorkspacePlugin
