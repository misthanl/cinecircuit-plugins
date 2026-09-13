import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cinecircuit_plugins.brush_flow.statistics import build_statistics, capture, record_execution
from test_brush_flow_cleanup import Items


class State:
    def __init__(self):
        self.values = {}

    def scoped(self, name):
        return self

    def get(self, key, default=None):
        return deepcopy(self.values.get(key, default))

    def set(self, key, value):
        self.values[key] = deepcopy(value)


def fixture():
    receipt = dict(hash="abc", downloader_id="d1", ownership_verified=True, ownership_tag="owned", task_added_on=100, brush_task_id="r1")
    ctx = SimpleNamespace(config={}, state=State(), items=Items([dict(item_key="one", status="added", result=receipt)]), downloads=SimpleNamespace(task=AsyncMock()))
    task = dict(hash="abc", downloader_id="d1", added_on=100, tags="owned", progress=100, uploaded_bytes=2048, downloaded=1024, upload_speed=20, download_speed=0, size=1024)
    ctx.downloads.task.return_value = task
    rules = [dict(id="r1", name="First", site_id="s1", enabled=True)]
    return ctx, receipt, task, rules


def test_only_verified_owned_generation_counts_and_refresh_does_not_double_count():
    ctx, receipt, task, rules = fixture()
    ctx.items.rows.extend([dict(item_key="duplicate", status="added", result=receipt), dict(item_key="unknown", status="added", result={**receipt, "ownership_verified": False})])
    for _ in range(2):
        row = asyncio.run(build_statistics(ctx, rules))["tasks"][0]
        assert row["uploaded"] == 2048 and row["downloaded"] == 1024
        assert row["seed_count"] == 1 and row["size"] == 1024
    assert ctx.downloads.task.await_count == 2


def test_deleted_task_keeps_last_observed_traffic_and_no_live_usage():
    ctx, receipt, task, rules = fixture()
    capture(ctx, receipt, task)
    ctx.items.rows[0]["status"] = "deleted"
    row = asyncio.run(build_statistics(ctx, rules))["tasks"][0]
    assert row["uploaded"] == 2048 and row["downloaded"] == 1024
    assert row["size"] == 0 and row["seed_count"] == 0
    ctx.downloads.task.assert_not_awaited()


def test_generation_mismatch_does_not_attribute_another_download():
    ctx, receipt, task, rules = fixture()
    ctx.downloads.task.return_value = {**task, "hash": "different"}
    row = asyncio.run(build_statistics(ctx, rules))["tasks"][0]
    assert row["size"] == 0 and not row["history_complete"]


def test_offline_and_old_unobserved_records_are_not_reported_as_complete_zero():
    ctx, receipt, task, rules = fixture()
    ctx.downloads.task.side_effect = RuntimeError("secret")
    result = asyncio.run(build_statistics(ctx, rules))
    assert not result["tasks"][0]["available"]
    assert not result["tasks"][0]["history_complete"]
    assert "secret" not in str(result)


def test_counter_reset_does_not_reduce_cumulative_snapshot():
    ctx, receipt, task, rules = fixture()
    capture(ctx, receipt, task)
    assert capture(ctx, receipt, {**task, "uploaded_bytes": 100})["uploaded"] == 2048


def test_execution_history_keeps_counts_and_limit_reason(monkeypatch):
    timestamps = iter([100, 101, 102])
    monkeypatch.setattr("cinecircuit_plugins.brush_flow.statistics.time", lambda: next(timestamps))
    ctx, receipt, task, rules = fixture()
    record_execution(ctx, rules[0], reason="达到体积上限")
    record_execution(ctx, rules[0], added=2, failed=1, skipped=8, matched=11, reason="部分失败")
    report = asyncio.run(build_statistics(ctx, rules))
    assert len(report["history"]) == 2
    assert report["history"][0]["failed"] == 1
    assert report["history"][1]["reason"] == "达到体积上限"
