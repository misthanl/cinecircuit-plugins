from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.modules.media.media_server_service import MediaServerService
from cinecircuit_plugins.cast_profile_enricher import CastProfileEnricherPlugin
from app.modules.plugins.permissions import PluginPermission
from app.modules.plugins.contracts import PluginEvent
from cinecircuit_plugins.catalog import test_registry as PluginRegistry


class _MediaServers:
    def __init__(self) -> None:
        self.updates: list[tuple[str, dict]] = []
        self.images: list[str] = []

    async def configurations(self) -> dict:
        return {"items": [{"id": "server-1", "enabled": True}]}

    async def libraries(self, server_id: str) -> dict:
        assert server_id == "server-1"
        return {"items": [{"id": "library-1"}]}

    async def metadata_items(self, server_id, library_id, **kwargs) -> dict:
        assert kwargs["include_types"] == ("Movie", "Series")
        return {
            "total": 1,
            "items": [
                {
                    "id": "movie-1",
                    "name": "演示电影",
                    "type": "Movie",
                    "provider_ids": {"Tmdb": "99"},
                    "people": [
                        {
                            "Id": "person-1",
                            "Name": "Example Actor",
                            "Role": "Hero",
                            "Type": "Actor",
                        }
                    ],
                }
            ],
        }

    async def item_metadata(self, server_id: str, item_id: str) -> dict:
        return {
            "id": item_id,
            "name": "Example Actor",
            "provider_ids": {"Tmdb": "7"},
            "locked_fields": ["Path"],
        }

    async def update_item_metadata(self, server_id: str, item_id: str, changes: dict) -> dict:
        self.updates.append((item_id, changes))
        return {"ok": True}

    async def set_primary_image(self, server_id, item_id, content, *, content_type) -> dict:
        assert content_type == "image/jpeg"
        self.images.append(item_id)
        return {"ok": True}


class _Media:
    async def search_source_identity(self, **payload) -> dict:
        assert payload["source"] == "douban"
        assert payload["title"] == "演示电影"
        return {"source_key": "douban", "source_id": "1292052"}

    async def detail(self, source: str, payload: dict) -> dict:
        assert source == "douban"
        assert payload["source_id"] == "1292052"
        return {
            "cast": [
                {
                    "name": "示例演员",
                    "aliases": ["Example Actor"],
                    "character": "英雄 Hero",
                }
            ]
        }

    async def person_detail(self, source: str, payload: dict) -> dict:
        assert source == "tmdb"
        assert payload["source_id"] == "7"
        return {
            "name": "示例演员",
            "biography": "示例人物简介",
            "profile": "https://image.example/person.jpg",
            "works": [{"source_id": "99", "character": "Hero"}],
        }

    async def search_people(self, keyword: str, *, source: str, page: int) -> dict:
        raise AssertionError("已有来源 ID 时不应重复搜索")

    async def download_image(self, url: str) -> bytes:
        assert url == "https://image.example/person.jpg"
        return b"\xff\xd8\xffimage"


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        config={
            "enabled": True,
            "selected_servers": ["server-1"],
            "condition": "missing_any",
            "update_biography": True,
            "update_images": True,
            "remove_unresolved": False,
        },
        media_servers=_MediaServers(),
        media=_Media(),
        logger=logging.getLogger("test.cast-profile-enricher"),
    )


def test_plugin_updates_person_profile_role_and_image() -> None:
    context = _context()
    result = asyncio.run(CastProfileEnricherPlugin().run(context))

    assert result["updated_media"] == 1
    assert result["updated_profiles"] == 1
    assert result["updated_images"] == 1
    parent = next(
        changes
        for item_id, changes in reversed(context.media_servers.updates)
        if item_id == "movie-1"
    )
    assert parent["People"][0]["Name"] == "示例演员"
    assert parent["People"][0]["Role"] == "英雄 Hero"
    profile = next(
        changes for item_id, changes in context.media_servers.updates if item_id == "person-1"
    )
    assert profile == {
        "Name": "示例演员",
        "Overview": "示例人物简介",
        "LockedFields": ["Path", "Name", "Overview"],
    }
    assert context.media_servers.images == ["person-1"]


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"\xff\xd8\xfffixture", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\nfixture", "image/png"),
        (b"RIFF\x08\x00\x00\x00WEBPfixture", "image/webp"),
    ],
)
def test_person_image_content_type_uses_file_signature(content: bytes, expected: str) -> None:
    assert CastProfileEnricherPlugin._image_content_type(content) == expected


def test_localized_role_falls_back_to_unique_latin_character_name() -> None:
    class RoleMedia:
        async def search_source_identity(self, **payload) -> dict:
            return {"source_key": "douban", "source_id": "35811064"}

        async def detail(self, source: str, payload: dict) -> dict:
            assert payload["media_type"] == "movie"
            return {
                "cast": [
                    {"name": "艾哈迈德·塞利姆", "character": "阿里 Ali"},
                    {"name": "另一位演员", "character": "店主"},
                ]
            }

    plugin = CastProfileEnricherPlugin()
    context = SimpleNamespace(media=RoleMedia(), logger=logging.getLogger("test.cast-roles"))
    media = {"name": "欢迎来龙餐馆", "media_type": "Movie", "provider_ids": {}}

    roles = asyncio.run(plugin._localized_roles(context, media))
    localized = plugin._localized_role(
        {},
        media,
        roles,
        person_name="艾哈迈德·萨利姆",
        person_role="Ali",
        localized_name="",
    )

    assert localized == "阿里 Ali"


def test_ambiguous_latin_character_name_is_not_used_as_fallback() -> None:
    class RoleMedia:
        async def search_source_identity(self, **payload) -> dict:
            return {"source_key": "douban", "source_id": "1"}

        async def detail(self, source: str, payload: dict) -> dict:
            assert payload["media_type"] == "tv"
            return {
                "cast": [
                    {"name": "甲", "character": "警察 Police"},
                    {"name": "乙", "character": "警员 Police"},
                ]
            }

    plugin = CastProfileEnricherPlugin()
    context = SimpleNamespace(media=RoleMedia(), logger=logging.getLogger("test.cast-roles"))
    media = {"name": "示例", "media_type": "Series", "provider_ids": {}}

    roles = asyncio.run(plugin._localized_roles(context, media))

    assert "role:police" not in roles


def test_schedule_switch_does_not_block_manual_execution() -> None:
    context = _context()
    context.config["enabled"] = False
    context.trigger = "manual"

    result = asyncio.run(CastProfileEnricherPlugin().run(context))

    assert result["updated_media"] == 1


def test_event_trigger_options_follow_the_requested_order() -> None:
    fields = {
        field["key"]: field for field in CastProfileEnricherPlugin.manifest.config_schema["fields"]
    }

    assert [option["label"] for option in fields["trigger_event"]["options"]] == [
        "不启用",
        "整理完成",
        "同步完成",
        "刮削完成",
    ]
    assert fields["trigger_event"]["default"] == ""


def test_disabled_schedule_skips_only_scheduled_execution() -> None:
    context = _context()
    context.config["enabled"] = False
    context.trigger = "scheduled"

    result = asyncio.run(CastProfileEnricherPlugin().run(context))

    assert result["reason"] == "scheduled_maintenance_disabled"
    assert context.media_servers.updates == []


def test_scrape_completion_schedules_targeted_delayed_refresh() -> None:
    calls = []
    context = _context()
    context.config.update({"trigger_event": "metadata.scrape.completed", "scrape_delay": 45})
    context.jobs = SimpleNamespace(
        schedule_event=lambda event, data, **options: calls.append((event, data, options)) or True
    )
    event = PluginEvent(
        "metadata.scrape.completed",
        {
            "completion_id": "batch:1",
            "provider_key": "local",
            "generated_files": 1,
            "items": [{"identity": {"title": "演示电影"}}],
        },
    )

    result = asyncio.run(CastProfileEnricherPlugin().on_event(event, context))

    assert result == {"status": "pending", "delay_seconds": 45}
    assert calls[0][0] == "cast-profile.media-refresh"
    assert calls[0][2]["delay_seconds"] == 45


@pytest.mark.parametrize("event_type", ["organizer.completed", "sync.completed"])
def test_selected_completion_event_schedules_person_refresh(event_type: str) -> None:
    calls = []
    context = _context()
    context.config.update({"trigger_event": event_type, "scrape_delay": 30})
    context.jobs = SimpleNamespace(
        schedule_event=lambda event, data, **options: calls.append((event, data, options)) or True
    )
    event = PluginEvent(
        event_type,
        {"completion_id": "operation:1", "items": [{"identity": {"title": "演示电影"}}]},
    )

    result = asyncio.run(CastProfileEnricherPlugin().on_event(event, context))

    assert result == {"status": "pending", "delay_seconds": 30}
    assert calls[0][1]["_source_event"] == event_type


def test_empty_event_selection_disables_event_trigger() -> None:
    context = _context()
    context.config["trigger_event"] = ""
    event = PluginEvent(
        "metadata.scrape.completed",
        {"completion_id": "batch:1", "generated_files": 1, "items": [{}]},
    )

    result = asyncio.run(CastProfileEnricherPlugin().on_event(event, context))

    assert result == {"status": "skipped", "reason": "event_trigger_disabled"}


def test_delayed_scrape_refresh_updates_only_matching_media() -> None:
    context = _context()
    context.config["trigger_event"] = "metadata.scrape.completed"
    event = PluginEvent(
        "cast-profile.media-refresh",
        {
            "_source_event": "metadata.scrape.completed",
            "items": [{"identity": {"title": "演示电影"}}],
        },
    )

    result = asyncio.run(CastProfileEnricherPlugin().on_event(event, context))

    assert result["scanned_media"] == 1
    assert result["updated_media"] == 1


def test_delayed_scrape_refresh_does_not_update_unrelated_media() -> None:
    context = _context()
    context.config["trigger_event"] = "metadata.scrape.completed"
    event = PluginEvent(
        "cast-profile.media-refresh",
        {
            "_source_event": "metadata.scrape.completed",
            "items": [{"identity": {"title": "另一部电影", "year": "2025"}}],
        },
    )

    result = asyncio.run(CastProfileEnricherPlugin().on_event(event, context))

    assert result["scanned_media"] == 0
    assert context.media_servers.updates == []


def test_plugin_does_not_remove_people_when_lookup_is_unavailable() -> None:
    class UnavailableMedia:
        async def person_detail(self, source: str, payload: dict) -> dict:
            raise RuntimeError("temporary failure")

        async def search_people(self, keyword: str, *, source: str, page: int) -> dict:
            raise RuntimeError("temporary failure")

    context = _context()
    context.config["remove_unresolved"] = True
    context.media = UnavailableMedia()

    result = asyncio.run(CastProfileEnricherPlugin().run(context))

    assert result["updated_media"] == 0
    assert context.media_servers.updates == []


def test_plugin_is_discovered_without_central_registration() -> None:
    manifest = PluginRegistry().builtin_manifest("cast-profile-enricher")
    assert PluginPermission.MEDIA_SERVER_WRITE_METADATA in manifest.permissions
    assert manifest.name == "演职员资料完善"
    assert manifest.icon == "mdi-account-star-outline"
    assert manifest.config_schema["editor_width"] == 900


def test_cast_icons_are_supported_by_host() -> None:
    project = Path(__file__).resolve().parents[1]
    registry = (
        project.parent / "cinecircuit/frontend/src/icons/mdiRegistry.generated.ts"
    ).read_text(encoding="utf-8")
    supported = set(re.findall(r'"(mdi-[a-z0-9-]+)"\s*:', registry))
    sources = project / "cinecircuit_plugins/cast_profile_enricher"
    used = {
        icon
        for path in sources.iterdir()
        if path.suffix in {".py", ".ts", ".vue"}
        for icon in re.findall(r"mdi-[a-z0-9-]+", path.read_text(encoding="utf-8"))
    }
    assert used - supported == set()


def test_plugin_sources_do_not_contain_upstream_identity_markers() -> None:
    root = Path("app/modules/plugins/builtin/cast_profile_enricher")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py")).casefold()
    markers = ("movie" + "pilot", "person" + "meta", "jxx" + "ghp", "actor" + ".png")
    for marker in markers:
        assert marker not in text


def test_media_server_metadata_gateway_merges_only_allowed_fields() -> None:
    requests: list[httpx.Request] = []

    class Config:
        def get_media_servers(self, redact: bool = True) -> dict:
            assert redact is False
            return {
                "active_id": "server-1",
                "items": [
                    {
                        "uid": "server-1",
                        "name": "家庭媒体库",
                        "provider": "emby",
                        "enabled": True,
                        "config": {"base_url": "http://media.local", "api_key": "secret"},
                    }
                ],
            }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path == "/Users":
            return httpx.Response(
                200,
                json=[{"Id": "admin", "Policy": {"IsAdministrator": True}}],
            )
        if request.method == "GET" and request.url.path == "/emby/Users/admin/Items/person-1":
            return httpx.Response(200, json={"Id": "person-1", "Name": "Old", "Type": "Person"})
        if request.method == "POST" and request.url.path == "/emby/Items/person-1":
            assert b'"Name":"\xe6\x96\xb0\xe5\x90\x8d"' in request.content
            assert b'"Type":"Person"' in request.content
            return httpx.Response(204)
        return httpx.Response(404)

    service = MediaServerService(Config(), transport=httpx.MockTransport(handler))
    result = asyncio.run(service.update_item_metadata("server-1", "person-1", {"Name": "新名"}))

    assert result["ok"] is True
    assert len(requests) == 3
