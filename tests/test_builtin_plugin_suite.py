from __future__ import annotations

import asyncio
import io
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from app.extensions.schema import ExtensionConfigSchema
from cinecircuit_plugins.auto_signin import SiteCheckinPlugin
from cinecircuit_plugins.brush_flow import SiteTrafficPlugin
from cinecircuit_plugins.media_cover_generator import LibraryArtworkPlugin
from cinecircuit_plugins.media_cover_generator.renderer import (
    CoverRenderer,
    CoverRenderOptions,
)
from cinecircuit_plugins.subtitle_manager import SubtitleWorkspacePlugin
from app.modules.plugins.contracts import PluginApiRequest
from app.modules.plugins.cron import next_cron_time
from app.modules.plugins.gateways import MediaFilesGateway
from app.modules.plugins.permissions import PluginPermission
from cinecircuit_plugins.catalog import test_registry as PluginRegistry


def test_builtin_plugins_are_discoverable() -> None:
    registry = PluginRegistry()
    plugins = {item["id"]: item for item in registry.builtin_catalog()}

    assert {
        "maoyan-rank",
        "douban-hot",
        "auto-signin",
        "brush-flow",
        "emby-cover-generator",
        "subtitle-manager",
        "cookiecloud",
    } <= set(plugins)
    for plugin_id in plugins:
        manifest = registry.builtin_manifest(plugin_id)
        ExtensionConfigSchema(manifest.configuration_fields()).normalize({})


def test_builtin_plugin_config_fields_use_current_user_facing_schema() -> None:
    registry = PluginRegistry()

    for catalog_item in registry.builtin_catalog():
        manifest = registry.builtin_manifest(catalog_item["id"])
        if manifest.schedule_seconds and manifest.id != "cookiecloud":
            assert any(
                field.get("key") == "cron" and field.get("input_type") == "cron"
                for field in manifest.config_schema.get("fields") or []
            ), f"{manifest.id} 的定时任务应提供交互式 Cron 控件"
        for field in manifest.config_schema.get("fields") or []:
            assert "type" not in field, f"{manifest.id}.{field.get('key')} 使用了旧 type 声明"
            assert "min" not in field, f"{manifest.id}.{field.get('key')} 使用了旧 min 声明"
            assert "max" not in field, f"{manifest.id}.{field.get('key')} 使用了旧 max 声明"
            if field.get("visible") is False:
                continue
            default = field.get("default")
            if isinstance(default, bool):
                assert field.get("input_type") == "switch", (
                    f"{manifest.id}.{field.get('key')} 的布尔值必须显示为开关"
                )
            if isinstance(default, dict):
                pytest.fail(f"{manifest.id}.{field.get('key')} 不应直接显示对象默认值")
            if field.get("key") == "cron" and manifest.id != "cookiecloud":
                assert field.get("input_type") == "cron", (
                    f"{manifest.id}.cron 应使用支持时间标签选择和手动输入的 Cron 控件"
                )


def test_each_builtin_plugin_owns_an_isolated_directory() -> None:
    registry = PluginRegistry()
    plugin_ids = {
        "maoyan-rank",
        "douban-hot",
        "auto-signin",
        "brush-flow",
        "emby-cover-generator",
        "subtitle-manager",
        "cookiecloud",
    }

    roots = {plugin_id: registry.builtin_root(plugin_id) for plugin_id in plugin_ids}

    assert len(set(roots.values())) == len(plugin_ids)
    for plugin_id, root in roots.items():
        assert root.name != "builtin"
        assert (root / "plugin.py").is_file()
        frontend_module = registry.builtin_manifest(plugin_id).frontend_module
        if frontend_module:
            assert frontend_module == "frontend.js"
            assert (root / "frontend.ts").is_file()
            assert not (root / frontend_module).exists()


def test_notification_capable_builtin_plugins_are_explicit_opt_in() -> None:
    registry = PluginRegistry()
    for plugin_id in ("auto-signin", "brush-flow", "cookiecloud", "subtitle-manager"):
        manifest = registry.builtin_manifest(plugin_id)
        fields = manifest.config_schema.get("fields") or []
        notification_field = next(
            (field for field in fields if field.get("key") == "notification_enabled"),
            None,
        )
        assert notification_field is not None
        assert notification_field.get("input_type") == "switch"
        assert notification_field.get("default") is False
        assert PluginPermission.NOTIFICATION_SEND in manifest.permissions


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("*/15 * * * *", datetime(2026, 8, 25, 12, 15)),
        ("30 8 * * *", datetime(2026, 8, 26, 8, 30)),
        ("0 9 * * 3", datetime(2026, 8, 26, 9, 0)),
    ],
)
def test_plugin_cron_schedule_matches_five_field_expressions(
    expression: str,
    expected: datetime,
) -> None:
    assert next_cron_time(expression, datetime(2026, 8, 25, 12, 7)) == expected


def test_brush_flow_filters_names_and_torrent_sizes() -> None:
    task = {"include": "2160p|4K", "exclude": "CAM", "min_size": 1, "max_size": 10}

    assert SiteTrafficPlugin._matches({"title": "Movie.2160p", "size": 3 * 1024**3}, task)
    assert not SiteTrafficPlugin._matches({"title": "Movie.CAM.2160p", "size": 3 * 1024**3}, task)
    assert not SiteTrafficPlugin._matches({"title": "Movie.1080p", "size": 3 * 1024**3}, task)
    assert not SiteTrafficPlugin._matches({"title": "Movie.2160p", "size": 12 * 1024**3}, task)


def test_brush_flow_adds_matching_torrents_once() -> None:
    recorded: dict[str, dict[str, object]] = {}

    def remember(key: str, status: str, **kwargs: object) -> dict[str, object]:
        result = {"status": status, **kwargs}
        recorded[key] = result
        return result

    context = SimpleNamespace(
        config={
            "enabled": True,
            "max_tasks": 10,
            "tasks": [
                {
                    "id": "daily",
                    "name": "每日刷流",
                    "enabled": True,
                    "site_id": "site-1",
                    "downloader_id": "qb",
                    "include": "2160p",
                    "max_add": 3,
                },
            ],
        },
        sites=SimpleNamespace(
            feed=AsyncMock(
                return_value={
                    "items": [
                        {
                            "id": "torrent-1",
                            "title": "Movie.2160p",
                            "size": 2 * 1024**3,
                            "download_url": "https://example.com/1",
                        },
                        {
                            "id": "torrent-2",
                            "title": "Movie.1080p",
                            "size": 2 * 1024**3,
                            "download_url": "https://example.com/2",
                        },
                    ]
                }
            )
        ),
        downloads=SimpleNamespace(
            list_tasks=AsyncMock(return_value={"items": []}),
            add=AsyncMock(return_value={"task_id": "hash-1"}),
        ),
        items=SimpleNamespace(get=lambda key: recorded.get(key), record=remember),
    )

    first = asyncio.run(SiteTrafficPlugin().run(context))
    second = asyncio.run(SiteTrafficPlugin().run(context))

    assert first["added"] == 1
    assert second["added"] == 0
    context.downloads.add.assert_awaited_once()


def test_auto_signin_retries_only_matching_transient_failures() -> None:
    signer = AsyncMock(
        side_effect=[RuntimeError("connection timeout"), {"ok": True, "message": "签到成功"}]
    )
    context = SimpleNamespace(
        config={
            "enabled": True,
            "sign_sites": ["site-1"],
            "retry_keyword": "timeout",
            "notification_enabled": False,
        },
        sites=SimpleNamespace(sign_in=signer, check=AsyncMock()),
        items=SimpleNamespace(record=Mock()),
        notifications=SimpleNamespace(send=AsyncMock()),
    )

    result = asyncio.run(SiteCheckinPlugin().run(context))

    assert result["updated_count"] == 1
    assert signer.await_count == 2


def test_media_cover_inventory_uses_selectable_servers_and_libraries() -> None:
    context = SimpleNamespace(
        config={"selected_servers": ["server-1"]},
        media_servers=SimpleNamespace(
            configurations=AsyncMock(
                return_value={
                    "active_id": "server-1",
                    "items": [{"id": "server-1", "name": "Emby"}],
                }
            ),
            libraries=AsyncMock(return_value={"items": [{"id": "movies", "name": "电影"}]}),
        ),
        items=SimpleNamespace(list=Mock(return_value=[])),
    )

    inventory = asyncio.run(
        LibraryArtworkPlugin().handle_api(PluginApiRequest(action="inventory"), context)
    )

    assert inventory["servers"][0]["name"] == "Emby"
    assert inventory["libraries"][0]["name"] == "电影"


def test_subtitle_plugin_deletes_only_through_sidecar_gateway() -> None:
    deleter = AsyncMock(return_value={"subtitle_name": "movie.zh-CN.srt"})
    context = SimpleNamespace(media_files=SimpleNamespace(delete_subtitle=deleter))

    result = asyncio.run(
        SubtitleWorkspacePlugin().handle_api(
            PluginApiRequest(
                action="delete",
                method="POST",
                payload={"media_path": "/media/movie.mkv", "subtitle_name": "movie.zh-CN.srt"},
            ),
            context,
        )
    )

    assert result["subtitle_name"] == "movie.zh-CN.srt"
    deleter.assert_awaited_once_with("/media/movie.mkv", "movie.zh-CN.srt")


@pytest.mark.parametrize(("image_format", "expected"), [("apng", "PNG"), ("gif", "GIF")])
def test_cover_renderer_produces_actual_animated_images(image_format: str, expected: str, monkeypatch) -> None:
    import os
    import shutil
    from pathlib import Path
    from cinecircuit_plugins.media_cover_generator import encoding

    if os.name == 'nt' and (executable := shutil.which('ffmpeg')):
        monkeypatch.setattr(encoding, 'FFMPEG_EXECUTABLE', Path(executable))
    source = []
    for color in ((220, 30, 70), (20, 130, 240), (70, 200, 100)):
        output = io.BytesIO()
        Image.new("RGB", (200, 300), color).save(output, "JPEG")
        source.append(output.getvalue())

    rendered = CoverRenderer().render_animated(
        source,
        title="电影",
        subtitle="MOVIES",
        item_count=5,
        options=CoverRenderOptions(width=320, height=180),
        image_format=image_format,
        duration_seconds=2,
        frames_per_second=2,
    )

    with Image.open(io.BytesIO(rendered)) as image:
        assert image.format == expected
        assert image.size == (320, 180)
        assert image.is_animated
        assert image.n_frames > 1


def test_subtitle_timeline_adjustment_updates_srt_without_touching_other_files(tmp_path) -> None:
    media = tmp_path / "movie.mkv"
    media.touch()
    subtitle = tmp_path / "movie.zh-CN.srt"
    subtitle.write_text("1\n00:00:01,250 --> 00:00:02,750\n第一行\n", encoding="utf-8")
    gateway = MediaFilesGateway(
        Mock(),
        "subtitle-manager",
        1,
        {PluginPermission.MEDIA_FILES_WRITE_SIDECAR},
    )

    result = asyncio.run(gateway.adjust_subtitle(str(media), subtitle.name, offset_seconds=1.5))

    assert result["adjusted_count"] == 1
    assert "00:00:02,750 --> 00:00:04,250" in subtitle.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="当前媒体"):
        asyncio.run(gateway.adjust_subtitle(str(media), "other.srt", offset_seconds=1))


def test_subtitle_plugin_enforces_configured_timeline_limit() -> None:
    adjust = AsyncMock(return_value={"adjusted_count": 2})
    context = SimpleNamespace(
        config={"timeline_max_offset_seconds": 30},
        media_files=SimpleNamespace(adjust_subtitle=adjust),
    )

    result = asyncio.run(
        SubtitleWorkspacePlugin().handle_api(
            PluginApiRequest(
                action="adjust",
                method="POST",
                payload={
                    "media_path": "/media/movie.mkv",
                    "subtitle_name": "movie.zh-CN.srt",
                    "offset_seconds": 1.25,
                },
            ),
            context,
        )
    )

    assert result["adjusted_count"] == 2
    adjust.assert_awaited_once_with("/media/movie.mkv", "movie.zh-CN.srt", offset_seconds=1.25)
    with pytest.raises(ValueError, match="30 秒"):
        asyncio.run(
            SubtitleWorkspacePlugin().handle_api(
                PluginApiRequest(action="adjust", method="POST", payload={"offset_seconds": 31}),
                context,
            )
        )
