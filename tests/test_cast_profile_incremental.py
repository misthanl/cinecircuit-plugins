import asyncio
from unittest.mock import AsyncMock

import pytest

from cinecircuit_plugins.cast_profile_enricher.plugin import (
    CastProfileEnricherPlugin,
    _RunState,
)
from test_cast_profile_enricher_plugin import _context


def complete_context():
    context = _context()
    context.media_servers.item_metadata = AsyncMock(
        return_value={
            "name": "示例演员",
            "overview": "已有中文简介",
            "has_primary_image": True,
            "provider_ids": {"Tmdb": "7"},
            "locked_fields": ["Path"],
        }
    )
    context.media.person_detail = AsyncMock(side_effect=AssertionError("不应查询人物"))
    context.media.search_people = AsyncMock(side_effect=AssertionError("不应搜索人物"))
    return context


def test_cast_supplies_role_when_person_has_no_provider_ids():
    context = _context()
    context.media_servers.item_metadata = AsyncMock(return_value={"name": "Example Actor"})
    context.media.search_people = AsyncMock()
    context.media.person_detail = AsyncMock()
    result = asyncio.run(CastProfileEnricherPlugin().run(context))
    context.media.search_people.assert_not_awaited()
    context.media.person_detail.assert_not_awaited()
    assert result["updated_roles"] == 1
    people_updates = [changes["People"] for _, changes in context.media_servers.updates if "People" in changes]
    assert people_updates[-1][0]["Role"] == "英雄 Hero"


def test_known_douban_id_never_triggers_implicit_tmdb_name_search():
    context = _context()
    context.media_servers.item_metadata = AsyncMock(return_value={
        "name": "Example Actor", "provider_ids": {"Douban": "12"},
    })
    context.media.search_people = AsyncMock()
    context.media.person_detail = AsyncMock(return_value={"name": "示例演员"})
    asyncio.run(CastProfileEnricherPlugin().run(context))
    context.media.search_people.assert_not_awaited()
    context.media.person_detail.assert_awaited_once()
    call = context.media.person_detail.await_args
    assert call.args[0] == "douban"
    assert call.args[1]["source_id"] == "12"
    assert call.args[1]["include_fallback"] is False


def test_existing_shared_profile_only_updates_movie_role():
    context = complete_context()
    result = asyncio.run(CastProfileEnricherPlugin().run(context))
    assert result["updated_profiles"] == result["updated_images"] == 0
    assert result["updated_media"] == 1
    assert [item for item, _ in context.media_servers.updates] == ["movie-1", "movie-1"]
    assert context.media_servers.updates[0][1]["People"][0]["Role"] == "英雄 Hero"
    assert context.media_servers.updates[-1][1]["People"][0]["Name"] == "示例演员"
    context.media.person_detail.assert_not_awaited()
    context.media.search_people.assert_not_awaited()


def test_disabled_biography_does_not_trigger_lookups_with_existing_image():
    context = complete_context()
    context.config.update(update_images=False, update_biography=False)
    context.media_servers.item_metadata.return_value = {
        "name": "示例演员",
        "has_primary_image": True,
    }
    result = asyncio.run(CastProfileEnricherPlugin().run(context))
    assert result["updated_media"] == 1
    context.media.person_detail.assert_not_awaited()
    context.media.search_people.assert_not_awaited()
    assert context.media_servers.images == []


def test_complete_tmdb_profile_stops_person_source_queries_with_legacy_config():
    context = _context()
    context.config["metadata_priority"] = "douban_tmdb"
    context.media.person_detail = AsyncMock(wraps=context.media.person_detail)
    context.media.search_people = AsyncMock(wraps=context.media.search_people)
    asyncio.run(CastProfileEnricherPlugin().run(context))
    assert [call.args[0] for call in context.media.person_detail.await_args_list] == ["tmdb"]
    context.media.search_people.assert_not_awaited()
    assert "metadata_priority" not in {
        field["key"] for field in CastProfileEnricherPlugin.manifest.config_schema["fields"]
    }


def test_non_chinese_biography_falls_back_without_overwriting_existing_image():
    context = complete_context()
    context.media_servers.item_metadata.return_value["provider_ids"]["Douban"] = "12"
    context.media_servers.item_metadata.return_value["overview"] = "English biography"
    context.media.person_detail = AsyncMock(
        side_effect=[
            {"name": "示例演员", "biography": "English biography"},
            {"name": "示例演员", "biography": "豆瓣中文简介", "profile": "other.jpg"},
        ]
    )
    context.media.search_people = AsyncMock(
        return_value={"items": [{"name": "Example Actor", "source_id": "12"}]}
    )
    asyncio.run(CastProfileEnricherPlugin().run(context))
    assert [call.args[0] for call in context.media.person_detail.await_args_list] == [
        "tmdb",
        "douban",
    ]
    profile = next(changes for item, changes in context.media_servers.updates if item == "person-1")
    assert profile == {"Overview": "豆瓣中文简介", "LockedFields": ["Path", "Overview"]}
    assert context.media_servers.images == []
    context.media.search_people.assert_not_awaited()


def test_movie_cast_supplies_missing_name_without_person_search():
    context = _context()
    context.config.update(update_images=False, update_biography=False)
    context.media_servers.item_metadata = AsyncMock(
        return_value={
            "name": "Example Actor",
            "has_primary_image": True,
            "provider_ids": {"Tmdb": "7"},
        }
    )
    context.media.person_detail = AsyncMock(return_value={"name": "Example Actor"})
    context.media.search_people = AsyncMock(side_effect=AssertionError("不应重复搜索"))
    result = asyncio.run(CastProfileEnricherPlugin().run(context))
    assert result["updated_profiles"] == 1
    context.media.person_detail.assert_awaited_once()
    context.media.search_people.assert_not_awaited()


def test_missing_image_is_automatically_filled_despite_legacy_disabled_setting():
    context = _context()
    context.config["update_images"] = False
    result = asyncio.run(CastProfileEnricherPlugin().run(context))
    assert result["updated_images"] == 1
    assert "update_images" not in {
        field["key"] for field in CastProfileEnricherPlugin.manifest.config_schema["fields"]
    }


def test_person_cache_is_shared_but_roles_are_per_movie_and_servers_are_isolated():
    context = complete_context()
    context.media.detail = AsyncMock(
        side_effect=[
            {"cast": [{"name": "示例演员", "character": "角色甲"}]},
            {"cast": [{"name": "示例演员", "character": "角色乙"}]},
        ]
    )
    context.media.search_source_identity = AsyncMock(
        return_value={"source_key": "douban", "source_id": "12345"}
    )
    plugin, state = CastProfileEnricherPlugin(), _RunState()
    person = {"Id": "person-1", "Name": "示例演员", "Role": "English", "Type": "Actor"}
    first = {"id": "movie-1", "name": "影片甲", "people": [person]}
    second = {"id": "movie-2", "name": "影片乙", "people": [person]}

    async def run():
        await plugin._process_media(context, state, "server-1", first)
        await plugin._process_media(context, state, "server-1", second)
        await plugin._process_media(context, state, "server-2", first)

    asyncio.run(run())
    assert context.media_servers.item_metadata.await_count == 2
    assert context.media.detail.await_count == 2
    assert [changes["People"][0]["Role"] for _, changes in context.media_servers.updates] == [
        "角色甲",
        "角色乙",
        "角色甲",
    ]


def test_scope_excludes_people_before_external_requests():
    context = _context()
    context.config["condition"] = "missing_role"
    context.media.detail = AsyncMock()
    plugin, state = CastProfileEnricherPlugin(), _RunState()
    asyncio.run(
        plugin._process_media(
            context,
            state,
            "server-1",
            {"people": [{"Name": "示例演员", "Role": "中文角色", "Type": "Actor"}]},
        )
    )
    context.media.detail.assert_not_awaited()
    assert context.media_servers.updates == []


@pytest.mark.parametrize("failure", [True, False])
def test_failed_or_empty_existing_metadata_never_causes_removal(failure):
    context = _context()
    context.config["remove_unresolved"] = True
    context.media_servers.item_metadata = AsyncMock(
        side_effect=RuntimeError("offline") if failure else None, return_value={}
    )
    context.media.detail = AsyncMock(return_value={})
    result = asyncio.run(CastProfileEnricherPlugin().run(context))
    assert result["removed_people"] == 0
    assert context.media_servers.updates == []


def test_all_scope_leaves_complete_profiles_and_chinese_roles_unchanged():
    context = complete_context()
    context.config["condition"] = "all"
    context.media.detail = AsyncMock()
    plugin, state = CastProfileEnricherPlugin(), _RunState()
    asyncio.run(
        plugin._process_media(
            context,
            state,
            "server-1",
            {
                "id": "movie-1",
                "people": [
                    {"Id": "person-1", "Name": "示例演员", "Role": "已有角色", "Type": "Actor"}
                ],
            },
        )
    )
    context.media.detail.assert_not_awaited()
    context.media.person_detail.assert_not_awaited()
    assert context.media_servers.updates == []
    assert context.media_servers.images == []


def test_cached_profiles_are_written_once_across_movies():
    context = _context()
    context.media.person_detail = AsyncMock(wraps=context.media.person_detail)
    plugin, state = CastProfileEnricherPlugin(), _RunState()

    async def run():
        media = (
            await context.media_servers.metadata_items(
                "server-1", "library-1", include_types=("Movie", "Series")
            )
        )["items"][0]
        await plugin._process_media(context, state, "server-1", media)
        await plugin._process_media(context, state, "server-1", {**media, "id": "movie-2"})

    asyncio.run(run())
    assert state.updated_media == 2
    assert state.updated_profiles == state.updated_images == 1
    context.media.person_detail.assert_awaited_once()


def test_douban_person_id_from_movie_cast_avoids_name_search():
    context = _context()
    context.media.detail = AsyncMock(
        return_value={
            "cast": [
                {
                    "name": "示例演员",
                    "aliases": ["Example Actor"],
                    "character": "英雄 Hero",
                    "douban_person_id": "12345",
                }
            ]
        }
    )
    context.media.person_detail = AsyncMock(
        side_effect=[
            {"name": "示例演员"},
            {"biography": "中文简介", "profile": "https://image.example/person.jpg"},
        ]
    )
    context.media.search_people = AsyncMock()
    result = asyncio.run(CastProfileEnricherPlugin().run(context))
    assert result["updated_profiles"] == result["updated_images"] == 1
    assert context.media.person_detail.await_args_list[1].args[1]["source_id"] == "12345"
    context.media.search_people.assert_not_awaited()
