from __future__ import annotations
import typing

import io
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import (
    Image,
    ImageColor,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
    ImageStat,
)

Font = ImageFont.ImageFont | ImageFont.FreeTypeFont


@dataclass(frozen=True, slots=True)
class CoverRenderOptions:
    style: str = "mosaic"
    width: int = 1920
    height: int = 1080
    blur_radius: int = 32
    background_color: str = ""
    show_count: bool = True
    jpeg_quality: int = 92

    @classmethod
    def from_config(cls, config: dict[typing.Any, typing.Any]) -> "CoverRenderOptions":
        resolutions = {
            "1080p": (1920, 1080),
            "720p": (1280, 720),
            "480p": (854, 480),
        }
        resolution = str(config.get("resolution") or "1080p")
        width, height = resolutions.get(resolution, (1920, 1080))
        if resolution == "custom":
            width = min(7680, max(320, int(config.get("custom_width") or 1920)))
            height = min(4320, max(180, int(config.get("custom_height") or 1080)))
        style = str(config.get("style") or "mosaic")
        if style not in {"spotlight", "split", "mosaic", "filmstrip"}:
            style = "mosaic"
        return cls(
            style=style,
            width=width,
            height=height,
            blur_radius=min(80, max(0, int(config.get("blur_radius") or 32))),
            background_color=str(config.get("background_color") or "").strip(),
            show_count=bool(config.get("show_count", True)),
            jpeg_quality=min(96, max(75, int(config.get("jpeg_quality") or 92))),
        )


class CoverRenderer:
    """Original deterministic Emby cover compositor built only with Pillow."""

    def __init__(self, font_path: Path | str | None = None) -> None:
        self.font_path = Path(font_path) if font_path else None

    def render(
        self,
        source_images: list[bytes],
        *,
        title: str,
        subtitle: str,
        item_count: int,
        options: CoverRenderOptions,
    ) -> bytes:
        images = self._open_images(source_images)
        if not images:
            raise ValueError("没有可用于生成封面的 Emby 图片")
        accent = self._accent_color(images[0], options.background_color)
        if options.style == "spotlight":
            canvas = self._spotlight(images, options, accent)
        elif options.style == "split":
            canvas = self._split(images, options, accent)
        elif options.style == "filmstrip":
            canvas = self._filmstrip(images, options, accent)
        else:
            canvas = self._mosaic(images, options, accent)
        self._draw_copy(
            canvas,
            title=str(title or "MEDIA LIBRARY"),
            subtitle=str(subtitle or "EMBY COLLECTION"),
            item_count=max(0, int(item_count)),
            show_count=options.show_count,
            accent=accent,
        )
        output = io.BytesIO()
        canvas.convert("RGB").save(
            output,
            format="JPEG",
            quality=options.jpeg_quality,
            optimize=True,
            progressive=True,
        )
        return output.getvalue()

    def render_animated(
        self,
        source_images: list[bytes],
        *,
        title: str,
        subtitle: str,
        item_count: int,
        options: CoverRenderOptions,
        image_format: str = "apng",
        duration_seconds: int = 12,
        frames_per_second: int = 12,
    ) -> bytes:
        images = self._open_images(source_images)
        if not images:
            raise ValueError("没有可用于生成动态封面的媒体图片")
        format_name = str(image_format or "apng").casefold()
        if format_name not in {"apng", "gif", "webp"}:
            raise ValueError("动态封面仅支持 APNG、GIF 和 WebP")

        accent = self._accent_color(images[0], options.background_color)
        key_frames = self._animated_key_frames(
            images,
            options,
            accent,
            title=title,
            subtitle=subtitle,
            item_count=item_count,
        )
        seconds = min(60, max(2, int(duration_seconds)))
        fps = min(30, max(1, int(frames_per_second)))
        frame_count = min(36, max(len(key_frames), seconds * fps))
        frames = self._blended_animation_frames(key_frames, frame_count)
        output = io.BytesIO()
        encoder = {"apng": "PNG", "gif": "GIF", "webp": "WEBP"}[format_name]
        if encoder == "GIF":
            frames = [frame.convert("RGB") for frame in frames]
        frames[0].save(
            output,
            format=encoder,
            save_all=True,
            append_images=frames[1:],
            duration=max(20, round(seconds * 1000 / frame_count)),
            loop=0,
        )
        return output.getvalue()

    def _animated_key_frames(
        self,
        images: list[Image.Image],
        options: CoverRenderOptions,
        accent: tuple[int, int, int],
        *,
        title: str,
        subtitle: str,
        item_count: int,
    ) -> list[Image.Image]:
        frames: list[Image.Image] = []
        for offset in range(min(len(images), 6)):
            sources = images[offset:] + images[:offset]
            canvas = self._filmstrip(sources, options, accent)
            self._draw_copy(
                canvas,
                title=str(title or "MEDIA LIBRARY"),
                subtitle=str(subtitle or "EMBY COLLECTION"),
                item_count=max(0, int(item_count)),
                show_count=options.show_count,
                accent=accent,
            )
            frames.append(canvas)
        if len(frames) == 1:
            frames.append(frames[0].copy())
        return frames

    @staticmethod
    def _blended_animation_frames(
        key_frames: list[Image.Image], frame_count: int
    ) -> list[Image.Image]:
        frames: list[Image.Image] = []
        for index in range(frame_count):
            position = index * len(key_frames) / frame_count
            source = key_frames[int(position) % len(key_frames)]
            target = key_frames[(int(position) + 1) % len(key_frames)]
            frames.append(Image.blend(source, target, position % 1))
        return frames

    @staticmethod
    def _open_images(values: list[bytes]) -> list[Image.Image]:
        images = []
        for value in values:
            try:
                with Image.open(io.BytesIO(value)) as image:
                    normalized = ImageOps.exif_transpose(image).convert("RGB")
                    images.append(normalized.copy())
            except (OSError, ValueError):
                continue
        return images

    def _spotlight(
        self,
        images: list[Image.Image],
        options: CoverRenderOptions,
        accent: tuple[int, int, int],
    ) -> Image.Image:
        size = (options.width, options.height)
        background = ImageOps.fit(images[0], size, Image.Resampling.LANCZOS)
        background = ImageEnhance.Color(background).enhance(0.72)
        background = background.filter(ImageFilter.GaussianBlur(options.blur_radius))
        canvas = background.convert("RGBA")
        self._overlay_color(canvas, accent, 82)
        card_width = int(options.width * 0.38)
        card_height = int(options.height * 0.78)
        card = ImageOps.fit(
            images[min(1, len(images) - 1)], (card_width, card_height), Image.Resampling.LANCZOS
        )
        card = self._rounded(card, max(18, options.width // 80))
        x = int(options.width * 0.57)
        y = (options.height - card_height) // 2
        self._paste_shadow(canvas, card, (x, y), max(18, options.width // 90))
        return canvas

    def _split(
        self,
        images: list[Image.Image],
        options: CoverRenderOptions,
        accent: tuple[int, int, int],
    ) -> Image.Image:
        canvas = Image.new("RGBA", (options.width, options.height), (*accent, 255))
        midpoint = int(options.width * 0.54)
        left = ImageOps.fit(images[0], (midpoint, options.height), Image.Resampling.LANCZOS)
        right = ImageOps.fit(
            images[min(1, len(images) - 1)],
            (options.width - midpoint, options.height),
            Image.Resampling.LANCZOS,
        )
        canvas.paste(left, (0, 0))
        canvas.paste(right, (midpoint, 0))
        self._overlay_color(canvas, accent, 54)
        seam = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(seam)
        for offset in range(-160, 161):
            alpha = int(150 * (1 - abs(offset) / 161))
            x = midpoint + offset
            draw.line((x, 0, x, options.height), fill=(5, 10, 18, alpha))
        canvas.alpha_composite(seam)
        return canvas

    def _mosaic(
        self,
        images: list[Image.Image],
        options: CoverRenderOptions,
        accent: tuple[int, int, int],
    ) -> Image.Image:
        canvas = Image.new("RGBA", (options.width, options.height), (*accent, 255))
        columns, rows = 4, 2
        gap = max(6, options.width // 240)
        cell_width = (options.width - gap * (columns - 1)) // columns
        cell_height = (options.height - gap * (rows - 1)) // rows
        for index in range(columns * rows):
            source = images[index % len(images)]
            cell = ImageOps.fit(source, (cell_width, cell_height), Image.Resampling.LANCZOS)
            x = (index % columns) * (cell_width + gap)
            y = (index // columns) * (cell_height + gap)
            canvas.paste(cell, (x, y))
        self._overlay_color(canvas, accent, 42)
        return canvas

    def _filmstrip(
        self,
        images: list[Image.Image],
        options: CoverRenderOptions,
        accent: tuple[int, int, int],
    ) -> Image.Image:
        canvas = Image.new("RGBA", (options.width, options.height), (*accent, 255))
        strip_width = int(options.width * 0.19)
        strip_height = int(options.height * 0.86)
        gap = int(options.width * 0.018)
        start_x = int(options.width * 0.31)
        for index in range(5):
            source = images[index % len(images)]
            strip = ImageOps.fit(source, (strip_width, strip_height), Image.Resampling.LANCZOS)
            strip = self._rounded(strip, max(12, options.width // 120))
            y = int(options.height * 0.07) + (index % 2) * int(options.height * 0.035)
            self._paste_shadow(canvas, strip, (start_x + index * (strip_width + gap), y), 14)
        self._overlay_color(canvas, accent, 36)
        return canvas

    def _draw_copy(
        self,
        canvas: Image.Image,
        *,
        title: str,
        subtitle: str,
        item_count: int,
        show_count: bool,
        accent: tuple[int, int, int],
    ) -> None:
        width, height = canvas.size
        self._draw_background_overlay(canvas)
        draw = ImageDraw.Draw(canvas)
        margin = int(width * 0.065)
        title_font = self._fit_font(title, int(height * 0.15), int(width * 0.49), bold=True)
        subtitle_font = self._font(max(20, int(height * 0.042)), bold=False)
        title_box = draw.textbbox((0, 0), title, font=title_font, stroke_width=1)
        title_height = title_box[3] - title_box[1]
        baseline = int(height * 0.69)
        draw.rounded_rectangle(
            (margin, baseline - 22, margin + int(width * 0.055), baseline - 10),
            radius=6,
            fill=(*self._brighten(accent), 255),
        )
        draw.text(
            (margin, baseline),
            title,
            font=title_font,
            fill=(250, 252, 255, 255),
            stroke_width=max(1, width // 900),
            stroke_fill=(0, 0, 0, 72),
        )
        subtitle_y = baseline + title_height + int(height * 0.035)
        draw.text(
            (margin, subtitle_y),
            subtitle.upper(),
            font=subtitle_font,
            fill=(222, 231, 243, 235),
        )
        if show_count:
            self._draw_count_badge(draw, canvas.size, margin, item_count, accent)

    @staticmethod
    def _draw_background_overlay(canvas: Image.Image) -> None:
        width, height = canvas.size
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for x in range(int(width * 0.68)):
            alpha = int(220 * (1 - x / max(1, width * 0.68)))
            draw.line((x, 0, x, height), fill=(5, 9, 16, alpha))
        for y in range(int(height * 0.48)):
            alpha = int(150 * (1 - y / max(1, height * 0.48)))
            draw.line((0, height - 1 - y, width, height - 1 - y), fill=(5, 9, 16, alpha))
        canvas.alpha_composite(overlay)

    def _draw_count_badge(
        self,
        draw: ImageDraw.ImageDraw,
        size: tuple[int, int],
        margin: int,
        item_count: int,
        accent: tuple[int, int, int],
    ) -> None:
        width, height = size
        badge_font = self._font(max(18, int(height * 0.03)), bold=True)
        label = f"{item_count} ITEMS"
        box = draw.textbbox((0, 0), label, font=badge_font)
        badge_width = box[2] - box[0] + int(width * 0.034)
        badge_height = box[3] - box[1] + int(height * 0.025)
        x, y = margin, int(height * 0.075)
        draw.rounded_rectangle(
            (x, y, x + badge_width, y + badge_height),
            radius=badge_height // 2,
            fill=(8, 14, 24, 188),
            outline=(*self._brighten(accent), 210),
            width=max(2, width // 900),
        )
        draw.text(
            (x + int(width * 0.017), y + int(height * 0.011)),
            label,
            font=badge_font,
            fill=(246, 249, 253, 255),
        )

    def _fit_font(self, text: str, size: int, max_width: int, *, bold: bool) -> Font:
        candidate = max(22, size)
        probe = ImageDraw.Draw(Image.new("RGB", (2, 2)))
        while candidate > 22:
            font = self._font(candidate, bold=bold)
            box = probe.textbbox((0, 0), text, font=font)
            if box[2] - box[0] <= max_width:
                return font
            candidate -= 4
        return self._font(22, bold=bold)

    def _font(self, size: int, *, bold: bool) -> Font:
        return self._load_font(str(self.font_path or ""), size, bold)

    @staticmethod
    @lru_cache(maxsize=128)
    def _load_font(font_path: str, size: int, bold: bool) -> Font:
        if font_path and Path(font_path).is_file():
            return ImageFont.truetype(font_path, size=size)
        names = (
            "NotoSansCJK-Bold.ttc" if bold else "NotoSansCJK-Regular.ttc",
            "NotoSansCJKsc-Bold.otf" if bold else "NotoSansCJKsc-Regular.otf",
            "msyhbd.ttc" if bold else "msyh.ttc",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        )
        directories = (
            Path("/usr/share/fonts/opentype/noto"),
            Path("/usr/share/fonts/truetype/dejavu"),
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
        )
        for directory in directories:
            for name in names:
                path = directory / name
                if path.is_file():
                    return ImageFont.truetype(str(path), size=size)
        for name in names:
            try:
                return ImageFont.truetype(name, size=size)
            except OSError:
                continue
        return ImageFont.load_default(size=size)

    @staticmethod
    def system_cjk_font() -> Path | None:
        candidates = (
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc",
        )
        return next((path for path in candidates if path.is_file()), None)

    @staticmethod
    def _rounded(image: Image.Image, radius: int) -> Image.Image:
        rgba = image.convert("RGBA")
        mask = Image.new("L", rgba.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, *rgba.size), radius=radius, fill=255)
        rgba.putalpha(mask)
        return rgba

    @staticmethod
    def _paste_shadow(
        canvas: Image.Image, image: Image.Image, position: tuple[int, int], blur: int
    ) -> None:
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        mask = image.getchannel("A") if image.mode == "RGBA" else Image.new("L", image.size, 255)
        shadow_layer = Image.new("RGBA", image.size, (0, 0, 0, 180))
        shadow_layer.putalpha(mask)
        shadow.paste(shadow_layer, (position[0] + blur, position[1] + blur), shadow_layer)
        shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
        canvas.alpha_composite(shadow)
        canvas.paste(image, position, image if image.mode == "RGBA" else None)

    @staticmethod
    def _overlay_color(canvas: Image.Image, color: tuple[int, int, int], alpha: int) -> None:
        canvas.alpha_composite(Image.new("RGBA", canvas.size, (*color, alpha)))

    @staticmethod
    def _accent_color(image: Image.Image, configured: str) -> tuple[int, int, int]:
        if configured:
            try:
                configured_color = ImageColor.getrgb(configured)
                return (
                    configured_color[0],
                    configured_color[1],
                    configured_color[2],
                )
            except ValueError:
                pass
        sample = ImageOps.fit(image, (24, 24), Image.Resampling.BILINEAR)
        mean = ImageStat.Stat(sample).mean
        return (
            min(180, max(18, int(mean[0]))),
            min(180, max(18, int(mean[1]))),
            min(180, max(18, int(mean[2]))),
        )

    @staticmethod
    def _brighten(color: tuple[int, int, int]) -> tuple[int, int, int]:
        return (
            min(255, int(color[0] * 1.45 + 28)),
            min(255, int(color[1] * 1.45 + 28)),
            min(255, int(color[2] * 1.45 + 28)),
        )
