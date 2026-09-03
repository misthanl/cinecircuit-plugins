from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.core.config import get_settings
from app.core.http_client import outbound_async_client
from app.modules.config.service import ConfigService
from app.modules.plugins.contracts import (
    PluginApiRequest,
    PluginBase,
    PluginContext,
    PluginEvent,
    PluginManifest,
)
from app.modules.plugins.permissions import PluginPermission
from .scrape_refresh import (
    REFRESH_EVENT,
    schedule_refresh,
)

if TYPE_CHECKING:
    from .renderer import CoverRenderOptions


class LibraryArtworkPlugin(PluginBase):
    FONT_FILENAME = "NotoSansCJKsc-Regular.otf"
    FONT_URL = (
        "https://raw.githubusercontent.com/notofonts/noto-cjk/"
        "f8d157532fbfaeda587e826d4cd5b21a49186f7c/"
        "Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"
    )
    FONT_SHA256 = "2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
    FONT_MAX_BYTES = 20 * 1024 * 1024

    manifest = PluginManifest(
        entrypoint="plugin:LibraryArtworkPlugin",
        id="emby-cover-generator",
        name="媒体库视觉封面",
        version="1.0.0",
        description="为媒体服务器媒体库生成静态或动态风格封面，支持媒体库选择、标题、字体、分辨率和历史清理。",
        icon="mdi-image-multiple-outline",
        permissions=(
            PluginPermission.MEDIA_SERVER_READ,
            PluginPermission.MEDIA_SERVER_WRITE_IMAGES,
        ),
        capabilities=(
            "plugin_page",
            "media_server_controller",
            "image_generator",
            "scheduled_task",
        ),
        schedule_seconds=24 * 60 * 60,
        events=("metadata.scrape.completed", REFRESH_EVENT),
        frontend_module="frontend.js",
        navigation={
            "title": "Emby 封面",
            "icon": "mdi-image-multiple-outline",
            "section": "tools",
            "order": 80,
        },
        config_schema={
            "sections": [
                {
                    "key": "run",
                    "title": "运行设置",
                    "description": "选择执行周期、媒体服务器和媒体库。",
                },
                {
                    "key": "style",
                    "title": "封面样式",
                    "description": "配置封面的基础样式、变体、字体与标题。",
                },
                {
                    "key": "animation",
                    "title": "动态封面",
                    "description": "设置动态封面的格式、帧率与尺寸。",
                },
                {
                    "key": "storage",
                    "title": "缓存与历史",
                    "description": "控制生成文件、字体缓存与历史保留。",
                },
            ],
            "fields": [
                {
                    "key": "enabled",
                    "input_type": "switch",
                    "label": "启用定时生成",
                    "default": False,
                    "section": "run",
                },
                {
                    "key": "cron",
                    "input_type": "cron",
                    "label": "执行周期",
                    "default": "",
                    "placeholder": "5位cron表达式，留空自动",
                    "section": "run",
                },
                {
                    "key": "transfer_monitor",
                    "input_type": "switch",
                    "label": "刮削完成后更新封面",
                    "default": False,
                    "section": "run",
                },
                {
                    "key": "delay",
                    "input_type": "number",
                    "label": "延迟执行（秒）",
                    "default": 60,
                    "validation": {"minimum": 0, "maximum": 3600},
                    "section": "run",
                },
                {
                    "key": "selected_servers",
                    "input_type": "textarea",
                    "label": "媒体服务器",
                    "default": [],
                    "visible": False,
                },
                {
                    "key": "include_libraries",
                    "input_type": "textarea",
                    "label": "媒体库",
                    "default": [],
                    "visible": False,
                },
                {
                    "key": "cover_style_base",
                    "input_type": "select",
                    "label": "基础样式",
                    "default": "multi",
                    "section": "style",
                    "options": [
                        {"value": "single", "label": "单图"},
                        {"value": "multi", "label": "多图"},
                        {"value": "poster", "label": "海报墙"},
                        {"value": "animated", "label": "动态封面"},
                    ],
                },
                {
                    "key": "cover_style_variant",
                    "input_type": "select",
                    "label": "样式变体",
                    "default": "1",
                    "section": "style",
                    "options": [
                        {"value": str(value), "label": f"样式 {value}"} for value in range(1, 5)
                    ],
                },
                {
                    "key": "sort_by",
                    "input_type": "select",
                    "label": "媒体排序",
                    "default": "DateCreated",
                    "section": "style",
                    "options": [
                        {"value": "DateCreated", "label": "入库时间"},
                        {"value": "PremiereDate", "label": "首映时间"},
                        {"value": "Random", "label": "随机"},
                    ],
                },
                {
                    "key": "use_primary",
                    "input_type": "switch",
                    "label": "优先使用海报图",
                    "default": False,
                    "section": "style",
                },
                {
                    "key": "show_item_count",
                    "input_type": "switch",
                    "label": "显示媒体数量角标",
                    "default": False,
                    "section": "style",
                },
                {
                    "key": "title_config",
                    "input_type": "textarea",
                    "label": "媒体库标题配置",
                    "default": "",
                    "description": "每行：媒体库名称=中文标题|英文标题",
                    "section": "style",
                },
                {
                    "key": "zh_font_preset",
                    "input_type": "text",
                    "label": "中文字体",
                    "default": "chaohei",
                    "section": "style",
                },
                {
                    "key": "en_font_preset",
                    "input_type": "text",
                    "label": "英文字体",
                    "default": "EmblemaOne",
                    "section": "style",
                },
                {
                    "key": "zh_font_size",
                    "input_type": "number",
                    "label": "中文字号",
                    "default": 170,
                    "validation": {"minimum": 20, "maximum": 400},
                    "section": "style",
                },
                {
                    "key": "en_font_size",
                    "input_type": "number",
                    "label": "英文字号",
                    "default": 75,
                    "validation": {"minimum": 12, "maximum": 240},
                    "section": "style",
                },
                {
                    "key": "resolution",
                    "input_type": "select",
                    "label": "输出分辨率",
                    "default": "480p",
                    "section": "style",
                    "options": [
                        {"value": "1080p", "label": "1920 × 1080"},
                        {"value": "720p", "label": "1280 × 720"},
                        {"value": "480p", "label": "854 × 480"},
                        {"value": "custom", "label": "自定义"},
                    ],
                },
                {
                    "key": "custom_width",
                    "input_type": "number",
                    "label": "自定义宽度",
                    "default": 1920,
                    "validation": {"minimum": 320, "maximum": 7680},
                    "section": "style",
                },
                {
                    "key": "custom_height",
                    "input_type": "number",
                    "label": "自定义高度",
                    "default": 1080,
                    "validation": {"minimum": 180, "maximum": 4320},
                    "section": "style",
                },
                {
                    "key": "animation_format",
                    "input_type": "select",
                    "label": "动态格式",
                    "default": "apng",
                    "section": "animation",
                    "options": [
                        {"value": "apng", "label": "APNG"},
                        {"value": "webp", "label": "WebP"},
                        {"value": "gif", "label": "GIF"},
                    ],
                },
                {
                    "key": "animation_duration",
                    "input_type": "number",
                    "label": "动画时长（秒）",
                    "default": 12,
                    "validation": {"minimum": 2, "maximum": 60},
                    "section": "animation",
                },
                {
                    "key": "animation_fps",
                    "input_type": "number",
                    "label": "动画帧率",
                    "default": 12,
                    "validation": {"minimum": 1, "maximum": 30},
                    "section": "animation",
                },
                {
                    "key": "animation_resolution",
                    "input_type": "select",
                    "label": "动画分辨率",
                    "default": "320x180",
                    "section": "animation",
                    "options": [
                        {"value": "320x180", "label": "320 × 180"},
                        {"value": "480x270", "label": "480 × 270"},
                        {"value": "640x360", "label": "640 × 360"},
                    ],
                },
                {
                    "key": "clean_images",
                    "input_type": "switch",
                    "label": "生成后清理图片缓存",
                    "default": False,
                    "section": "storage",
                },
                {
                    "key": "clean_fonts",
                    "input_type": "switch",
                    "label": "生成后清理字体缓存",
                    "default": False,
                    "section": "storage",
                },
                {
                    "key": "save_recent_covers",
                    "input_type": "switch",
                    "label": "保留最近生成封面",
                    "default": True,
                    "section": "storage",
                },
                {
                    "key": "covers_history_limit_per_library",
                    "input_type": "number",
                    "label": "每个媒体库保留数量",
                    "default": 10,
                    "validation": {"minimum": 1, "maximum": 100},
                    "section": "storage",
                },
                {
                    "key": "covers_page_history_limit",
                    "input_type": "number",
                    "label": "页面历史显示数量",
                    "default": 50,
                    "validation": {"minimum": 10, "maximum": 500},
                    "section": "storage",
                },
                {
                    "key": "server_id",
                    "input_type": "text",
                    "label": "服务器内部字段",
                    "default": "",
                    "visible": False,
                },
                {
                    "key": "library_ids",
                    "input_type": "textarea",
                    "label": "媒体库内部字段",
                    "default": [],
                    "visible": False,
                },
                {
                    "key": "style",
                    "input_type": "text",
                    "label": "渲染样式",
                    "default": "mosaic",
                    "visible": False,
                },
                {
                    "key": "image_sources",
                    "input_type": "select",
                    "label": "图片来源优先级",
                    "default": ["Backdrop", "Primary"],
                    "multiple": True,
                    "visible": False,
                    "options": [
                        {"value": "Backdrop", "label": "背景图"},
                        {"value": "Primary", "label": "主海报"},
                        {"value": "Thumb", "label": "缩略图"},
                    ],
                },
                {
                    "key": "max_libraries",
                    "input_type": "number",
                    "label": "单次处理媒体库上限",
                    "default": 10,
                    "validation": {"minimum": 1, "maximum": 50},
                    "description": "一次任务最多处理多少个媒体库",
                    "section": "run",
                },
                {
                    "key": "source_limit",
                    "input_type": "number",
                    "label": "每张封面最多使用图片",
                    "default": 8,
                    "validation": {"minimum": 1, "maximum": 12},
                    "description": "图片越多，拼图封面的内容越丰富",
                    "section": "style",
                },
                {
                    "key": "include_types",
                    "input_type": "textarea",
                    "label": "Emby 媒体类型",
                    "default": [],
                    "visible": False,
                },
                {
                    "key": "title_map",
                    "input_type": "textarea",
                    "label": "媒体库标题映射",
                    "default": {},
                    "visible": False,
                },
                {
                    "key": "show_count",
                    "input_type": "switch",
                    "label": "显示媒体数量",
                    "default": True,
                    "visible": False,
                },
                {
                    "key": "background_color",
                    "input_type": "text",
                    "label": "图片不足时的背景色",
                    "default": "",
                    "placeholder": "例如 #101828，留空则自动取色",
                    "section": "style",
                },
                {
                    "key": "blur_radius",
                    "input_type": "number",
                    "label": "背景模糊强度",
                    "default": 32,
                    "validation": {"minimum": 0, "maximum": 80},
                    "description": "数值越大，背景虚化越明显",
                    "section": "style",
                },
                {
                    "key": "jpeg_quality",
                    "input_type": "number",
                    "label": "JPEG 质量",
                    "default": 92,
                    "validation": {"minimum": 75, "maximum": 96},
                    "description": "质量越高，图片文件通常越大",
                    "section": "style",
                },
                {
                    "key": "skip_unchanged",
                    "input_type": "switch",
                    "label": "跳过未变化封面",
                    "default": True,
                    "description": "封面内容没有变化时不重复上传",
                    "section": "storage",
                },
                {
                    "key": "dry_run",
                    "input_type": "switch",
                    "label": "预览模式（不上传）",
                    "default": True,
                    "description": "只生成预览结果，不修改媒体服务器中的封面",
                    "section": "run",
                },
            ],
        },
    )

    COLLECTION_ITEM_TYPES = {
        "movies": ("Movie",),
        "tvshows": ("Series",),
        "boxsets": ("BoxSet",),
        "music": ("MusicAlbum",),
        "musicvideos": ("MusicVideo",),
        "homevideos": ("Video",),
        "playlists": ("Playlist",),
        "mixed": ("Movie", "Series", "BoxSet"),
    }
    COLLECTION_LABELS = {
        "movies": "MOVIES",
        "tvshows": "TV SERIES",
        "boxsets": "COLLECTIONS",
        "music": "MUSIC",
        "musicvideos": "MUSIC VIDEOS",
        "homevideos": "VIDEOS",
        "playlists": "PLAYLISTS",
        "mixed": "MEDIA LIBRARY",
    }
    ALLOWED_ITEM_TYPES = {
        "Movie",
        "Series",
        "BoxSet",
        "MusicAlbum",
        "MusicVideo",
        "Video",
        "Playlist",
    }

    def __init__(self) -> None:
        self.renderer: Any | None = None
        self._font_lock = asyncio.Lock()

    async def run(self, context: PluginContext) -> dict[str, Any]:
        if getattr(context, "trigger", "manual") == "scheduled" and not bool(
            context.config.get("enabled", False)
        ):
            return {
                "status": "skipped",
                "reason": "scheduled_generation_disabled",
            }
        return await ArtworkGenerationRun(self, context).run()

    async def on_event(self, event: PluginEvent, context: PluginContext) -> dict[str, Any]:
        if event.type not in self.manifest.events:
            return {"status": "skipped", "reason": "unsupported_event"}
        if not context.config.get("transfer_monitor", False):
            return {"status": "skipped", "reason": "scrape_monitor_disabled"}
        if int(event.data.get("generated_files") or 0) <= 0:
            return {"status": "skipped", "reason": "no_scraped_changes"}
        if event.type == "metadata.scrape.completed":
            return schedule_refresh(context, event)
        return await self.run(context)

    async def handle_api(self, request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        if request.action == "inventory" and request.method == "GET":
            servers = await context.media_servers.configurations()
            selected = self._string_set(context.config.get("selected_servers"))
            server_id = next(iter(selected), str(servers.get("active_id") or ""))
            libraries = (
                await context.media_servers.libraries(server_id) if server_id else {"items": []}
            )
            return {
                "servers": servers.get("items", []),
                "libraries": libraries.get("items", []),
                "config": context.config,
                "history": context.items.list(100),
            }
        if request.action == "libraries" and request.method == "GET":
            return await context.media_servers.libraries(request.query.get("server_id", ""))
        if request.action == "generate" and request.method == "POST":
            return await self.run(context)
        raise KeyError("封面生成插件页面操作不存在")

    async def _ensure_cjk_font(self, context: PluginContext) -> Path:
        from .renderer import CoverRenderer

        system_font = CoverRenderer.system_cjk_font()
        if system_font:
            return system_font
        font_dir = Path(get_settings().config_dir) / "plugins" / self.manifest.id / "fonts"
        font_path = font_dir / self.FONT_FILENAME
        if self._valid_font(font_path):
            return font_path
        async with self._font_lock:
            if self._valid_font(font_path):
                return font_path
            font_dir.mkdir(parents=True, exist_ok=True)
            temporary = font_dir / f".font-{uuid4().hex}.tmp"
            digest = hashlib.sha256()
            size = 0
            context.logger.info("首次生成封面，正在下载 Noto Sans CJK 中文字体")
            try:
                async with outbound_async_client(
                    ConfigService(),
                    timeout=180,
                    follow_redirects=True,
                ) as client:
                    async with client.stream("GET", self.FONT_URL) as response:
                        response.raise_for_status()
                        font_dir.mkdir(parents=True, exist_ok=True)
                        with temporary.open("wb") as target:
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > self.FONT_MAX_BYTES:
                                    raise ValueError("中文字体文件超过 20 MiB 安全限制")
                                digest.update(chunk)
                                target.write(chunk)
                if digest.hexdigest() != self.FONT_SHA256:
                    raise ValueError("中文字体 SHA-256 校验失败")
                os.replace(temporary, font_path)
                context.logger.info("中文字体已缓存：%s（%s 字节）", font_path, size)
                return font_path
            except Exception as error:
                temporary.unlink(missing_ok=True)
                raise RuntimeError(f"首次生成封面需要下载中文字体，但下载失败：{error}") from error

    def _valid_font(self, path: Path) -> bool:
        if not path.is_file() or path.stat().st_size > self.FONT_MAX_BYTES:
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == self.FONT_SHA256

    async def _download_images(
        self,
        context: PluginContext,
        server_id: str,
        items: list[dict[str, Any]],
        image_sources: tuple[str, ...],
        limit: int,
    ) -> list[bytes]:
        semaphore = asyncio.Semaphore(4)

        async def fetch(item: dict[str, Any]) -> bytes | None:
            for image_type in image_sources:
                if image_type == "Backdrop" and not int(item.get("backdrop_count") or 0):
                    continue
                if image_type == "Primary" and not item.get("has_primary"):
                    continue
                try:
                    async with semaphore:
                        return await context.media_servers.item_image(
                            server_id,
                            str(item.get("id") or ""),
                            image_type,
                        )
                except Exception as error:
                    context.logger.debug(
                        "读取 Emby 图片失败：%s/%s - %s",
                        item.get("id"),
                        image_type,
                        error,
                    )
            return None

        values = await asyncio.gather(*(fetch(item) for item in items[: limit * 3]))
        return [value for value in values if value][:limit]

    def _item_types(self, config: dict[str, Any], library: dict[str, Any]) -> tuple[str, ...]:
        requested = config.get("include_types")
        if isinstance(requested, list):
            cleaned = tuple(
                dict.fromkeys(
                    str(value) for value in requested if str(value) in self.ALLOWED_ITEM_TYPES
                )
            )
            if cleaned:
                return cleaned
        collection_type = str(library.get("collection_type") or "mixed").lower()
        return self.COLLECTION_ITEM_TYPES.get(collection_type, self.COLLECTION_ITEM_TYPES["mixed"])

    def _titles(self, config: dict[str, Any], library: dict[str, Any]) -> tuple[str, str]:
        name = str(library.get("name") or "MEDIA LIBRARY")
        collection_type = str(library.get("collection_type") or "mixed").lower()
        title = name
        subtitle = f"EMBY · {self.COLLECTION_LABELS.get(collection_type, 'MEDIA LIBRARY')}"
        mapping = config.get("title_map")
        if not isinstance(mapping, dict):
            mapping = {}
            for line in str(config.get("title_config") or "").splitlines():
                key, separator, value = line.partition("=")
                if separator and key.strip() and value.strip():
                    zh_title, _, en_title = value.partition("|")
                    mapping[key.strip()] = {
                        "title": zh_title.strip(),
                        "subtitle": en_title.strip(),
                    }
        selected = mapping.get(str(library.get("id") or ""), mapping.get(name))
        if isinstance(selected, str) and selected.strip():
            return selected.strip(), subtitle
        if isinstance(selected, dict):
            title = str(selected.get("title") or title).strip()
            subtitle = str(selected.get("subtitle") or subtitle).strip()
        return title, subtitle

    @staticmethod
    def _string_set(value: object) -> set[str]:
        if not isinstance(value, list):
            return set()
        return {str(item).strip() for item in value if str(item).strip()}

    @staticmethod
    def _image_sources(value: object) -> tuple[str, ...]:
        values = value if isinstance(value, list) else ["Backdrop", "Primary"]
        cleaned = tuple(
            dict.fromkeys(
                str(item).strip().title()
                for item in values
                if str(item).strip().title() in {"Backdrop", "Primary", "Thumb"}
            )
        )
        return cleaned or ("Backdrop", "Primary")


class ArtworkGenerationRun:
    def __init__(
        self,
        plugin: LibraryArtworkPlugin,
        context: PluginContext,
    ) -> None:
        from .renderer import CoverRenderOptions

        self.plugin = plugin
        self.context = context
        self.config = dict(context.config)
        selected_servers = plugin._string_set(self.config.get("selected_servers"))
        selected_libraries = plugin._string_set(self.config.get("include_libraries"))
        if selected_servers:
            self.config["server_id"] = next(iter(selected_servers))
        if selected_libraries:
            self.config["library_ids"] = list(selected_libraries)
        style_base = str(self.config.get("cover_style_base") or "multi")
        self.animated = style_base == "animated"
        style_variant = str(self.config.get("cover_style_variant") or "1")
        self.config["style"] = {
            "single": "spotlight",
            "multi": "mosaic" if style_variant in {"1", "2"} else "split",
            "poster": "filmstrip",
            "animated": "mosaic",
        }.get(style_base, "mosaic")
        self.config["show_count"] = bool(self.config.get("show_item_count", False))
        if bool(self.config.get("use_primary", False)):
            self.config["image_sources"] = ["Primary", "Backdrop"]
        self.server_id = ""
        self.source_limit = min(12, max(1, int(self.config.get("source_limit") or 8)))
        self.image_sources = plugin._image_sources(self.config.get("image_sources"))
        self.options = CoverRenderOptions.from_config(self.config)
        self.image_format = (
            str(self.config.get("animation_format") or "apng").casefold()
            if self.animated
            else "jpeg"
        )
        if self.animated:
            self.options = self._animated_options()
        self.dry_run = bool(self.config.get("dry_run", True))
        self.skip_unchanged = bool(self.config.get("skip_unchanged", True))
        self.results: list[dict[str, Any]] = []
        self.errors: list[dict[str, str]] = []

    def _animated_options(self) -> CoverRenderOptions:
        from .renderer import CoverRenderOptions

        animation_size = str(self.config.get("animation_resolution") or "320x180")
        width_text, _, height_text = animation_size.partition("x")
        return CoverRenderOptions(
            style=self.options.style,
            width=min(640, max(320, int(width_text or 320))),
            height=min(360, max(180, int(height_text or 180))),
            blur_radius=self.options.blur_radius,
            background_color=self.options.background_color,
            show_count=self.options.show_count,
            jpeg_quality=self.options.jpeg_quality,
        )

    async def run(self) -> dict[str, Any]:
        from .renderer import CoverRenderer

        font_path = await self.plugin._ensure_cjk_font(self.context)
        self.plugin.renderer = CoverRenderer(font_path)
        requested_server_id = str(self.config.get("server_id") or "")
        response = await self.context.media_servers.libraries(requested_server_id)
        self.server_id = str(response.get("server_id") or requested_server_id)
        libraries = self._selected_libraries(response)
        if not libraries:
            raise ValueError("没有匹配到可生成封面的 Emby 媒体库")
        for library in libraries:
            await self._process_library(library)
        generated = [item for item in self.results if item.get("status") in {"preview", "updated"}]
        if (
            self.errors
            and not generated
            and not any(item.get("status") == "unchanged" for item in self.results)
        ):
            raise RuntimeError(self.errors[0]["error"])
        self.context.logger.info(
            "Emby 封面生成完成：媒体库 %s，生成 %s，失败 %s，预览模式 %s",
            len(libraries),
            len(generated),
            len(self.errors),
            self.dry_run,
        )
        return self._summary(libraries, generated)

    def _selected_libraries(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        selected_ids = self.plugin._string_set(self.config.get("library_ids"))
        selected_names = self.plugin._string_set(self.config.get("library_names"))
        max_libraries = min(50, max(1, int(self.config.get("max_libraries") or 10)))
        return [
            item
            for item in list(response.get("items") or [])
            if (not selected_ids and not selected_names)
            or str(item.get("id") or "") in selected_ids
            or str(item.get("name") or "") in selected_names
        ][:max_libraries]

    async def _process_library(self, library: dict[str, Any]) -> None:
        library_id = str(library.get("id") or "")
        library_name = str(library.get("name") or "媒体库")
        item_key = f"emby-cover:{self.server_id}:{library_id}"
        try:
            result = await self._generate_library(library, item_key)
            self.results.append(result)
        except Exception as error:
            self._record_failure(item_key, library_id, library_name, error)

    async def _generate_library(
        self,
        library: dict[str, Any],
        item_key: str,
    ) -> dict[str, Any]:
        library_id = str(library.get("id") or "")
        library_name = str(library.get("name") or "媒体库")
        listing = await self.context.media_servers.library_items(
            self.server_id,
            library_id,
            limit=min(50, self.source_limit * 3),
            include_types=self.plugin._item_types(self.config, library),
        )
        images = await self.plugin._download_images(
            self.context,
            self.server_id,
            list(listing.get("items") or []),
            self.image_sources,
            self.source_limit,
        )
        cover = self._render_cover(library, listing, images)
        digest = hashlib.sha256(cover).hexdigest()
        if self._unchanged(item_key, digest):
            return {"library_id": library_id, "name": library_name, "status": "unchanged"}
        result = self._cover_result(library_id, library_name, listing, images, cover, digest)
        if not self.dry_run:
            await self.context.media_servers.set_primary_image(
                self.server_id,
                library_id,
                cover,
                content_type={
                    "jpeg": "image/jpeg",
                    "apng": "image/png",
                    "gif": "image/gif",
                    "webp": "image/webp",
                }[self.image_format],
            )
        self.context.items.record(
            item_key,
            result["status"],
            payload={"server_id": self.server_id, "library_id": library_id, "name": library_name},
            result=result,
        )
        return result

    def _render_cover(
        self,
        library: dict[str, Any],
        listing: dict[str, Any],
        images: list[bytes],
    ) -> bytes:
        title, subtitle = self.plugin._titles(self.config, library)
        renderer = self.plugin.renderer
        if renderer is None:
            raise RuntimeError("封面渲染器尚未初始化")
        if self.animated:
            return renderer.render_animated(
                images,
                title=title,
                subtitle=subtitle,
                item_count=int(listing.get("total") or 0),
                options=self.options,
                image_format=self.image_format,
                duration_seconds=int(self.config.get("animation_duration") or 12),
                frames_per_second=int(self.config.get("animation_fps") or 12),
            )
        return renderer.render(
            images,
            title=title,
            subtitle=subtitle,
            item_count=int(listing.get("total") or 0),
            options=self.options,
        )

    def _unchanged(self, item_key: str, digest: str) -> bool:
        previous = self.context.items.get(item_key) or {}
        previous_value = previous.get("result")
        previous_result = previous_value if isinstance(previous_value, dict) else {}
        return bool(
            self.skip_unchanged
            and previous.get("status") == "updated"
            and previous_result.get("sha256") == digest
        )

    def _cover_result(
        self,
        library_id: str,
        library_name: str,
        listing: dict[str, Any],
        images: list[bytes],
        cover: bytes,
        digest: str,
    ) -> dict[str, Any]:
        return {
            "library_id": library_id,
            "name": library_name,
            "status": "preview" if self.dry_run else "updated",
            "sha256": digest,
            "bytes": len(cover),
            "source_images": len(images),
            "item_count": int(listing.get("total") or 0),
            "style": "animated" if self.animated else self.options.style,
            "format": self.image_format,
            "resolution": f"{self.options.width}x{self.options.height}",
        }

    def _record_failure(
        self,
        item_key: str,
        library_id: str,
        library_name: str,
        error: Exception,
    ) -> None:
        message = str(error)[:500]
        self.context.logger.warning(
            "生成 Emby 媒体库封面失败：%s - %s",
            library_name,
            message,
        )
        self.context.items.record(
            item_key,
            "failed",
            payload={"server_id": self.server_id, "library_id": library_id, "name": library_name},
            result={"error": message},
        )
        self.errors.append({"library_id": library_id, "name": library_name, "error": message})

    def _summary(
        self,
        libraries: list[dict[str, Any]],
        generated: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "dry_run": self.dry_run,
            "library_count": len(libraries),
            "generated_count": len(generated),
            "updated_count": sum(item.get("status") == "updated" for item in self.results),
            "preview_count": sum(item.get("status") == "preview" for item in self.results),
            "unchanged_count": sum(item.get("status") == "unchanged" for item in self.results),
            "error_count": len(self.errors),
            "items": self.results,
            "errors": self.errors,
        }


Plugin = LibraryArtworkPlugin
PLUGIN = LibraryArtworkPlugin
