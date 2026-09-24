"""Font discovery and bounded fitting for artwork typography."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypeAlias
from PIL import Image, ImageDraw, ImageFont

Font: TypeAlias = ImageFont.ImageFont | ImageFont.FreeTypeFont


class CoverFonts:
    font_path: Path | None

    def _fit_font(
        self,
        text: str,
        size: int,
        max_width: int,
        *,
        bold: bool,
        preset: str = "modern",
        max_height: int | None = None,
    ) -> Font:
        candidate = max(4, size)
        probe = ImageDraw.Draw(Image.new("RGB", (2, 2)))
        while candidate > 4:
            font = self._font(candidate, bold=bold, preset=preset)
            box = probe.textbbox((0, 0), text, font=font)
            if box[2] - box[0] <= max_width and (
                max_height is None or box[3] - box[1] <= max_height
            ):
                return font
            candidate = max(4, candidate - max(1, candidate // 12))
        return self._font(4, bold=bold, preset=preset)

    def _font(self, size: int, *, bold: bool, preset: str = "modern") -> Font:
        cache = getattr(self, "_font_cache", None)
        if cache is None:
            self._font_cache = cache = {}
        key = (str(self.font_path or ""), size, bold, preset)
        if key not in cache:
            if len(cache) >= 32:
                cache.pop(next(iter(cache)))
            cache[key] = self._load_font(*key)
        return cache[key]

    @staticmethod
    def _load_font(font_path: str, size: int, bold: bool, preset: str) -> Font:
        named = CoverFonts._named_font(size, bold, preset)
        if named is not None:
            return named
        names = CoverFonts._font_names(bold, preset)
        if preset == "modern" and font_path and Path(font_path).is_file():
            return ImageFont.truetype(font_path, size=size)
        names = names + (
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
        for name in names:
            for directory in directories:
                path = directory / name
                if path.is_file():
                    return ImageFont.truetype(str(path), size=size)
        if font_path and Path(font_path).is_file():
            return ImageFont.truetype(font_path, size=size)
        for name in names:
            try:
                return ImageFont.truetype(name, size=size)
            except OSError:
                continue
        return ImageFont.load_default(size=size)

    @staticmethod
    def _named_font(size, bold, preset):
        optional = {
            "cuyasong": ("FZCuYaSongS-B-GB.ttf", "FZCYSJW.TTF", "FZCYSK.TTF"),
            "phosphate": ("Phosphate-Solid.otf", "Phosphate.ttc", "Phosphate.ttf"),
        }
        if preset in optional:
            from app.modules.plugins.runtime_services import data_directory

            directories = (
                data_directory("emby-cover-generator") / "fonts",
                Path(__file__).parent / "assets" / "fonts",
            )
            for directory in directories:
                for name in optional[preset]:
                    path = directory / name
                    if path.is_file():
                        return ImageFont.truetype(str(path), size=size)
            label = "粗雅宋" if preset == "cuyasong" else "Phosphate"
            raise ValueError(f"{label} 尚未安装真实字体文件；请安装有权使用的字体，或选择其他字体")
        # Named presets must load their real family, never silently substitute.
        bundled = {
            "wendao": "WenDaoChaoHei.ttf",
            "emblemaone": "EmblemaOne-Regular.ttf",
            "melete": "Melete-Regular.otf",
            "josefinsans": "JosefinSans[wght].ttf",
            "lilitaone": "LilitaOne-Regular.ttf",
            "monoton": "Monoton-Regular.ttf",
            "plaster": "Plaster-Regular.ttf",
        }
        if preset in bundled:
            path = Path(__file__).parent / "assets" / "fonts" / bundled[preset]
            if not path.is_file():
                raise ValueError(f"字体文件缺失：{bundled[preset]}，请重新安装完整插件包")
            font = ImageFont.truetype(str(path), size=size)
            if preset == "josefinsans":
                font.set_variation_by_axes([700 if bold else 400])
            return font
        return None

    @staticmethod
    def _font_names(bold, preset):
        preset_names = {
            "bold": (
                "NotoSansCJKsc-Bold.otf",
                "NotoSansCJK-Bold.ttc",
                "msyhbd.ttc",
                "simhei.ttf",
            ),
            "serif": (
                "NotoSerifCJKsc-Bold.otf" if bold else "NotoSerifCJKsc-Regular.otf",
                "NotoSerifCJK-Bold.ttc" if bold else "NotoSerifCJK-Regular.ttc",
                "simsun.ttc",
            ),
            "cinema": (
                "impact.ttf",
                "Arial Narrow Bold.ttf" if bold else "Arial Narrow.ttf",
                "DejaVuSansCondensed-Bold.ttf" if bold else "DejaVuSansCondensed.ttf",
            ),
            "editorial": (
                "georgiab.ttf" if bold else "georgia.ttf",
                "timesbd.ttf" if bold else "times.ttf",
                "DejaVuSerif-Bold.ttf" if bold else "DejaVuSerif.ttf",
            ),
            "inter": (
                "arialbd.ttf" if bold else "arial.ttf",
                "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            ),
        }
        names = preset_names.get(preset, ())
        return names

    @staticmethod
    def system_cjk_font() -> Path | None:
        candidates = (
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc",
        )
        return next((path for path in candidates if path.is_file()), None)
