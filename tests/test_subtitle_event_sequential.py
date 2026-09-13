import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from cinecircuit_plugins.subtitle_manager.identity import resolve_identity
from cinecircuit_plugins.subtitle_manager.online_sources.service import OnlineSubtitleService
from cinecircuit_plugins.subtitle_manager.plugin import SubtitleWorkspacePlugin

@pytest.mark.parametrize("first", ["saved", "empty", "low_score", "unavailable", "download_failed", "unpack_failed", "mismatch", "write_failed"])
def test_event_only_visits_next_source_after_unsuccessful_attempt(monkeypatch, first):
    trace = []
    sources = [SimpleNamespace(name=name) for name in ("first", "second", "third")]
    service = OnlineSubtitleService(sources)
    async def bounded(source, requests):
        trace.append("search:" + source.name)
        rows = [] if source.name == "first" and first == "empty" else [SimpleNamespace(
            provider=source.name, downloadable=not(source.name == "first" and first == "unavailable"),
            score=20 if source.name == "first" and first == "low_score" else 90,
        )]
        return SimpleNamespace(errors=()), rows
    service._bounded_source_search = bounded
    monkeypatch.setattr("cinecircuit_plugins.subtitle_manager.online_sources.service.merge_and_rank", lambda rows: tuple(rows))
    async def save(context, target, candidates, **kwargs):
        name = candidates[0].provider
        trace.append("download:" + name)
        success = name == "second" or first == "saved"
        return {"saved": ["subtitle.srt"] if success else [], "failed": int(not success), "skipped": 0}
    monkeypatch.setattr("cinecircuit_plugins.subtitle_manager.plugin.save_candidates", save)
    identity = resolve_identity({"media_path":"/media/Show.S01E02.mkv", "title":"Show", "media_type":"tv", "season":1, "episode":2})
    context = SimpleNamespace(config={"auto_match_score":75}, logger=Mock())
    result = asyncio.run(SubtitleWorkspacePlugin()._process_event_identity(context, service, identity))
    expected = ["search:first"]
    if first not in {"empty", "low_score", "unavailable"}: expected.append("download:first")
    if first != "saved": expected += ["search:second", "download:second"]
    assert trace == expected
    assert result["saved"] == ["subtitle.srt"]


def test_source_search_is_lazy_until_consumer_advances():
    calls = []
    service = OnlineSubtitleService([SimpleNamespace(name="one"), SimpleNamespace(name="two")])
    async def bounded(source, requests):
        calls.append(source.name)
        return SimpleNamespace(errors=()), []
    service._bounded_source_search = bounded
    async def run():
        reports = service.search_sequential([])
        assert calls == []
        await anext(reports)
        assert calls == ["one"]
        await reports.aclose()
    asyncio.run(run())
    assert calls == ["one"]
