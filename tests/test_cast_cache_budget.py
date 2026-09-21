import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.modules.plugins.models import PluginState
from app.modules.config.models import ApplicationConfig
from app.modules.plugins.state import PluginStateGateway
from cinecircuit_plugins.cast_profile_enricher.maintenance import Maintenance, SourceRequests
from cinecircuit_plugins.cast_profile_enricher.run_state import RunState
from test_cast_profile_enricher_plugin import _context


def test_complete_works_survive_cache_and_returned_values_are_independent(tmp_path):
    async def scenario():
        engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
        PluginState.__table__.create(engine)
        ApplicationConfig.__table__.create(engine)
        context = _context()
        context.state = PluginStateGateway(sessionmaker(engine), "cast-profile-enricher")
        result = {"name": "Actor", "works": [{"id": 1, "title": "Film"}], "extra": [1, 2]}
        original = copy.deepcopy(result)
        api = SimpleNamespace(person_detail=AsyncMock(return_value=result))
        first = SourceRequests(api, Maintenance(context, RunState()))
        returned = await first.person_detail("tmdb", {"id": "1"})
        returned["works"].clear()
        second = SourceRequests(api, Maintenance(context, RunState()))
        assert await second.person_detail("tmdb", {"id": "1"}) == original
        assert api.person_detail.await_count == 1
        engine.dispose()

    asyncio.run(scenario())


def test_oversize_response_is_returned_in_full_without_caching():
    async def scenario():
        context = _context()
        result = {"works": ["x" * 200_000]}
        api = SimpleNamespace(person_detail=AsyncMock(return_value=result))
        requests = SourceRequests(api, Maintenance(context, RunState()))
        assert await requests.person_detail("tmdb", {}) == result
        assert not requests.cache

    asyncio.run(scenario())


def test_cache_and_progress_failures_do_not_break_source_processing():
    class BrokenStore:
        def scoped(self, _):
            return self

        def get(self, *_):
            raise OSError("read failure")

        def set(self, *_, **__):
            raise OSError("write failure")

        def set_cache(self, *_, **__):
            raise OSError("cache failure")

        def prune_cache(self, **_):
            return 0

    async def scenario():
        context = _context()
        context.state = BrokenStore()
        api = SimpleNamespace(person_detail=AsyncMock(return_value={"works": ["film"]}))
        maintenance = Maintenance(context, RunState())
        requests = SourceRequests(api, maintenance)
        assert await requests.person_detail("tmdb", {}) == {"works": ["film"]}
        maintenance.finish("completed")

    asyncio.run(scenario())


def test_memory_and_lock_counts_are_bounded():
    requests = SourceRequests(SimpleNamespace(), Maintenance(_context(), RunState()))
    for i in range(1100):
        requests.remember(str(i), {"works": ["x" * 10_000]})
    assert len(requests.cache) <= 1000
    assert requests.cache_bytes <= 8 * 1024 * 1024
    assert len(requests.locks) == 64


def test_old_batch_tokens_and_done_markers_are_not_read_or_written():
    from test_cast_maintenance import MemoryState

    context = _context()
    context.state = MemoryState()
    first = Maintenance(context, RunState())
    second = Maintenance(context, RunState())
    assert first.run != second.run
    assert not context.state.rows


def test_upgrade_registers_cache_policy_without_processing_media(tmp_path):
    from sqlalchemy import select
    from cinecircuit_plugins.cast_profile_enricher.plugin import CastProfileEnricherPlugin

    async def scenario():
        engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle.db'}")
        PluginState.__table__.create(engine)
        ApplicationConfig.__table__.create(engine)
        factory = sessionmaker(engine)
        context = _context()
        context.state = PluginStateGateway(factory, "cast-profile-enricher")
        plugin = CastProfileEnricherPlugin()
        plugin._run = AsyncMock()
        await plugin.on_lifecycle("upgrade", context, "1.0.1")
        plugin._run.assert_not_awaited()
        with factory() as session:
            assert session.scalar(select(ApplicationConfig.key)).startswith("runtime:cache_policy:")
            assert list(session.scalars(select(PluginState.id))) == []
        engine.dispose()

    asyncio.run(scenario())
