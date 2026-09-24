"""A bounded artwork generation run: plan libraries, render and publish results."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import TYPE_CHECKING, Any
from app.modules.plugins.contracts import PluginContext

if TYPE_CHECKING:
    from .plugin import LibraryArtworkPlugin
    from .renderer import CoverRenderOptions


class ArtworkGenerationRun:
    def __init__(
        self,
        plugin: LibraryArtworkPlugin,
        context: PluginContext,
        *,
        target_libraries: dict[str, set[str]] | None = None,
    ) -> None:
        from .renderer import CoverRenderOptions

        self.plugin = plugin
        self.context = context
        self.target_libraries = target_libraries
        self.config = dict(context.config)
        selected_libraries = plugin._string_set(self.config.get("include_libraries"))
        if selected_libraries:
            self.config["library_ids"] = list(selected_libraries)
        self._configure_style()
        self.config["show_count"] = bool(self.config.get("show_item_count", False))
        if bool(self.config.get("use_primary", True)):
            self.config["image_sources"] = ["Primary", "Backdrop"]
        self.server_id = ""
        self.source_limit = min(12, max(1, int(self.config.get("source_limit") or 8)))
        self.image_sources = plugin._image_sources(self.config.get("image_sources"))
        self.options = CoverRenderOptions.from_config(self.config)
        self.image_format = (
            str(self.config.get("animation_format") or "webp").casefold()
            if self.animated
            else "jpeg"
        )
        if self.animated:
            self.options = self._animated_options()
        self.dry_run = bool(self.config.get("dry_run", False))
        self.skip_unchanged = bool(self.config.get("skip_unchanged", True))
        self.results: list[dict[str, Any]] = []
        self.errors: list[dict[str, str]] = []

    def _animated_options(self) -> CoverRenderOptions:
        from dataclasses import replace

        animation_size = str(self.config.get("animation_resolution") or "1920x1080")
        width_text, _, height_text = animation_size.partition("x")
        return replace(
            self.options,
            width=min(1920, max(320, int(width_text or 1920))),
            height=min(1080, max(180, int(height_text or 1080))),
        )

    async def run(self) -> dict[str, Any]:
        from .renderer import CoverRenderer

        requested = list(dict.fromkeys(map(str, self.config.get("selected_servers") or [])))
        if not requested:
            return {
                "status": "skipped",
                "reason": "no_servers_selected",
                "server_ids": [],
                "library_count": 0,
                "generated_count": 0,
                "items": [],
            }
        await self._validate_servers(requested)
        selected_targets = self._selected_targets(requested)
        plans = await self._library_plans(requested, selected_targets)
        libraries = [library for _, chosen in plans for library in chosen]
        if not libraries:
            return {
                "status": "skipped",
                "reason": "no_libraries",
                "server_ids": requested,
                "library_count": 0,
                "generated_count": 0,
                "items": [],
            }
        font_path = await self.plugin._ensure_cjk_font(self.context)
        self.plugin.renderer = CoverRenderer(font_path)
        try:
            for identity, chosen in plans:
                self.server_id = identity
                for library in chosen:
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
            return {**self._summary(libraries, generated), "server_ids": requested}
        finally:
            self.plugin.renderer = None

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
        cover = await asyncio.to_thread(self._render_cover, library, listing, images)
        digest = hashlib.sha256(cover).hexdigest()
        from .encoding import save_cover

        output_path = await asyncio.to_thread(
            save_cover,
            cover,
            server=self.server_id,
            library=library_id,
            image_format=self.image_format,
        )
        if self._unchanged(item_key, digest):
            return {
                "library_id": library_id,
                "name": library_name,
                "status": "unchanged",
            }
        result = self._cover_result(library_id, library_name, listing, images, cover, digest)
        result["output_path"] = str(output_path)
        await self._publish_cover(cover, result, item_key, library_id, library_name)
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
                duration_seconds=int(self.config.get("animation_duration") or 6),
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
            "style": str(self.config.get("cover_style_base") or "animated")
            if self.animated
            else self.options.style,
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
        from .history import CoverHistory

        CoverHistory().failure()
        self.context.logger.warning(
            "生成 Emby 媒体库封面失败：%s - %s",
            library_name,
            message,
        )
        self.context.items.record(
            item_key,
            "failed",
            payload={
                "server_id": self.server_id,
                "library_id": library_id,
                "name": library_name,
            },
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

    def _configure_style(self):
        style_base = str(self.config.get("cover_style_base") or "multi")
        self.animated = style_base in {
            "animated",
            "animated_diagonal",
            "animated_wedge",
        }
        style_variant = str(self.config.get("cover_style_variant") or "1")
        self.config["style"] = {
            "single": "spotlight",
            "multi": {
                "1": "mosaic",
                "2": "mosaic_focus",
                "3": "split",
                "4": "triptych",
            }.get(style_variant, "mosaic"),
            "poster": "filmstrip",
            "animated": "filmstrip",
            "animated_diagonal": "diagonal",
            "animated_wedge": "wedge",
            "diagonal": "diagonal",
            "echo": "echo",
            "wedge": "wedge",
            "duo": "duo",
            "stack": "stack",
            "editorial": "editorial",
            "panorama": "panorama",
            "cinema": "cinema",
        }.get(style_base, "mosaic")

    def _selected_targets(self, requested):
        selected_targets: dict[str, set[str]] = {}
        for raw in self.config.get("library_targets") or []:
            try:
                server, library = json.loads(raw)
                if (
                    not isinstance(server, str)
                    or not isinstance(library, str)
                    or server not in requested
                ):
                    raise ValueError()
                selected_targets.setdefault(server, set()).add(library)
            except (ValueError, TypeError):
                raise ValueError("媒体库选择已失效，请重新选择") from None
        return selected_targets

    def _choose_libraries(self, response, identity, selected_targets):
        if self.target_libraries is not None:
            target_ids = self.target_libraries.get(identity, set())
            chosen = [
                item
                for item in list(response.get("items") or [])
                if str(item.get("id") or "") in target_ids
            ]
        elif selected_targets:
            all_items = list(response.get("items") or [])
            if selected_targets[identity] - {str(item["id"]) for item in all_items}:
                raise ValueError("所选媒体库已失效，请重新选择")
            chosen = [item for item in all_items if str(item["id"]) in selected_targets[identity]]
        elif "library_targets" in self.config:
            chosen = list(response.get("items") or [])
        else:
            chosen = self._selected_libraries(response)
        return chosen

    async def _library_plans(self, requested, selected_targets):
        plans = []
        remaining = min(50, max(1, int(self.config.get("max_libraries") or 10)))
        for identity in requested:
            if selected_targets and identity not in selected_targets:
                continue
            response = await self.context.media_servers.libraries(identity)
            self.server_id = identity
            chosen = self._choose_libraries(response, identity, selected_targets)
            plans.append((identity, chosen[:remaining]))
            remaining -= len(plans[-1][1])
            if remaining <= 0:
                break
        return plans

    async def _validate_servers(self, requested):
        configurations = await self.context.media_servers.configurations()
        supported = {
            str(item["id"])
            for item in configurations.get("items", [])
            if item.get("enabled", True)
            and str(item.get("type", "")).casefold() in {"emby", "jellyfin"}
        }
        if any(identity not in supported for identity in requested):
            raise ValueError(
                "所选服务器已关闭、删除或类型不受支持，请重新选择已启用的 Emby 或 Jellyfin 服务器"
            )

    async def _publish_cover(self, cover, result, item_key, library_id, library_name):
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
            payload={
                "server_id": self.server_id,
                "library_id": library_id,
                "name": library_name,
            },
            result=result,
        )
        from .history import CoverHistory

        await asyncio.to_thread(CoverHistory().add, cover, result, self.server_id, self.config)
