from __future__ import annotations
import typing

import io
import random
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import (
    Image,
    ImageColor,
    ImageChops,
    ImageDraw,
    ImageFilter,
    ImageOps,
)

from .fonts import CoverFonts, Font

DESIGNED_STYLES = {
    "diagonal",
    "duo",
    "stack",
    "editorial",
    "panorama",
    "cinema",
    "echo",
    "wedge",
}

COPY_WIDTH = {
    "diagonal": 0.35,
    "duo": 0.36,
    "stack": 0.36,
    "echo": 0.35,
    "wedge": 0.35,
    "editorial": 0.27,
    "panorama": 0.86,
    "cinema": 0.78,
    "filmstrip": 0.22,
}

COPY_BASELINE = {
    "diagonal": 0.44,
    "duo": 0.45,
    "stack": 0.45,
    "echo": 0.44,
    "wedge": 0.44,
    "editorial": 0.43,
    "panorama": 0.70,
}


class SubtitleGeometry(typing.NamedTuple):
    size: int
    width_ratio: float
    bar_width: int
    bar_gap: int
    top: float
    left: float


@dataclass(frozen=True, slots=True)
class CoverRenderOptions:
    style: str = "mosaic"
    width: int = 1920
    height: int = 1080
    blur_radius: int = 32
    background_color: str = ""
    show_count: bool = True
    jpeg_quality: int = 92
    zh_font_preset: str = "wendao"
    en_font_preset: str = "emblemaone"
    zh_font_size: int = 170
    en_font_size: int = 75
    background_mode: str = "blurred"
    text_finish: str = "shadow"
    background_mix: int = 80
    background_light: int = 35
    background_grain: int = 3
    animation_direction: str = "up"

    @classmethod
    def from_config(cls, config: dict[typing.Any, typing.Any]) -> "CoverRenderOptions":
        width, height = cls._resolution(config)
        style = str(config.get("style") or "mosaic")
        if (
            style
            not in {
                "spotlight",
                "split",
                "mosaic",
                "mosaic_focus",
                "triptych",
                "filmstrip",
            }
            | DESIGNED_STYLES
        ):
            style = "mosaic"
        return cls(
            style=style,
            width=width,
            height=height,
            blur_radius=min(
                80,
                max(
                    0,
                    int(
                        config.get("blur_radius", 32)
                        if config.get("blur_radius") is not None
                        else 32
                    ),
                ),
            ),
            background_color=str(config.get("background_color") or "").strip(),
            show_count=bool(config.get("show_count", True)),
            jpeg_quality=min(96, max(75, int(config.get("jpeg_quality") or 92))),
            zh_font_preset=str(config.get("zh_font_preset") or "wendao"),
            en_font_preset=str(config.get("en_font_preset") or "emblemaone"),
            zh_font_size=min(400, max(20, int(config.get("zh_font_size") or 170))),
            en_font_size=min(240, max(12, int(config.get("en_font_size") or 75))),
            background_mode=str(config.get("background_mode") or "blurred"),
            text_finish=str(config.get("text_finish") or "shadow"),
            background_mix=min(100, max(0, int(config.get("background_mix", 80)))),
            background_light=min(100, max(0, int(config.get("background_light", 35)))),
            background_grain=min(10, max(0, int(config.get("background_grain", 3)))),
            animation_direction=str(config.get("animation_direction") or "up"),
        )

    @staticmethod
    def _resolution(config):
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
        return width, height


class CoverRenderer(CoverFonts):
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
        if options.style in DESIGNED_STYLES:
            canvas = self._designed_layout(images, options, accent)
        elif options.style == "spotlight":
            canvas = self._spotlight(images, options, accent)
        elif options.style == "split":
            canvas = self._split(images, options, accent)
        elif options.style == "mosaic_focus":
            canvas = self._mosaic_focus(images, options, accent)
        elif options.style == "triptych":
            canvas = self._triptych(images, options, accent)
        elif options.style == "filmstrip":
            canvas = self._filmstrip(images, options, accent)
        else:
            canvas = self._mosaic(images, options, accent)
        self._draw_copy(
            canvas,
            title=str(title or "MEDIA LIBRARY"),
            subtitle=str(subtitle or ""),
            item_count=max(0, int(item_count)),
            options=options,
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
        seconds = min(60, max(2, int(duration_seconds)))
        fps = min(30, max(1, int(frames_per_second)))
        from .encoding import encode_frames

        count = min(500, seconds * fps)
        images = [
            ImageOps.contain(image, (options.width, options.height * 2), Image.Resampling.LANCZOS)
            for image in images
        ]
        frames = self._animation_frames(images, options, accent, count, title, subtitle, item_count)
        return encode_frames(
            frames,
            width=options.width,
            height=options.height,
            frame_count=count,
            seconds=seconds,
            image_format=format_name,
        )

    def _animation_frames(self, images, options, accent, count, title, subtitle, item_count):
        if options.style == "diagonal":
            background = self._paper_background(images[0], options, accent)
            tiles = self._wall_tiles(images, options)
            lettering = self._animation_lettering(options, accent, title, subtitle, item_count)
            for index in range(count):
                frame = self._designed_layout(
                    images,
                    options,
                    accent,
                    scroll_phase=index / count,
                    background=background,
                    wall_tiles=tiles,
                )
                frame.alpha_composite(lettering)
                yield frame
            return
        if options.style == "wedge":
            lettering = self._animation_lettering(options, accent, title, subtitle, item_count)

            def wedge_key(index):
                photo = images[index % min(len(images), 6)]
                color = self._accent_color(photo, options.background_color)
                return self._designed_layout([photo], options, color)

            for frame in self._dissolve_frames(wedge_key, min(len(images), 6), count, 0.55, 0.45):
                frame.alpha_composite(lettering)
                yield frame
            return
        film_options = replace(options, style="filmstrip")

        def key(index):
            offset = index % min(len(images), 6)
            frame = self._filmstrip(images[offset:] + images[:offset], film_options, accent)
            self._draw_copy(
                frame,
                title=title,
                subtitle=subtitle,
                item_count=item_count,
                options=film_options,
                accent=accent,
            )
            return frame

        yield from self._dissolve_frames(key, min(len(images), 6), count, 0.35, 0.65)

    def _animation_lettering(self, options, accent, title, subtitle, item_count):
        lettering = Image.new("RGBA", (options.width, options.height))
        self._draw_copy(
            lettering,
            title=title,
            subtitle=subtitle,
            item_count=item_count,
            options=options,
            accent=accent,
        )
        return lettering

    @staticmethod
    def _dissolve_frames(key, total, count, hold, transition):
        # Retain only adjacent key frames, preserving the original smoothstep timing.
        if count <= 0:
            return
        previous = 0
        left, right = key(0), key(1)
        for index in range(count):
            position = index * total / count
            segment = int(position)
            if segment != previous:
                left = right if previous == segment - 1 and right is not None else key(segment)
                right = key(segment + 1)
                previous = segment
            fraction = max(0.0, (position % 1 - hold) / transition)
            yield Image.blend(left, right, fraction * fraction * (3 - 2 * fraction))

    @staticmethod
    def _blended_animation_frames(
        key_frames: list[Image.Image], frame_count: int
    ) -> list[Image.Image]:
        frames: list[Image.Image] = []
        for index in range(frame_count):
            position = index * len(key_frames) / frame_count
            source = key_frames[int(position) % len(key_frames)]
            target = key_frames[(int(position) + 1) % len(key_frames)]
            # Hold a clear frame for most of each interval, then briefly dissolve.
            fraction = position % 1
            blend = max(0.0, (fraction - 0.75) / 0.25)
            blend = blend * blend * (3 - 2 * blend)
            frames.append(Image.blend(source, target, blend))
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
        canvas = self._paper_background(images[0], options, accent)
        card_width = int(options.width * 0.38)
        card_height = int(options.height * 0.78)
        card = ImageOps.fit(
            images[min(1, len(images) - 1)],
            (card_width, card_height),
            Image.Resampling.LANCZOS,
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
        seam = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(seam)
        seam_width = max(1, options.width // 40)
        for offset in range(-seam_width, seam_width + 1):
            alpha = int(60 * (1 - abs(offset) / (seam_width + 1)))
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
        return canvas

    def _mosaic_focus(
        self,
        images: list[Image.Image],
        options: CoverRenderOptions,
        accent: tuple[int, int, int],
    ) -> Image.Image:
        canvas = Image.new("RGBA", (options.width, options.height), (*accent, 255))
        gap = max(6, options.width // 240)
        focus_width = int(options.width * 0.56)
        focus = ImageOps.fit(images[0], (focus_width, options.height), Image.Resampling.LANCZOS)
        canvas.paste(focus, (0, 0))
        cell_width = (options.width - focus_width - gap * 2) // 2
        cell_height = (options.height - gap) // 2
        for index in range(4):
            cell = ImageOps.fit(
                images[(index + 1) % len(images)],
                (cell_width, cell_height),
                Image.Resampling.LANCZOS,
            )
            x = focus_width + gap + (index % 2) * (cell_width + gap)
            y = (index // 2) * (cell_height + gap)
            canvas.paste(cell, (x, y))
        return canvas

    def _triptych(
        self,
        images: list[Image.Image],
        options: CoverRenderOptions,
        accent: tuple[int, int, int],
    ) -> Image.Image:
        canvas = Image.new("RGBA", (options.width, options.height), (*accent, 255))
        gap = max(6, options.width // 220)
        panel_width = (options.width - gap * 2) // 3
        for index in range(3):
            panel = ImageOps.fit(
                images[index % len(images)],
                (panel_width, options.height),
                Image.Resampling.LANCZOS,
            )
            canvas.paste(panel, (index * (panel_width + gap), 0))
        return canvas

    def _filmstrip(
        self,
        images: list[Image.Image],
        options: CoverRenderOptions,
        accent: tuple[int, int, int],
    ) -> Image.Image:
        canvas = self._paper_background(images[0], options, accent)
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
        return canvas

    def _paper_background(
        self,
        image: Image.Image,
        options: CoverRenderOptions,
        accent: tuple[int, int, int],
    ) -> Image.Image:
        """Independent matte recipe: muted tint, optional optical blur, light and fixed dither.

        Dither uses bounded uniform RGB perturbations, not a borrowed noise function.
        A local fixed seed keeps previews, repeated renders and animation frames stable.
        """
        size = (options.width, options.height)
        tint = accent if options.background_color else tuple(round(c * 0.42 + 70) for c in accent)
        base = Image.new("RGB", size, tint)
        if options.background_mode == "blurred":
            photograph = ImageOps.fit(image, size, Image.Resampling.LANCZOS)
            photograph = photograph.filter(
                ImageFilter.GaussianBlur(options.blur_radius * options.height / 1080)
            )
            base = Image.blend(photograph, base, options.background_mix / 100)
        if options.background_mode != "solid" and options.background_light:
            # Smooth ease-out light across the canvas, not a band over the posters.
            ramp = Image.new("L", (256, 1))
            ramp.putdata(
                [round(options.background_light * 2.55 * (x / 255) ** 0.8) for x in range(256)]
            )
            base = Image.composite(Image.new("RGB", size, "white"), base, ramp.resize(size))
        if options.background_grain:
            rng = random.Random(71423)
            noise = Image.frombytes("RGB", size, rng.randbytes(size[0] * size[1] * 3))
            amplitude = options.background_grain * 2.55
            noise = noise.point([round(128 + (i / 127.5 - 1) * amplitude) for i in range(256)] * 3)
            base = ImageChops.add(base, noise, offset=-128)
        return base.convert("RGBA")

    def _wall_tiles(
        self, images: list[Image.Image], options: CoverRenderOptions
    ) -> list[Image.Image]:
        """Prepare bounded card shadows once; moving frames only translate these tiles."""
        width, height = int(options.width * 0.215), int(options.height * 0.57)
        blur = max(1, round(options.height * 0.006))
        pad = blur * 3
        tiles = []
        for index in range(min(9, len(images))):
            card = ImageOps.fit(images[index], (width, height), Image.Resampling.LANCZOS)
            card = self._rounded(card, max(3, min(width, height) // 14))
            tile = Image.new("RGBA", (width + pad * 2, height + pad * 2))
            self._paste_shadow(tile, card, (pad, pad), blur)
            tiles.append(tile)
        return tiles

    def _designed_layout(
        self,
        images: list[Image.Image],
        options: CoverRenderOptions,
        accent: tuple[int, int, int],
        *,
        scroll_phase: float | None = None,
        background: Image.Image | None = None,
        wall_tiles: list[Image.Image] | None = None,
    ) -> Image.Image:
        """Independent compositions with deliberate space reserved for typography."""
        canvas = (
            background.copy()
            if background is not None
            else self._paper_background(images[0], options, accent)
        )

        def card(index: int, width: int, height: int) -> Image.Image:
            fitted = ImageOps.fit(
                images[index % len(images)],
                (max(1, width), max(1, height)),
                Image.Resampling.LANCZOS,
            )
            return self._rounded(fitted, max(3, min(width, height) // 14))

        if options.style == "diagonal":
            self._draw_diagonal_wall(canvas, images, options, scroll_phase, wall_tiles)
        else:
            canvas = self._draw_still_layout(canvas, images, options, card)
        return canvas

    def _draw_still_layout(self, canvas, images, options, card):
        w, h = options.width, options.height
        if options.style == "echo":
            self._draw_echo(canvas, card)
        elif options.style == "wedge":
            self._draw_wedge(canvas, images)
        elif options.style == "duo":
            for index, x, y in [(0, 0.49, 0.09), (1, 0.735, 0.20)]:
                self._paste_shadow(
                    canvas,
                    card(index, int(w * 0.225), int(h * 0.70)),
                    (int(w * x), int(h * y)),
                    max(2, w // 240),
                )
        elif options.style == "stack":
            self._draw_stack(canvas, card)
        elif options.style == "editorial":
            for index, x, y, cw, ch in [
                (0, 0.37, 0.055, 0.37, 0.89),
                (1, 0.755, 0.055, 0.215, 0.435),
                (2, 0.755, 0.51, 0.215, 0.435),
            ]:
                canvas.alpha_composite(
                    card(index, int(w * cw), int(h * ch)), (int(w * x), int(h * y))
                )
        elif options.style == "panorama":
            for index in range(3):
                tile = card(index, int(w * 0.305), int(h * 0.57))
                canvas.alpha_composite(tile, (int(w * (0.027 + index * 0.321)), int(h * 0.055)))
        else:  # cinema: a single wide still, with centered lower typography.
            canvas = ImageOps.fit(images[0], (w, h), Image.Resampling.LANCZOS).convert("RGBA")
        return canvas

    def _draw_stack(self, canvas, card):
        w, h = canvas.size
        for index, angle, x, y in [
            (2, -14, 0.66, 0.17),
            (1, 10, 0.49, 0.16),
            (0, -3, 0.58, 0.12),
        ]:
            tile = card(index, int(w * 0.26), int(h * 0.73)).rotate(
                angle, Image.Resampling.BICUBIC, expand=True
            )
            self._paste_shadow(canvas, tile, (int(w * x), int(h * y)), max(2, w // 200))

    def _draw_echo(self, canvas, card):
        w, h = canvas.size
        # Same image repeated as receding translucent leaves, sharp front card.
        for angle, opacity, blur, x, y in [
            (22, 0.28, 6, 0.59, 0.08),
            (11, 0.52, 3, 0.54, 0.12),
            (0, 1, 0, 0.51, 0.16),
        ]:
            tile = card(0, int(w * 0.31), int(h * 0.72))
            if blur:
                tile = tile.filter(ImageFilter.GaussianBlur(blur * h / 1080))
            tile.putalpha(tile.getchannel("A").point(lambda p: round(p * opacity)))
            tile = tile.rotate(angle, Image.Resampling.BICUBIC, expand=True)
            self._paste_shadow(canvas, tile, (int(w * x), int(h * y)), max(1, round(h * 0.01)))

    def _draw_wedge(self, canvas, images):
        w, h = canvas.size
        right = ImageOps.fit(images[0], (round(w * 0.66), h), Image.Resampling.LANCZOS).convert(
            "RGBA"
        )
        layer = Image.new("RGBA", canvas.size)
        layer.alpha_composite(right, (round(w * 0.34), 0))
        mask = Image.new("L", canvas.size)
        ImageDraw.Draw(mask).polygon(
            [(round(w * 0.57), 0), (w, 0), (w, h), (round(w * 0.40), h)], fill=255
        )
        layer.putalpha(mask)
        canvas.alpha_composite(layer)

    def _draw_diagonal_wall(self, canvas, images, options, scroll_phase, wall_tiles):
        w, h = options.width, options.height
        cw, ch, gap = int(w * 0.215), int(h * 0.57), max(3, int(w * 0.012))
        sheet = Image.new("RGBA", (3 * (cw + gap), 3 * (ch + gap)), (0, 0, 0, 0))
        tiles = wall_tiles if wall_tiles is not None else self._wall_tiles(images, options)
        pad = max(1, round(h * 0.006)) * 3
        period = 3 * (ch + gap)
        for col in range(3):
            direction = (
                -1
                if options.animation_direction == "down"
                or (options.animation_direction == "alternate" and col % 2)
                else 1
            )
            shift = round(((scroll_phase or 0) * direction % 1) * period)
            stagger = round(ch * (0, 0.12, -0.16)[col])
            for row in range(-1, 7):
                y = row * (ch + gap) - shift + stagger
                if y < sheet.height and y + ch > -gap:
                    tile = tiles[(((row + 1) % 3) * 3 + col) % len(tiles)]
                    sheet.alpha_composite(tile, (col * (cw + gap) - pad, y - pad))
        rotated = sheet.rotate(-14, Image.Resampling.BICUBIC, expand=True)
        # Clip to a slanted right-hand region; left copy never competes with photos.
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        layer.alpha_composite(rotated, (int(w * 0.39), -int(h * 0.40)))
        mask = Image.new("L", canvas.size, 0)
        ImageDraw.Draw(mask).polygon(
            [(int(w * 0.54), 0), (w, 0), (w, h), (int(w * 0.40), h)], fill=255
        )
        layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
        canvas.alpha_composite(layer)

    def _draw_copy(
        self,
        canvas: Image.Image,
        *,
        title: str,
        subtitle: str,
        item_count: int,
        options: CoverRenderOptions,
        accent: tuple[int, int, int],
    ) -> None:
        width, height = canvas.size
        designed = options.style in DESIGNED_STYLES
        if not designed or options.style == "cinema":
            self._draw_background_overlay(canvas, centered=options.style == "cinema")
        copy_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(copy_layer)
        margin: float = int(width * 0.065)
        scale = height / 1080
        title_size = max(20, round(options.zh_font_size * scale))
        subtitle_size = max(12, round(options.en_font_size * scale))
        copy_width = COPY_WIDTH.get(options.style, 0.49)
        title_font = self._copy_title_font(title, title_size, copy_width, options)
        bar_width = max(2, round(22 * scale)) if subtitle.strip() else 0
        bar_gap = max(3, round(18 * scale)) if bar_width else 0
        title_box = draw.textbbox((0, 0), title, font=title_font, stroke_width=1)
        title_height = title_box[3] - title_box[1]
        baseline = int(height * COPY_BASELINE.get(options.style, 0.69))
        if options.style == "cinema":
            margin = (width - (title_box[2] - title_box[0])) // 2
        shadow_color = (round(accent[0] * 0.28), round(accent[1] * 0.28), round(accent[2] * 0.28))
        self._draw_title_material(
            copy_layer,
            (margin, baseline),
            title,
            title_font,
            options.text_finish,
            shadow_color,
        )
        subtitle_y = baseline + title_height + int(height * 0.035)
        geometry = SubtitleGeometry(
            subtitle_size, copy_width, bar_width, bar_gap, subtitle_y, margin
        )
        self._draw_subtitle(copy_layer, subtitle, geometry, options, accent, shadow_color)
        if options.show_count:
            self._draw_count_badge(draw, canvas.size, int(width * 0.065), item_count, accent)
        canvas.alpha_composite(copy_layer)

    def _copy_title_font(self, title, size, width_ratio, options):
        return self._fit_font(
            title,
            size,
            int(options.width * width_ratio),
            bold=True,
            preset=options.zh_font_preset,
            max_height=int(options.height * (0.14 if options.style == "panorama" else 0.19)),
        )

    def _draw_subtitle(self, copy_layer, subtitle, geometry, options, accent, shadow_color):
        draw = ImageDraw.Draw(copy_layer)
        subtitle_size, copy_width, bar_width, bar_gap, subtitle_y, margin = geometry
        width, height = copy_layer.size
        scale = height / 1080
        lines, subtitle_font, line_height, line_gap = self._subtitle_lines(
            subtitle.upper(),
            subtitle_size,
            max(1, int(width * copy_width) - bar_width - bar_gap),
            max(8, height - subtitle_y - round(height * 0.045)),
            options.en_font_preset,
        )
        text_height = len(lines) * line_height + max(0, len(lines) - 1) * line_gap
        if options.style == "cinema":
            margin = int(
                (
                    width
                    - max(
                        (draw.textlength(line, font=subtitle_font) for line in lines),
                        default=0,
                    )
                    - bar_width
                    - bar_gap
                )
                / 2
            )
        margin = self._draw_subtitle_bar(
            draw, margin, subtitle_y, text_height, bar_width, bar_gap, scale, accent
        )
        for index, line in enumerate(lines):
            self._draw_title_material(
                copy_layer,
                (margin, subtitle_y + index * (line_height + line_gap)),
                line,
                subtitle_font,
                options.text_finish,
                shadow_color,
            )

    def _draw_subtitle_bar(self, draw, margin, top, height, width, gap, scale, accent):
        if width:
            padding = max(2, round(14 * scale))
            draw.rectangle(
                (
                    margin,
                    top - padding,
                    margin + width - 1,
                    top + height + padding,
                ),
                fill=(*self._brighten(accent), 255),
            )
            margin += width + gap
        return margin

    @staticmethod
    def _draw_title_material(
        layer: Image.Image,
        position: tuple[float, float],
        text: str,
        font: Font,
        finish: str,
        shadow_color: tuple[int, int, int] = (10, 13, 20),
    ) -> None:
        """Antialiased glyph mask, soft offset shadow and optional satin-silver fill."""
        mask = Image.new("L", layer.size, 0)
        ImageDraw.Draw(mask).text(position, text, font=font, anchor="lt", fill=255)
        scale = max(0.35, layer.height / 1080)
        if finish in {"shadow", "silver"}:
            offset = round(4 * scale)
            shadow_mask = Image.new("L", layer.size, 0)
            shadow_mask.paste(mask, (round(2 * scale), offset))
            shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(3 * scale)).point(
                lambda p: round(p * 0.32)
            )
            shadow = Image.new("RGBA", layer.size, (*shadow_color, 0))
            shadow.putalpha(shadow_mask)
            layer.alpha_composite(shadow)
        ink = Image.new("RGBA", layer.size, (250, 249, 246, 255))
        if finish == "silver":
            bounds = mask.getbbox()
            if bounds:
                gradient = Image.new("RGBA", (1, max(1, bounds[3] - bounds[1])))
                stops = [
                    (0, (255, 255, 253)),
                    (0.42, (224, 229, 235)),
                    (0.50, (178, 187, 200)),
                    (0.59, (249, 251, 255)),
                    (1, (212, 219, 227)),
                ]
                colors = []
                for y in range(gradient.height):
                    t = y / max(1, gradient.height - 1)
                    for (a, ca), (b, cb) in zip(stops, stops[1:]):
                        if a <= t <= b:
                            colors.append(
                                tuple(
                                    round(c + (d - c) * (t - a) / (b - a)) for c, d in zip(ca, cb)
                                )
                                + (255,)
                            )
                            break
                gradient.putdata(colors)
                ink.paste(gradient.resize((layer.width, gradient.height)), (0, bounds[1]))
        ink.putalpha(mask)
        layer.alpha_composite(ink)

    def _subtitle_lines(
        self, text: str, size: int, width: int, height: float, preset: str
    ) -> tuple[list[str], Font, float, int]:
        """Prefer readable word wrapping; shrink only when the available block is full."""
        probe = ImageDraw.Draw(Image.new("L", (1, 1)))
        for candidate in range(max(4, size), 3, -1):
            font = self._font(candidate, bold=False, preset=preset)
            lines = []
            for paragraph in text.splitlines():
                current = ""
                for word in paragraph.split():
                    combined = f"{current} {word}".strip()
                    if current and probe.textlength(combined, font=font) > width:
                        lines.append(current)
                        current = word
                    else:
                        current = combined
                if current:
                    lines.append(current)
            bounds = [probe.textbbox((0, 0), line, font=font, anchor="lt") for line in lines]
            line_height = max((b[3] - b[1] for b in bounds), default=0)
            gap = max(1, round(candidate * 0.22))
            if (
                len(lines) <= 3
                and all(b[2] - b[0] <= width for b in bounds)
                and len(lines) * line_height + max(0, len(lines) - 1) * gap <= height
            ):
                return lines, font, line_height, gap
        # Extremely long tokens still fit by reducing to a bounded display string.
        clipped = text.replace("\n", " ")
        while clipped and probe.textlength(clipped, font=font) > width:
            clipped = clipped[:-1]
        box = probe.textbbox((0, 0), clipped, font=font, anchor="lt")
        return [clipped], font, max(1, box[3] - box[1]), gap

    @staticmethod
    def _draw_background_overlay(canvas: Image.Image, *, centered: bool = False) -> None:
        # One smooth 2D mask: untouched upper half and no intersecting gradient seams.
        mask = Image.new("L", (128, 128))
        values = []
        for y in range(128):
            fy = max(0.0, min(1.0, (y / 127 - 0.46) / 0.40))
            fy = fy * fy * (3 - 2 * fy)
            for x in range(128):
                fx = 1.0 if centered else max(0.0, min(1.0, (0.68 - x / 127) / 0.45))
                fx = fx * fx * (3 - 2 * fx)
                values.append(round(160 * fx * fy))
        mask.putdata(values)
        overlay = Image.new("RGBA", canvas.size, (5, 9, 16, 0))
        overlay.putalpha(mask.resize(canvas.size, Image.Resampling.BILINEAR))
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
        badge_font = self._font(max(18, int(height * 0.03)), bold=True, preset="inter")
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
        shadow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        shadow_layer.putalpha(mask.point(lambda value: round(value * 0.24)))
        shadow.alpha_composite(shadow_layer, (position[0] + blur, position[1] + blur))
        shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
        canvas.alpha_composite(shadow)
        canvas.alpha_composite(image.convert("RGBA"), position)

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
        # Rank coarse palette regions instead of averaging unrelated hues to brown.
        sample = ImageOps.contain(image.convert("RGB"), (64, 64), Image.Resampling.BILINEAR)
        # RGB conversion guarantees three-channel tuples; Pillow types also cover L mode.
        palette = typing.cast(
            list[tuple[int, tuple[int, int, int]]],
            sample.quantize(colors=12).convert("RGB").getcolors(4096) or [],
        )
        candidates = [(count, color) for count, color in palette if 35 < sum(color) / 3 < 220]
        if not candidates:
            candidates = palette
        if not candidates:
            return (80, 95, 110)
        _, color = max(
            candidates,
            key=lambda entry: entry[0] * (0.25 + (max(entry[1]) - min(entry[1])) / 255),
        )
        return (min(200, max(18, color[0])), min(200, max(18, color[1])), min(200, max(18, color[2])))

    @staticmethod
    def _brighten(color: tuple[int, int, int]) -> tuple[int, int, int]:
        return (
            min(255, int(color[0] * 1.45 + 28)),
            min(255, int(color[1] * 1.45 + 28)),
            min(255, int(color[2] * 1.45 + 28)),
        )
