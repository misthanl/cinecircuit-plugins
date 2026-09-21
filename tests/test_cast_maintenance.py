import asyncio
import copy
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cinecircuit_plugins.cast_profile_enricher.plugin import CastProfileEnricherPlugin, _RunState
from cinecircuit_plugins.cast_profile_enricher.maintenance import (
    Maintenance,
    SourceRequests,
    process_checkpoint,
)
from test_cast_profile_enricher_plugin import _context


class MemoryState:
    def __init__(self):
        self.rows = {}

    def scoped(self, _name):
        return self

    def get(self, key):
        row = self.rows.get(key)
        return copy.deepcopy(row[0]) if row and row[1] > time.time() else None

    def set(self, key, value, *, ttl_seconds=0):
        self.rows[key] = (copy.deepcopy(value), time.time() + (ttl_seconds or 86400))


def test_roles_commit_before_person_queries_and_have_separate_counts():
    context = _context()
    original = context.media_servers.item_metadata

    async def metadata(*args):
        assert context.media_servers.updates[0][0] == "movie-1"
        assert context.media_servers.updates[0][1]["People"][0]["Role"] == "英雄 Hero"
        return await original(*args)

    context.media_servers.item_metadata = metadata
    result = asyncio.run(CastProfileEnricherPlugin().run(context))
    assert (
        result["updated_roles"],
        result["updated_names"],
        result["updated_biographies"],
        result["updated_images"],
    ) == (1, 1, 1, 1)


def test_role_only_scope_does_not_rename_but_still_fills_image_and_biography():
    context = _context()
    context.config["condition"] = "missing_role"
    result = asyncio.run(CastProfileEnricherPlugin().run(context))
    assert result["updated_names"] == 0
    assert result["updated_roles"] == result["updated_images"] == result["updated_biographies"] == 1
    assert all(
        "Name" not in changes for key, changes in context.media_servers.updates if key == "person-1"
    )


def test_all_localized_still_fills_missing_image_without_a_switch():
    context = _context()
    context.config.update(condition="missing_role", update_images=False)
    metadata_items = context.media_servers.metadata_items

    async def items(*args, **kwargs):
        page = await metadata_items(*args, **kwargs)
        page["items"][0]["people"][0].update(Name="示例演员", Role="英雄")
        return page

    context.media_servers.metadata_items = items
    context.media_servers.item_metadata = AsyncMock(
        return_value={"name": "示例演员", "overview": "中文简介", "provider_ids": {"Tmdb": "7"}}
    )
    result = asyncio.run(CastProfileEnricherPlugin().run(context))
    assert result["updated_images"] == 1
    assert result["updated_roles"] == result["updated_names"] == 0
    assert result["skipped_people"] == 0


def test_role_prefers_source_identity_over_names():
    plugin = CastProfileEnricherPlugin()
    person = {"Name": "Other Name", "Type": "Actor", "Role": "Hero", "ProviderIds": {"Douban": "7"}}
    cast = [
        {"source_key": "douban", "source_id": "7", "name": "甲", "character": "正确角色"},
        {"name": "Other Name", "character": "错误角色"},
    ]
    assert plugin._role_only(_context(), _RunState(), person, cast, {})["Role"] == "正确角色"


def test_identity_without_chinese_role_does_not_use_another_actors_role():
    plugin = CastProfileEnricherPlugin()
    context, state = _context(), _RunState()
    context.config["condition"] = "missing_role"
    person = {"Id": "p1", "Name": "Same Name", "Type": "Actor", "Role": "Hero"}
    plugin._profile = AsyncMock(return_value={"_provider_ids": {"Douban": "7"}})
    cast = [
        {"source_key": "douban", "source_id": "7", "name": "Different Alias", "character": "Hero"},
        {"name": "Same Name", "character": "错误角色"},
    ]
    updated = asyncio.run(
        plugin._process_person(
            context, state, "s1", {"id": "m1"}, person, plugin._role_map(cast), cast
        )
    )
    assert updated["Role"] == "Hero"
    assert state.no_chinese_role == 1
    assert state.unmatched_people == 0


def test_empty_results_are_deduplicated_only_within_one_run():
    async def scenario():
        context = _context()
        context.state = MemoryState()
        api = SimpleNamespace(search_people=AsyncMock(return_value={"items": []}))
        for _ in range(2):
            requests = SourceRequests(api, Maintenance(context, _RunState()))
            await requests.search_people("Nobody", source="douban")
            await requests.search_people("Nobody", source="douban")
        assert api.search_people.await_count == 2
        for key, (value, _) in list(context.state.rows.items()):
            if key.startswith("cache:"):
                context.state.rows[key] = (value, 0)
        await SourceRequests(api, Maintenance(context, _RunState())).search_people(
            "Nobody", source="douban"
        )
        assert api.search_people.await_count == 3

    asyncio.run(scenario())


def test_cancelled_media_is_retried_and_completed_media_is_checkpointed():
    context = _context()
    context.state = MemoryState()
    plugin = CastProfileEnricherPlugin()
    original = plugin._process_media
    attempted = []

    async def process(ctx, state, server, media):
        attempted.append(media["id"])
        if len(attempted) == 1:
            raise asyncio.CancelledError()
        await original(ctx, state, server, media)

    plugin._process_media = process
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(plugin.run(context))
    asyncio.run(plugin.run(context))
    assert attempted == ["movie-1", "movie-1"]
    assert context.state.get("progress")["status"] == "completed"


def test_douban_query_disables_duplicate_tmdb_fallback():
    context = _context()
    context.media_servers.item_metadata = AsyncMock(
        return_value={
            "name": "Example Actor",
            "provider_ids": {"Tmdb": "7", "Douban": "12"},
        }
    )
    context.media.person_detail = AsyncMock(
        side_effect=[{"name": "示例演员"}, {"name": "示例演员", "biography": "简介"}]
    )
    context.media.search_people = AsyncMock(
        return_value={"items": [{"name": "Example Actor", "source_id": "12"}]}
    )
    asyncio.run(CastProfileEnricherPlugin().run(context))
    assert context.media.person_detail.await_args_list[1].args[1]["include_fallback"] is False
    context.media.search_people.assert_not_awaited()


def test_new_run_never_restores_previous_completed_media():
    async def scenario():
        context = _context()
        context.state = MemoryState()
        first = _RunState()
        first.maintenance = Maintenance(context, first)
        plugin = SimpleNamespace(_process_media=AsyncMock(return_value={}))
        await process_checkpoint(plugin, context, first, "server", {"id": "done"})
        first.maintenance.finish("interrupted")
        resumed = _RunState()
        resumed.maintenance = Maintenance(context, resumed)
        await process_checkpoint(plugin, context, resumed, "server", {"id": "done"})
        await process_checkpoint(plugin, context, resumed, "server", {"id": "unfinished"})
        assert resumed.resumed_media == 0
        assert plugin._process_media.await_count == 3

    asyncio.run(scenario())


def test_partial_media_is_not_checkpointed_and_logs_share_operation(caplog):
    async def scenario():
        context = _context()
        context.state = MemoryState()
        state = _RunState()
        state.maintenance = Maintenance(context, state)
        plugin = SimpleNamespace(
            _process_media=AsyncMock(
                return_value={
                    "status": "partial",
                    "remaining_roles": 1,
                    "updated_roles": 0,
                    "message": "角色未完成",
                }
            )
        )
        media = {"id": "m1", "name": "示例作品"}
        await process_checkpoint(plugin, context, state, "s1", media)
        assert not state.maintenance.read(state.maintenance.done_key("s1", media))
        await process_checkpoint(plugin, context, state, "s1", media)
        assert plugin._process_media.await_count == 2

    import json
    import logging

    with caplog.at_level(logging.INFO):
        asyncio.run(scenario())
    events = [
        json.loads(record.message)["plugin_event"]
        for record in caplog.records
        if record.message.startswith('{"plugin_event":')
    ]
    assert len(events) == 4
    assert len({event["operation_id"] for event in events}) == 1
    assert [event["status"] for event in events] == ["running", "partial", "running", "partial"]


def test_rate_limit_retries_are_bounded_and_failures_are_counted():
    async def scenario():
        import httpx

        context = _context()
        state = _RunState()
        response = httpx.Response(
            429, headers={"Retry-After": "3"}, request=httpx.Request("GET", "https://example.test")
        )
        error = httpx.HTTPStatusError("rate limit", request=response.request, response=response)
        api = SimpleNamespace(search_people=AsyncMock(side_effect=error))
        requests = SourceRequests(api, Maintenance(context, state))
        requests.pace = AsyncMock()
        with pytest.raises(httpx.HTTPStatusError):
            await requests.search_people("actor", source="douban")
        assert api.search_people.await_count == 3
        assert state.request_failures == state.failures == 1
        assert requests.next_at["douban"] > 0
        assert not requests.cache

    asyncio.run(scenario())


def test_concurrent_identical_queries_share_one_request():
    async def scenario():
        context = _context()
        api = SimpleNamespace(search_people=AsyncMock(return_value={"items": [{"name": "actor"}]}))
        requests = SourceRequests(api, Maintenance(context, _RunState()))
        await asyncio.gather(*(requests.search_people("actor", source="tmdb") for _ in range(5)))
        assert api.search_people.await_count == 1

    asyncio.run(scenario())


def test_host_person_api_preserves_explicit_fallback_opt_out():
    from app.modules.plugins.gateway_media_discovery import MediaDiscoveryGateway

    async def scenario():
        service = SimpleNamespace(get_person_detail=AsyncMock(return_value={}))

        async def execute(_permission, _operation, _resource, _audit, call):
            return await call()

        gateway = SimpleNamespace(service=service, _execute=execute)
        await MediaDiscoveryGateway.person_detail(
            gateway, "douban", {"source_id": "7", "include_fallback": False, "unsafe": True}
        )
        assert service.get_person_detail.await_args.args[1] == {
            "source_id": "7",
            "include_fallback": False,
        }

    asyncio.run(scenario())


def test_douban_fallback_is_not_called_when_explicitly_disabled(monkeypatch):
    from app.modules.metadata.source_support import douban_people

    fallback = AsyncMock()
    monkeypatch.setattr(douban_people, "_tmdb_fallback", fallback)
    asyncio.run(
        douban_people.get_person_detail(
            SimpleNamespace(), object, {"name": "actor", "include_fallback": False}
        )
    )
    fallback.assert_not_awaited()
