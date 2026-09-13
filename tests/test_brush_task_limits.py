import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from cinecircuit_plugins.brush_flow.task_limits import volume_remaining, transfer_limits
from cinecircuit_plugins.brush_flow.plugin import SiteTrafficPlugin
from test_brush_flow_cleanup import fixture


@pytest.mark.parametrize("progress", [10, 100])
def test_volume_counts_current_generation_only(progress):
    ctx, rule, task = fixture()
    rule["seeding_limit_gib"] = 10
    task.update(size=4 * 1024**3, progress=progress)
    assert asyncio.run(volume_remaining(ctx, rule, [task, task])) == 6 * 1024**3
    assert asyncio.run(volume_remaining(ctx, rule, [{**task, "added_on": 101}])) == 10 * 1024**3
    assert asyncio.run(volume_remaining(ctx, {**rule, "id": "another"}, [task])) == 10 * 1024**3
    assert asyncio.run(volume_remaining(ctx, rule, [{**task, "size": None}])) == 0


def test_unlimited_needs_no_history():
    assert asyncio.run(volume_remaining(None, {}, [])) is None
    assert transfer_limits({}) == {}


def test_volume_reserves_each_add_and_skips_oversized(monkeypatch):
    from cinecircuit_plugins.brush_flow import plugin
    monkeypatch.setattr(plugin, "load_index", AsyncMock(return_value=None))
    sizes = [12, 6, 5, 4]
    candidates = [{"id": str(n), "size": size * 1024**3} for n, size in enumerate(sizes)]
    sites = SimpleNamespace(latest=AsyncMock(return_value={"items": candidates}))
    ctx = SimpleNamespace(config={}, downloads=SimpleNamespace(list_tasks=AsyncMock(return_value={"items": []})), items=SimpleNamespace(list=lambda *a, **kw: [], get=lambda _: None))
    host = SiteTrafficPlugin()
    monkeypatch.setattr(host, "_site_actions", lambda _: sites)
    monkeypatch.setattr(host, "_matches", lambda *a: True)
    monkeypatch.setattr(host, "_notify_tasks", AsyncMock())
    add = AsyncMock(return_value=True)
    monkeypatch.setattr(host, "_add_candidate", add)
    rule = {"id": "r", "name": "r", "site_id": "s", "seeding_limit_gib": 10, "max_add": 3}
    result = asyncio.run(host._run_tasks(ctx, [rule]))
    assert result["added"] == 2
    assert [call.args[4]["size"] for call in add.await_args_list] == [6 * 1024**3, 4 * 1024**3]


@pytest.mark.parametrize("secure", [True, False])
def test_limits_forwarded_to_dispatch(secure):
    dispatch = AsyncMock(return_value={"status": "queued"})
    ctx = SimpleNamespace(downloads=SimpleNamespace(add=dispatch), items=SimpleNamespace(record=Mock()))
    sites = SimpleNamespace(dispatch=dispatch) if secure else SimpleNamespace()
    task = {"id": "r", "upload_limit_kib": 100, "download_limit_kib": 200}
    assert asyncio.run(SiteTrafficPlugin._add_candidate(ctx, sites, "s", task, {"id": "i"}, "key"))
    values = dispatch.call_args.kwargs if secure else dispatch.call_args.args[0]
    assert values["upload_limit_kib"] == 100 and values["download_limit_kib"] == 200


def test_volume_queries_owned_torrent_missing_from_overview():
    ctx, rule, task = fixture()
    rule["seeding_limit_gib"] = 10
    task["size"] = 8 * 1024**3
    assert asyncio.run(volume_remaining(ctx, rule, [])) == 2 * 1024**3
    ctx.downloads.task.assert_awaited_once()
    ctx.downloads.task.side_effect = RuntimeError("offline")
    assert asyncio.run(volume_remaining(ctx, rule, [])) == 0
