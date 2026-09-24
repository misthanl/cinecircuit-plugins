import asyncio
from types import SimpleNamespace

from cinecircuit_plugins.maoyan_rank.prefetch import identity_prefetch


def test_prefetch_is_bounded_ordered_and_canceled_on_exit():
    async def run():
        started = []
        canceled = []
        gate = asyncio.Event()

        async def resolve(context, row, cache):
            started.append(row["title"])
            if row["title"] == "one":
                return {"title": "one"}
            try:
                await gate.wait()
            finally:
                canceled.append(row["title"])

        rows = [{"title": title} for title in ["one", "two", "three"]]
        cache = {"large_response": bytearray(1024 * 1024)}
        async with identity_prefetch(SimpleNamespace(), rows, resolve, cache) as prepared:
            async for row, task in prepared:
                assert row["title"] == "one"
                assert (await task)["title"] == "one"
                await asyncio.sleep(0)
                assert started == ["one", "two"]
                break
        assert canceled == ["two"]
        assert cache == {}

    asyncio.run(run())


def test_season_prefetch_uses_explicit_title_season_and_failure_keeps_identity(monkeypatch):
    from unittest.mock import AsyncMock, Mock
    from cinecircuit_plugins.maoyan_rank import plugin as module
    match = {"source_key": "tmdb", "source_id": "7", "season": "S01"}
    monkeypatch.setattr(module, "match_identity", AsyncMock(return_value=match))
    prepare = AsyncMock(side_effect=RuntimeError("temporary failure"))
    context = SimpleNamespace(subscriptions=SimpleNamespace(prepare_season=prepare), logger=Mock())
    row = {"title": "Fixture S02", "media_type": "tv"}
    result = asyncio.run(module.MaoyanWatchlistPlugin()._prepare_identity(context, row, {}))
    assert result == match
    assert prepare.call_args.args[0]["season"] == "S02"
    assert match["season"] == "S01"
    prepare.reset_mock()
    asyncio.run(module.MaoyanWatchlistPlugin()._prepare_identity(context, {**row, "media_type": "movie"}, {}))
    prepare.assert_not_awaited()
