from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.modules.plugins.runtime_services import data_directory, http_client
from app.modules.plugins.contracts import (
    PluginApiRequest,
    PluginBase,
    PluginContext,
    PluginEvent,
    PluginManifest,
)
from app.modules.plugins.permissions import PluginPermission
from .event_refresh import (
    REFRESH_EVENT,
    SOURCE_EVENTS,
    locate_target_libraries,
    schedule_refresh,
)

if TYPE_CHECKING:
    pass


from .api import CoverApi
from .generation import ArtworkGenerationRun


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
        version="1.0.1",
        description="为媒体库生成并上传静态或动态风格封面。",
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
        events=(*SOURCE_EVENTS, REFRESH_EVENT),
        frontend_module="frontend.js",
        config_schema={
            "description_display": "hidden",
            "layout": {"columns": 2, "row_gap": 14, "column_gap": 16},
            "editor_width": 920,
            "sections": [
                {
                    "key": "run",
                    "title": "运行设置",
                },
                {
                    "key": "style",
                    "title": "封面样式",
                },
                {
                    "key": "animation",
                    "title": "动态封面",
                },
                {
                    "key": "storage",
                    "title": "缓存与历史",
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
                    "key": "trigger_event",
                    "input_type": "select",
                    "label": "触发事件",
                    "default": "",
                    "section": "run",
                    "description": "不选择时关闭事件触发。",
                    "options": [
                        {"value": "", "label": "不启用"},
                        {"value": "organizer.completed", "label": "整理完成"},
                        {"value": "sync.completed", "label": "同步完成"},
                        {"value": "metadata.scrape.completed", "label": "刮削完成"},
                    ],
                },
                {
                    "key": "delay",
                    "input_type": "number",
                    "label": "触发后延迟执行（秒）",
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
                    "key": "library_targets",
                    "input_type": "textarea",
                    "label": "更新媒体库",
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
                        {"value": "single", "label": "焦点单图｜一张图片铺满"},
                        {"value": "multi", "label": "多图拼贴｜多张剧照组合"},
                        {"value": "poster", "label": "海报长廊｜竖版海报排列"},
                        {"value": "animated", "label": "动态轮播｜图片渐变切换"},
                        {
                            "value": "animated_diagonal",
                            "label": "动态斜向海报墙｜右侧海报循环移动",
                        },
                        {
                            "value": "animated_wedge",
                            "label": "动态斜切轮播｜大图淡入淡出，背景随图变色",
                        },
                        {"value": "diagonal", "label": "斜向画廊｜倾斜圆角海报墙"},
                        {"value": "echo", "label": "扇形叠影｜虚实渐隐卡片"},
                        {"value": "wedge", "label": "斜切大图｜留白与整幅剧照"},
                        {"value": "duo", "label": "留白双海报｜标题与海报分区"},
                        {"value": "stack", "label": "扇形叠卡｜错落层叠海报"},
                        {"value": "editorial", "label": "杂志拼版｜主海报与侧栏"},
                        {"value": "panorama", "label": "胶片横窗｜三幅横图与底栏"},
                        {"value": "cinema", "label": "极简巨幕｜全幅剧照与居中标题"},
                    ],
                },
                {
                    "key": "cover_style_variant",
                    "input_type": "select",
                    "label": "多图布局",
                    "default": "1",
                    "section": "style",
                    "description": "仅多图拼贴模式使用",
                    "options": [
                        {"value": "1", "label": "八宫格"},
                        {"value": "2", "label": "主次拼贴"},
                        {"value": "3", "label": "左右分镜"},
                        {"value": "4", "label": "三联画"},
                    ],
                },
                {
                    "key": "sort_by",
                    "input_type": "select",
                    "label": "媒体排序",
                    "default": "Random",
                    "section": "style",
                    "options": [
                        {"value": "Random", "label": "随机选择"},
                        {"value": "DateCreated", "label": "入库时间"},
                        {"value": "PremiereDate", "label": "首映时间"},
                    ],
                },
                {
                    "key": "use_primary",
                    "input_type": "switch",
                    "label": "优先使用海报图",
                    "default": True,
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
                    "input_type": "select",
                    "label": "主标题字体",
                    "default": "wendao",
                    "section": "style",
                    "options": [
                        {"value": "wendao", "label": "文道潮黑"},
                        {"value": "cuyasong", "label": "粗雅宋"},
                        {"value": "modern", "label": "现代黑体"},
                        {"value": "bold", "label": "电影粗黑"},
                        {"value": "serif", "label": "典雅宋体"},
                    ],
                },
                {
                    "key": "en_font_preset",
                    "input_type": "select",
                    "label": "副标题字体",
                    "default": "emblemaone",
                    "section": "style",
                    "options": [
                        {"value": "emblemaone", "label": "EmblemaOne"},
                        {"value": "melete", "label": "Melete"},
                        {"value": "phosphate", "label": "Phosphate"},
                        {"value": "josefinsans", "label": "JosefinSans"},
                        {"value": "lilitaone", "label": "LilitaOne"},
                        {"value": "monoton", "label": "Monoton"},
                        {"value": "plaster", "label": "Plaster"},
                        {"value": "inter", "label": "Inter 简洁"},
                        {"value": "cinema", "label": "Cinema 宽体"},
                        {"value": "editorial", "label": "Editorial 衬线"},
                    ],
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
                    "default": "1080p",
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
                    "description_display": "always",
                    "input_type": "select",
                    "label": "动态格式",
                    "default": "webp",
                    "description": "1080p 建议使用 WebP；APNG 文件较大，超过宿主 20 MB 限制时需缩短时长。",
                    "section": "animation",
                    "options": [
                        {"value": "webp", "label": "WebP"},
                        {"value": "apng", "label": "APNG"},
                        {"value": "gif", "label": "GIF"},
                    ],
                },
                {
                    "key": "animation_duration",
                    "description_display": "always",
                    "input_type": "number",
                    "label": "动画时长（秒）",
                    "default": 6,
                    "description": "1080p 建议 6 秒循环；更长动画可能超过 20 MB 上传限制。",
                    "validation": {"minimum": 2, "maximum": 60},
                    "section": "animation",
                },
                {
                    "key": "animation_fps",
                    "description_display": "always",
                    "input_type": "number",
                    "label": "动画帧率",
                    "description": "逐帧写入临时目录，最多 500 帧；超过时保留时长并降低实际帧率。",
                    "default": 12,
                    "validation": {"minimum": 1, "maximum": 30},
                    "section": "animation",
                },
                {
                    "key": "animation_resolution",
                    "description_display": "always",
                    "input_type": "select",
                    "label": "动画分辨率",
                    "description": "控制动态封面的输出尺寸；分辨率越高，画面越清晰，生成耗时和文件体积也越大。",
                    "default": "1920x1080",
                    "section": "animation",
                    "options": [
                        {"value": "320x180", "label": "320 × 180"},
                        {"value": "480x270", "label": "480 × 270"},
                        {"value": "640x360", "label": "640 × 360"},
                        {"value": "1280x720", "label": "1280 × 720（720p）"},
                        {"value": "1920x1080", "label": "1920 × 1080（1080p）"},
                    ],
                },
                {
                    "key": "clean_images",
                    "input_type": "switch",
                    "label": "生成后清理图片缓存",
                    "default": True,
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
                    "key": "skip_unchanged",
                    "input_type": "switch",
                    "label": "跳过未变化封面",
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
                    "label": "背景底色（留空自动取色）",
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
                    "key": "background_mode",
                    "input_type": "select",
                    "label": "留白背景",
                    "default": "blurred",
                    "section": "style",
                    "description": "用于带留白的样式；模糊、混色、提亮与颗粒仅作用于背景",
                    "options": [
                        {"value": "solid", "label": "纯色"},
                        {"value": "blurred", "label": "柔焦取色"},
                        {"value": "gradient", "label": "柔和渐变"},
                    ],
                },
                {
                    "key": "text_finish",
                    "input_type": "select",
                    "label": "文字质感",
                    "default": "shadow",
                    "section": "style",
                    "options": [
                        {"value": "clean", "label": "海报白字"},
                        {"value": "shadow", "label": "柔影立体"},
                        {"value": "silver", "label": "银色质感"},
                    ],
                },
                {
                    "key": "background_mix",
                    "input_type": "number",
                    "label": "底色占比（%）",
                    "default": 80,
                    "validation": {"minimum": 0, "maximum": 100},
                    "section": "style",
                },
                {
                    "key": "background_light",
                    "input_type": "number",
                    "label": "横向提亮（%）",
                    "default": 35,
                    "validation": {"minimum": 0, "maximum": 100},
                    "section": "style",
                },
                {
                    "key": "background_grain",
                    "input_type": "number",
                    "label": "磨砂颗粒",
                    "default": 3,
                    "validation": {"minimum": 0, "maximum": 10},
                    "section": "style",
                },
                {
                    "key": "animation_direction",
                    "input_type": "select",
                    "label": "海报移动方向",
                    "default": "up",
                    "section": "style",
                    "options": [
                        {"value": "up", "label": "向上"},
                        {"value": "down", "label": "向下"},
                        {"value": "alternate", "label": "交错滚动"},
                    ],
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
                    "key": "dry_run",
                    "input_type": "switch",
                    "label": "预览模式（不上传）",
                    "default": False,
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
        return await self.generation_run(context).run()

    def generation_run(
        self,
        context: PluginContext,
        *,
        target_libraries: dict[str, set[str]] | None = None,
    ) -> "ArtworkGenerationRun":
        return ArtworkGenerationRun(
            self,
            context,
            target_libraries=target_libraries,
        )

    async def on_event(self, event: PluginEvent, context: PluginContext) -> dict[str, Any]:
        if event.type not in self.manifest.events:
            return {"status": "skipped", "reason": "unsupported_event"}
        selected_event = str(context.config.get("trigger_event") or "").strip()
        if not selected_event:
            return {"status": "skipped", "reason": "event_trigger_disabled"}
        if event.type in SOURCE_EVENTS:
            if event.type != selected_event:
                return {"status": "skipped", "reason": "event_not_selected"}
            if (
                event.type == "metadata.scrape.completed"
                and int(event.data.get("generated_files") or 0) <= 0
            ):
                return {"status": "skipped", "reason": "no_scraped_changes"}
            if not event.data.get("items"):
                return {"status": "skipped", "reason": "missing_media_items"}
            return schedule_refresh(context, event)
        if str(event.data.get("_source_event") or "") != selected_event:
            return {"status": "skipped", "reason": "event_not_selected"}
        targets = await locate_target_libraries(context, event.data)
        if not targets:
            return {"status": "skipped", "reason": "target_libraries_not_found"}
        return await self.generation_run(context, target_libraries=targets).run()

    async def handle_api(self, request: PluginApiRequest, context: PluginContext) -> dict[str, Any]:
        if request.action in {
            "history",
            "history_image",
            "history_delete",
            "history_apply",
        }:
            return await CoverApi(self)._history_api(request, context)
        if request.action == "sample" and request.method == "GET":
            from .preview import read_sample

            return await asyncio.to_thread(
                read_sample,
                request.query.get("style", "multi"),
                request.query.get("variant", "1"),
            )
        if request.action == "preview" and request.method == "POST":
            return await CoverApi(self)._preview_api(request, context)
        if request.action == "preview_status" and request.method == "GET":
            from .preview import preview_status

            return preview_status(str(request.query.get("id") or ""))
        if request.action == "targets" and request.method == "GET":
            return await CoverApi(self)._targets_api(request, context)
        if request.action == "inventory" and request.method == "GET":
            return await CoverApi(self)._inventory_api(request, context)
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
        font_dir = data_directory(self.manifest.id) / "fonts"
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
                async with http_client(
                    use_application_proxy=True,
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
        title = name
        subtitle = ""
        mapping = {}
        for line in str(config.get("title_config") or "").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() and value.strip():
                zh_title, _, en_title = value.partition("|")
                mapping[key.strip()] = {
                    "title": zh_title.strip(),
                    "subtitle": en_title.strip(),
                }
        library_id = str(library.get("id") or "")
        selected = mapping.get(library_id, mapping.get(name))
        # Explicit editor entries take precedence even over legacy ID mappings.
        if selected is None:
            legacy = config.get("title_map")
            if isinstance(legacy, dict):
                selected = legacy.get(library_id, legacy.get(name))
        if isinstance(selected, str) and selected.strip():
            return selected.strip(), subtitle
        if isinstance(selected, dict):
            title = str(selected.get("title") or title).strip()
            subtitle = str(selected.get("subtitle") or "").strip()
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


PLUGIN = LibraryArtworkPlugin

Plugin = LibraryArtworkPlugin
