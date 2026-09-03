from __future__ import annotations

import asyncio
import base64
import io
import logging
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from app.modules.media.media_server_service import MediaServerService
from cinecircuit_plugins.media_cover_generator import (
    LibraryArtworkPlugin,
)
from cinecircuit_plugins.media_cover_generator import plugin as cover_plugin_module
from cinecircuit_plugins.media_cover_generator.renderer import (
    CoverRenderer,
    CoverRenderOptions,
)
from app.modules.plugins.permissions import PluginPermission
from cinecircuit_plugins.catalog import test_registry as PluginRegistry
from app.modules.plugins.contracts import PluginApiRequest


def jpeg(color: tuple[int, int, int], size: tuple[int, int] = (720, 1080)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, "JPEG", quality=90)
    return output.getvalue()


@pytest.mark.parametrize("style", ["spotlight", "split", "mosaic", "filmstrip"])
def test_original_cover_renderer_outputs_valid_jpeg(style: str) -> None:
    source = [jpeg((30 + index * 15, 70 + index * 10, 120)) for index in range(8)]

    result = CoverRenderer().render(
        source,
        title="华语电影",
        subtitle="EMBY MOVIES",
        item_count=128,
        options=CoverRenderOptions(style=style, width=854, height=480, blur_radius=8),
    )

    with Image.open(io.BytesIO(result)) as image:
        assert image.format == "JPEG"
        assert image.size == (854, 480)


def test_media_server_cover_api_keeps_credentials_in_host_gateway() -> None:
    downloaded = jpeg((22, 66, 110))
    uploaded = jpeg((110, 44, 66), (854, 480))
    requests: list[httpx.Request] = []

    class Config:
        def get_media_servers(self, redact: bool = True) -> dict:
            assert redact is False
            return {
                "active_id": "emby-1",
                "items": [
                    {
                        "uid": "emby-1",
                        "name": "家庭 Emby",
                        "provider": "emby",
                        "enabled": True,
                        "config": {
                            "base_url": "http://emby.local:8096",
                            "api_key": "secret-token",
                        },
                    }
                ],
            }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["X-Emby-Token"] == "secret-token"
        assert request.url.params["api_key"] == "secret-token"
        if request.url.path == "/Library/VirtualFolders/Query":
            return httpx.Response(
                200,
                json={
                    "Items": [{"ItemId": "library-1", "Name": "电影", "CollectionType": "movies"}]
                },
            )
        if request.url.path == "/Items":
            assert request.url.params["ParentId"] == "library-1"
            assert request.url.params["IncludeItemTypes"] == "Movie"
            return httpx.Response(
                200,
                json={
                    "TotalRecordCount": 42,
                    "Items": [
                        {
                            "Id": "movie-1",
                            "Name": "演示电影",
                            "Type": "Movie",
                            "ImageTags": {"Primary": "tag-1"},
                            "BackdropImageTags": ["tag-2"],
                        }
                    ],
                },
            )
        if request.method == "GET" and request.url.path == "/Items/movie-1/Images/Backdrop/0":
            return httpx.Response(200, content=downloaded, headers={"Content-Type": "image/jpeg"})
        if request.method == "POST" and request.url.path == "/Items/library-1/Images/Primary":
            assert request.headers["Content-Type"] == "image/jpeg"
            assert base64.b64decode(request.content) == uploaded
            return httpx.Response(204)
        return httpx.Response(404)

    service = MediaServerService(Config(), transport=httpx.MockTransport(handler))

    async def scenario() -> None:
        libraries = await service.list_libraries()
        assert libraries == {
            "server_id": "emby-1",
            "server_name": "家庭 Emby",
            "items": [{"id": "library-1", "name": "电影", "collection_type": "movies"}],
        }
        listing = await service.list_library_items(
            "emby-1",
            "library-1",
            include_types=["Movie"],
        )
        assert listing["total"] == 42
        assert listing["items"][0]["backdrop_count"] == 1
        assert await service.get_item_image("emby-1", "movie-1", "Backdrop") == downloaded
        result = await service.set_primary_image("emby-1", "library-1", uploaded)
        assert result["bytes"] == len(uploaded)

    asyncio.run(scenario())
    assert len(requests) == 4


def test_emby_cover_plugin_previews_updates_and_skips_unchanged(monkeypatch) -> None:
    source = [jpeg((30 + index * 20, 80, 140)) for index in range(8)]

    class MediaServers:
        def __init__(self) -> None:
            self.uploads: list[bytes] = []

        async def libraries(self, server_id: str = "") -> dict:
            return {
                "server_id": "emby-1",
                "server_name": "家庭 Emby",
                "items": [{"id": "library-1", "name": "华语电影", "collection_type": "movies"}],
            }

        async def library_items(self, server_id, library_id, *, limit, include_types) -> dict:
            assert server_id == "emby-1"
            assert library_id == "library-1"
            assert include_types == ("Movie",)
            return {
                "total": 88,
                "items": [
                    {"id": f"movie-{index}", "has_primary": True, "backdrop_count": 1}
                    for index in range(8)
                ],
            }

        async def item_image(self, server_id, item_id, image_type, *, index=0) -> bytes:
            return source[int(item_id.split("-")[-1])]

        async def set_primary_image(self, server_id, item_id, content, *, content_type) -> dict:
            assert content_type == "image/jpeg"
            self.uploads.append(content)
            return {"ok": True}

    class Items:
        def __init__(self) -> None:
            self.values: dict[str, dict] = {}

        def get(self, key: str) -> dict | None:
            return self.values.get(key)

        def record(self, key, status, *, payload=None, result=None) -> dict:
            value = {
                "item_key": key,
                "status": status,
                "payload": payload or {},
                "result": result or {},
            }
            self.values[key] = value
            return value

    media_servers = MediaServers()
    items = Items()

    def context(*, dry_run: bool):
        return SimpleNamespace(
            config={
                "dry_run": dry_run,
                "style": "mosaic",
                "resolution": "480p",
                "source_limit": 8,
                "title_map": {"华语电影": {"title": "华语电影", "subtitle": "CINEMA"}},
            },
            media_servers=media_servers,
            items=items,
            logger=logging.getLogger("test.emby-cover"),
        )

    plugin = LibraryArtworkPlugin()

    async def skip_font_download(_context):
        return None

    monkeypatch.setattr(plugin, "_ensure_cjk_font", skip_font_download)
    preview = asyncio.run(plugin.run(context(dry_run=True)))
    updated = asyncio.run(plugin.run(context(dry_run=False)))
    unchanged = asyncio.run(plugin.run(context(dry_run=False)))

    assert preview["preview_count"] == 1
    assert preview["updated_count"] == 0
    assert updated["updated_count"] == 1
    assert len(media_servers.uploads) == 1
    assert unchanged["unchanged_count"] == 1
    assert len(media_servers.uploads) == 1


def test_emby_cover_font_is_downloaded_once_to_persistent_cache(tmp_path, monkeypatch) -> None:
    content = b"test-cjk-font"
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, content=content, request=request)

    def client(*_args, **_kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(CoverRenderer, "system_cjk_font", staticmethod(lambda: None))
    monkeypatch.setattr(
        cover_plugin_module,
        "get_settings",
        lambda: SimpleNamespace(config_dir=str(tmp_path)),
    )
    monkeypatch.setattr(cover_plugin_module, "outbound_async_client", client)

    plugin = LibraryArtworkPlugin()
    plugin.FONT_SHA256 = sha256(content).hexdigest()
    context = SimpleNamespace(logger=logging.getLogger("test.emby-cover.font"))
    first = asyncio.run(plugin._ensure_cjk_font(context))
    second = asyncio.run(plugin._ensure_cjk_font(context))

    assert first == second
    assert first.read_bytes() == content
    assert requests == 1


def test_emby_cover_plugin_is_registered_with_explicit_write_permission() -> None:
    catalog = {item["id"]: item for item in PluginRegistry().builtin_catalog()}
    manifest = catalog["emby-cover-generator"]

    assert manifest["schedule_seconds"] == 24 * 60 * 60
    assert manifest["permissions"] == [
        PluginPermission.MEDIA_SERVER_READ,
        PluginPermission.MEDIA_SERVER_WRITE_IMAGES,
    ]
    assert manifest["config_schema"]["fields"][-1] == {
        "key": "dry_run",
        "input_type": "switch",
        "label": "预览模式（不上传）",
        "default": True,
        "description": "只生成预览结果，不修改媒体服务器中的封面",
        "section": "run",
    }


def test_emby_cover_disabled_schedule_skips_but_manual_generate_runs(monkeypatch) -> None:
    runs = 0

    async def fake_run(_self) -> dict[str, str]:
        nonlocal runs
        runs += 1
        return {"status": "generated"}

    monkeypatch.setattr(cover_plugin_module.ArtworkGenerationRun, "run", fake_run)
    plugin = LibraryArtworkPlugin()
    scheduled_context = SimpleNamespace(
        trigger="scheduled",
        config={"enabled": False},
    )
    manual_context = SimpleNamespace(
        trigger="manual",
        config={"enabled": False},
    )

    skipped = asyncio.run(plugin.run(scheduled_context))
    generated = asyncio.run(
        plugin.handle_api(
            PluginApiRequest(action="generate", method="POST"),
            manual_context,
        )
    )

    assert skipped == {
        "status": "skipped",
        "reason": "scheduled_generation_disabled",
    }
    assert generated == {"status": "generated"}
    assert runs == 1


def test_renderer_is_not_imported_at_module_level():
    import ast
    from pathlib import Path
    import cinecircuit_plugins.media_cover_generator.plugin as module
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    assert not any(isinstance(node, ast.ImportFrom) and node.module == "renderer" for node in tree.body)
