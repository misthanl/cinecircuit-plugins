from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace

import httpx

from app.modules.media.media_server_service import MediaServerService
from cinecircuit_plugins.cast_profile_enricher import CastProfileEnricherPlugin
from app.modules.plugins.permissions import PluginPermission
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
    async def person_detail(self, source: str, payload: dict) -> dict:
        assert source == "tmdb"
        assert payload["source_id"] == "7"
        return {
            "name": "示例演员",
            "biography": "示例人物简介",
            "profile": "https://image.example/person.jpg",
            "works": [{"source_id": "99", "character": "英雄"}],
        }

    async def search_people(self, keyword: str, *, source: str, page: int) -> dict:
        raise AssertionError("已有来源 ID 时不应重复搜索")

    async def download_image(self, url: str) -> bytes:
        assert url == "https://image.example/person.jpg"
        return b"\xff\xd8image"


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
        changes for item_id, changes in context.media_servers.updates if item_id == "movie-1"
    )
    assert parent["People"][0]["Name"] == "示例演员"
    assert parent["People"][0]["Role"] == "英雄"
    profile = next(
        changes for item_id, changes in context.media_servers.updates if item_id == "person-1"
    )
    assert profile == {
        "Name": "示例演员",
        "Overview": "示例人物简介",
        "LockedFields": ["Path", "Name", "Overview"],
    }
    assert context.media_servers.images == ["person-1"]


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
        if request.method == "GET" and request.url.path == "/Items/person-1":
            return httpx.Response(200, json={"Id": "person-1", "Name": "Old", "Type": "Person"})
        if request.method == "POST" and request.url.path == "/Items/person-1":
            assert b'"Name":"\xe6\x96\xb0\xe5\x90\x8d"' in request.content
            assert b'"Type":"Person"' in request.content
            return httpx.Response(204)
        return httpx.Response(404)

    service = MediaServerService(Config(), transport=httpx.MockTransport(handler))
    result = asyncio.run(service.update_item_metadata("server-1", "person-1", {"Name": "新名"}))

    assert result["ok"] is True
    assert len(requests) == 2
