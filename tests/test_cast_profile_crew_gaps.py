import asyncio
from unittest.mock import AsyncMock

import pytest

from cinecircuit_plugins.cast_profile_enricher.plugin import CastProfileEnricherPlugin, _RunState
from test_cast_profile_enricher_plugin import _context


@pytest.mark.parametrize("kind", ["Director", "Writer"])
@pytest.mark.parametrize("condition", ["missing_any", "missing_name", "missing_role", "all"])
def test_chinese_crew_missing_image_is_filled_and_reused(kind, condition):
    context = _context()
    context.config["condition"] = condition
    context.media_servers.item_metadata = AsyncMock(return_value={
        "name": "中文人物", "overview": "中文简介", "provider_ids": {"Tmdb": "7"},
    })
    context.media.person_detail = AsyncMock(return_value={"profile": "https://image.example/person.jpg"})
    context.media.detail = AsyncMock()
    plugin, state = CastProfileEnricherPlugin(), _RunState()
    person = {"Id": "person-1", "Name": "中文人物", "Type": kind}
    async def run():
        for title in ("影片甲", "影片乙"):
            await plugin._process_media(context, state, "server-1", {"name": title, "people": [person]})
    asyncio.run(run())
    assert context.media_servers.images == ["person-1"]
    assert context.media_servers.updates == []
    context.media_servers.item_metadata.assert_awaited_once()
    context.media.person_detail.assert_awaited_once()
    context.media.detail.assert_not_awaited()


def test_douban_list_is_shared_and_director_image_avoids_person_search():
    context = _context()
    context.config["update_biography"] = False
    context.media_servers.item_metadata = AsyncMock(return_value={"name": "中文人物", "provider_ids": {"Tmdb": "7"}})
    context.media.person_detail = AsyncMock(return_value={})
    context.media.search_people = AsyncMock(side_effect=AssertionError("list already has image"))
    context.media.search_source_identity = AsyncMock(return_value={"source_key": "douban", "source_id": "12"})
    context.media.detail = AsyncMock(return_value={"directors": [
        {"name": "中文人物", "profile": "https://image.example/person.jpg"},
    ]})
    plugin, state = CastProfileEnricherPlugin(), _RunState()
    people = [{"Id": str(index), "Name": "中文人物", "Type": "Director"} for index in range(2)]
    asyncio.run(plugin._process_media(context, state, "server-1", {"name": "影片", "people": people}))
    assert len(context.media_servers.images) == 2
    context.media.detail.assert_awaited_once()
    assert context.media.detail.await_args.args[1]["include_library"] is False
    assert context.media.detail.await_args.args[1]["include_recommendations"] is False
    assert context.media.detail.await_args.args[1].get("include_extensions") is not False
    context.media.search_source_identity.assert_awaited_once()
    context.media.search_people.assert_not_awaited()
    assert all(call.args[0] == "tmdb" for call in context.media.person_detail.await_args_list)


@pytest.mark.parametrize("biography_enabled", [False, True])
def test_biography_obeys_switch_without_changing_out_of_scope_name(biography_enabled):
    context = _context()
    context.config.update(condition="missing_role", update_biography=biography_enabled)
    context.media_servers.item_metadata = AsyncMock(return_value={
        "name": "English Writer", "has_primary_image": True, "provider_ids": {"Tmdb": "7"},
    })
    context.media.person_detail = AsyncMock(return_value={"name": "中文名字", "biography": "中文简介"})
    plugin, state = CastProfileEnricherPlugin(), _RunState()
    asyncio.run(plugin._process_media(context, state, "server-1", {"people": [
        {"Id": "1", "Name": "English Writer", "Type": "Writer"},
    ]}))
    assert context.media.person_detail.await_count == int(biography_enabled)
    assert context.media_servers.images == []
    assert all("Name" not in changes and "People" not in changes for _, changes in context.media_servers.updates)
    assert bool(context.media_servers.updates) == biography_enabled
