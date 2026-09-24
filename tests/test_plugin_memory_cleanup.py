import asyncio
import gc
import weakref
from types import SimpleNamespace

import pytest

from cinecircuit_plugins.subtitle_manager import sessions
from cinecircuit_plugins.subtitle_manager.online_sources import subdl
from cinecircuit_plugins.media_cover_generator.fonts import CoverFonts
from cinecircuit_plugins.cast_profile_enricher.plugin import CastProfileEnricherPlugin
from test_cast_profile_enricher_plugin import _context


def test_fallback_sessions_expire_without_further_requests(monkeypatch):
    async def scenario():
        monkeypatch.setattr(sessions, "SESSION_TTL", 1.0)
        store = sessions.SubtitleSessions()
        for i in range(300):
            store._remember(store._candidate_cache, str(i), {})
        assert len(store._candidate_cache) == 256
        await asyncio.sleep(1.1)
        assert not store._candidate_cache
        assert store._expiry_handle is None
    asyncio.run(scenario())


def test_session_timer_does_not_retain_abandoned_instance():
    async def scenario():
        store = sessions.SubtitleSessions()
        store._remember(store._captcha_cache, "token", {})
        reference = weakref.ref(store)
        del store
        assert reference() is None
    asyncio.run(scenario())


def test_subdl_cache_budget_and_request_ownership():
    cache = subdl.OrderedDict()
    subdl._remember_download(cache, "a", [("a", b"x" * (9 * 1024 * 1024))])
    subdl._remember_download(cache, "b", [("b", b"x" * (9 * 1024 * 1024))])
    assert list(cache) == ["b"]
    assert not hasattr(subdl, "_download_cache")


def test_font_cache_dies_with_renderer(monkeypatch):
    font = SimpleNamespace()
    monkeypatch.setattr(CoverFonts, "_load_font", staticmethod(lambda *args: font))
    renderer = CoverFonts()
    renderer.font_path = None
    for size in range(100):
        assert renderer._font(size, bold=False) is font
    assert len(renderer._font_cache) == 32
    reference = weakref.ref(renderer)
    del renderer
    assert reference() is None


@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
def test_cast_releases_request_graph_without_gc(monkeypatch, outcome):
    async def scenario():
        plugin = CastProfileEnricherPlugin()
        references = []
        captured = []
        async def servers(context):
            references.append(weakref.ref(context.media))
            context.media.cache["large"] = {"payload": b"x" * 1024}
            return ["server"]
        async def process(context, state, server, **kwargs):
            captured.append(state)
            state.profiles["actor"] = {"data": b"x" * 1024}
            if outcome == "failure":
                raise ValueError("fixture")
            if outcome == "cancel":
                raise asyncio.CancelledError()
        monkeypatch.setattr(plugin, "_server_ids", servers)
        monkeypatch.setattr(plugin, "_process_server", process)
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            try:
                await plugin._run(_context())
            except (ValueError, asyncio.CancelledError):
                assert outcome != "success"
            assert references[0]() is None
            assert captured[0].maintenance is None
            assert not captured[0].profiles
        finally:
            if was_enabled:
                gc.enable()
    asyncio.run(scenario())


def test_subtitle_disable_clears_fallback_state():
    from cinecircuit_plugins.subtitle_manager.plugin import SubtitleWorkspacePlugin
    async def scenario():
        plugin = SubtitleWorkspacePlugin()
        plugin._sessions._remember(plugin._sessions._captcha_cache, "token", {})
        await plugin.on_lifecycle("disable", None)
        assert not plugin._sessions._captcha_cache
        assert plugin._sessions._expiry_handle is None
    asyncio.run(scenario())


def test_cover_disable_drops_completed_preview():
    from cinecircuit_plugins.media_cover_generator.plugin import LibraryArtworkPlugin
    from cinecircuit_plugins.media_cover_generator.runtime_state import state
    async def scenario():
        task = asyncio.create_task(asyncio.sleep(0, result={"image": b"x" * 1024}))
        await task
        state.jobs["fixture"] = task
        plugin = LibraryArtworkPlugin()
        await plugin.on_lifecycle("disable", None)
        assert "fixture" not in state.jobs
        assert plugin.renderer is None
    asyncio.run(scenario())
