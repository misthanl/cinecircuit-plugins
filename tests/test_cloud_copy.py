import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from cinecircuit_plugins.cloud_copy import CloudCopyPlugin


class State:
    def __init__(self):
        self.values = {}

    def scoped(self, namespace):
        return self

    def get(self, key, default=None):
        return copy.deepcopy(self.values.get(key, default))

    def set(self, key, value):
        self.values[key] = copy.deepcopy(value)

    def list(self, *, prefix="", limit=100, after=""):
        return [{"key": key, "value": copy.deepcopy(value)} for key, value in sorted(self.values.items())
                if key.startswith(prefix) and key > after][:limit]


def context(source, target):
    gateway = SimpleNamespace(
        configurations=AsyncMock(return_value={"items": [
            {"id": source, "name": "Source", "enabled": True, "capabilities": ["file_copy_source", "change_feed"]},
            {"id": target, "name": "Target", "enabled": True, "capabilities": ["file_copy_target"]},
        ]}),
        acknowledge_changes=AsyncMock(),
        same_account=AsyncMock(return_value=False),
        file_page=AsyncMock(
            return_value={
                "items": [
                    {
                        "file_id": "file",
                        "name": "movie.mkv",
                        "directory": False,
                        "size": 10,
                        "checksums": {"md5": "abc"},
                    }
                ],
                "cursor": None,
            }
        ),
        ensure_directory=AsyncMock(return_value="folder"),
        copy_file=AsyncMock(
            return_value={"status": "completed", "file_id": "copy", "method": "rapid"}
        ),
        changes=AsyncMock(return_value={"supported": False}),
    )
    return SimpleNamespace(
        config={"source": source, "target": target, "target_root": "destination", "enabled": True},
        trigger="manual",
        sdk=Mock(require=Mock(return_value=gateway)),
        state=State(),
    )


@pytest.mark.parametrize("source", ["115", "123", "guangya"])
@pytest.mark.parametrize("target", ["115", "123", "guangya"])
def test_all_directions_use_the_same_sdk_and_dedupe(source, target):
    ctx = context(source, target)
    plugin = CloudCopyPlugin()
    asyncio.run(plugin.run(ctx))
    asyncio.run(plugin.run(ctx))
    gateway = ctx.sdk.require.return_value
    assert gateway.copy_file.await_count == 1
    assert gateway.copy_file.call_args.args[:4] == (source, "file", target, "destination")


def test_uncertain_remote_result_is_not_blindly_replayed():
    ctx = context("source", "target")
    gateway = ctx.sdk.require.return_value
    gateway.copy_file.side_effect = TimeoutError()
    plugin = CloudCopyPlugin()
    with pytest.raises(TimeoutError):
        asyncio.run(plugin.run(ctx))
    asyncio.run(plugin.run(ctx))
    assert gateway.copy_file.await_count == 1
    assert any(
        row.get("status") == "uncertain"
        for key, value in ctx.state.values.items()
        if key.startswith("records-")
        for row in value.values()
    )


def test_scan_failure_does_not_mark_completion():
    ctx = context("source", "target")
    ctx.sdk.require.return_value.file_page.side_effect = RuntimeError("incomplete page")
    with pytest.raises(RuntimeError):
        asyncio.run(CloudCopyPlugin().run(ctx))
    ctx.sdk.require.return_value.copy_file.assert_not_called()


def test_failed_handoff_retries_without_copying_again():
    ctx = context("source", "target")
    ctx.config["followup"] = "sync"
    gateway = ctx.sdk.require.return_value
    gateway.handoff_copy = AsyncMock(
        side_effect=[RuntimeError("temporary"), {"status": "completed"}]
    )
    plugin = CloudCopyPlugin()
    with pytest.raises(RuntimeError):
        asyncio.run(plugin.run(ctx))
    asyncio.run(plugin.run(ctx))
    assert gateway.copy_file.await_count == 1
    assert gateway.handoff_copy.await_count == 2


def test_completion_event_does_not_bypass_selected_triggers():
    ctx = context("source", "target")
    ctx.trigger = "event"
    gateway = ctx.sdk.require.return_value
    gateway.completion_file_ids = AsyncMock(return_value=["file"])
    gateway.file_relative_to = AsyncMock(return_value={"file_id": "file", "relative_path": "a.mkv"})
    event = SimpleNamespace(
        data={
            "storage_uid": "source",
            "items": [{"media_path": "a.strm"}],
            "generated_strm_count": 1,
        }
    )
    asyncio.run(CloudCopyPlugin().on_event(event, ctx))
    assert "progress" not in ctx.state.values
    gateway.file_page.assert_not_called()
    gateway.copy_file.assert_not_called()


def test_manual_batch_continues_when_automatic_rules_are_off():
    ctx = context("source", "target")
    ctx.config["enabled"] = False
    gateway = ctx.sdk.require.return_value
    gateway.file_page.return_value = {
        "items": [
            {
                "file_id": str(i),
                "name": f"{i}.mkv",
                "directory": False,
                "size": 10,
                "checksums": {"md5": str(i)},
            }
            for i in range(25)
        ],
        "cursor": None,
    }
    plugin = CloudCopyPlugin()
    asyncio.run(plugin.run(ctx))
    assert gateway.copy_file.await_count == 20
    ctx.trigger = "scheduled"
    asyncio.run(plugin.run(ctx))
    assert gateway.copy_file.await_count == 25
    assert not ctx.state.get("progress")["manual_active"]
    asyncio.run(plugin.run(ctx))
    assert gateway.copy_file.await_count == 25


def test_uncertain_alternate_name_is_persisted_for_reconciliation():
    ctx = context("source", "target")
    gateway = ctx.sdk.require.return_value
    gateway.copy_file.side_effect = [{"status": "conflict"}, TimeoutError()]
    plugin = CloudCopyPlugin()
    with pytest.raises(TimeoutError):
        asyncio.run(plugin.run(ctx))
    key = next(k for k in ctx.state.values if k.startswith("records-"))
    identity, record = next(iter(ctx.state.values[key].items()))
    alternate = record["target_name"]
    assert "[" in alternate
    request = SimpleNamespace(action="retry", method="POST", payload={"identity": identity})
    asyncio.run(plugin.handle_api(request, ctx))
    gateway.copy_file.side_effect = None
    gateway.copy_file.return_value = {
        "status": "completed",
        "file_id": "existing",
        "method": "existing",
    }
    asyncio.run(plugin.run(ctx))
    assert gateway.copy_file.call_args.args[4] == alternate


def test_scan_visits_children_before_loading_more_parent_pages():
    ctx = context("source", "target")
    gateway = ctx.sdk.require.return_value
    gateway.file_page.return_value = {"items": [{"file_id": "child", "name": "Child", "directory": True}], "cursor": "next"}
    progress = {"folders": [{"id": "root", "prefix": "", "cursor": None}], "pending": []}
    asyncio.run(CloudCopyPlugin().scan_page(gateway, ctx.state, progress, "source", "target", "destination", False))
    assert [row["id"] for row in progress["folders"]] == ["child", "root"]
    assert progress["folders"][1]["cursor"] == "next"


@pytest.mark.parametrize("source,target", [("", ""), ("source", "")])
def test_unconfigured_statistics_returns_empty_state(source, target):
    ctx = context(source, target)
    request = SimpleNamespace(action="status", method="GET", query={})
    result = asyncio.run(CloudCopyPlugin().handle_api(request, ctx))
    assert result["configured"] is False
    assert result["records"] == []
    assert result["next_cursor"] is None
    assert result["configuration_message"]
    ctx.sdk.require.assert_not_called()


def test_unconfigured_rescan_still_requires_configuration():
    ctx = context("", "")
    with pytest.raises(ValueError):
        asyncio.run(CloudCopyPlugin().handle_api(
            SimpleNamespace(action="rescan", method="POST"), ctx,
        ))


def test_default_and_legacy_interval_never_trigger_automatic_full_scan():
    ctx = context("source", "target")
    ctx.trigger = "scheduled"
    ctx.config["rescan_hours"] = 24
    result = asyncio.run(CloudCopyPlugin().run(ctx))
    assert result["reason"] == "no_trigger"
    ctx.sdk.require.return_value.file_page.assert_not_called()
    ctx.sdk.require.return_value.changes.assert_not_called()


def test_interval_scan_waits_default_60_minutes_and_repeats(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from cinecircuit_plugins.cloud_copy import schedule
    timestamp = datetime(2026, 9, 14, 2, 59, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
    clock = [timestamp]
    monkeypatch.setattr(schedule.time, "time", lambda: clock[0])
    ctx = context("source", "target")
    ctx.trigger = "scheduled"
    ctx.config.update(full_scan_enabled=True, life_events_enabled=True)
    plugin = CloudCopyPlugin()
    asyncio.run(plugin.run(ctx))
    ctx.sdk.require.return_value.file_page.assert_not_called()
    clock[0] += 3600
    asyncio.run(plugin.run(ctx))
    assert ctx.sdk.require.return_value.file_page.await_count == 1
    clock[0] += 60
    asyncio.run(plugin.run(ctx))
    assert ctx.sdk.require.return_value.file_page.await_count == 1
    ctx.sdk.require.return_value.changes.assert_not_called()


def test_event_mode_filters_history_without_initial_full_scan():
    ctx = context("source", "target")
    ctx.trigger = "scheduled"
    ctx.config.update(life_events_enabled=True, life_events_since=100)
    gateway = ctx.sdk.require.return_value
    gateway.changes.return_value = {"supported": True, "events": [
        {"file_id": "old", "event_time": 99}, {"file_id": "new", "event_time": 101},
    ]}
    gateway.file_relative_to = AsyncMock(return_value={"file_id": "new", "relative_path": "new.mkv"})
    asyncio.run(CloudCopyPlugin().run(ctx))
    gateway.file_page.assert_not_called()
    gateway.file_relative_to.assert_awaited_once_with("source", "0", "new")
    gateway.acknowledge_changes.assert_awaited_once()
    assert gateway.copy_file.await_count == 1


def test_unsupported_source_cannot_enable_events_even_with_forged_config():
    ctx = context("source", "target")
    ctx.trigger = "scheduled"
    ctx.config.update(life_events_enabled=True)
    gateway = ctx.sdk.require.return_value
    gateway.configurations.return_value["items"][0]["capabilities"] = ["file_copy_source"]
    assert asyncio.run(CloudCopyPlugin().run(ctx))["reason"] == "no_trigger"
    gateway.changes.assert_not_called()
    gateway.file_page.assert_not_called()


def test_directory_event_scans_only_affected_subtree():
    ctx = context("source", "target")
    ctx.trigger = "scheduled"
    ctx.config.update(life_events_enabled=True, life_events_since=100)
    gateway = ctx.sdk.require.return_value
    gateway.changes.return_value = {"supported": True, "events": [{"file_id": "sub", "event_time": 101, "is_dir": True}]}
    gateway.file_relative_to = AsyncMock(return_value={"file_id": "sub", "relative_path": "Movies/Sub"})
    asyncio.run(CloudCopyPlugin().run(ctx))
    gateway.file_page.assert_awaited_once_with("source", "sub", None)


def test_statistics_counts_are_global_and_filters_page_individual_files():
    ctx = context("source", "target")
    ctx.state.set("records-aaa", {str(i): {"path": f"movie-{i:02}.mkv", "status": "completed" if i < 10 else "conflict", "method": "rapid", "updated_at": i} for i in range(12)})
    request = SimpleNamespace(action="status", query={"page": "2", "status": "completed"})
    result = asyncio.run(CloudCopyPlugin().handle_api(request, ctx))
    assert result["counts"]["completed"] == 10
    assert result["counts"]["attention"] == 2
    assert result["total"] == 10
    assert len(result["records"]) == 2
    assert result["records"][0]["source_name"] == "Source"
    assert result["records"][0]["target_storage_name"] == "Target"
    ctx.sdk.require.return_value.file_page.assert_not_called()


def test_invalid_schedule_is_rejected_without_copying():
    ctx = context("source", "target")
    ctx.config.update(full_scan_enabled=True, full_scan_interval_minutes=0)
    with pytest.raises(ValueError, match="整数分钟"):
        asyncio.run(CloudCopyPlugin().run(ctx))
    ctx.sdk.require.return_value.copy_file.assert_not_called()


def test_partial_configuration_does_not_fail_background_poll():
    ctx = context("source", "")
    ctx.trigger = "scheduled"
    assert asyncio.run(CloudCopyPlugin().run(ctx))["status"] == "skipped"
    ctx.sdk.require.assert_not_called()


def test_interval_change_reschedules_and_pause_preserves_due():
    from cinecircuit_plugins.cloud_copy.schedule import prepare_interval_scan
    ctx = context("source", "target")
    progress = {}
    config = {"full_scan_enabled": True, "full_scan_interval_minutes": 5}
    prepare_interval_scan(config, ctx.state, progress, 1000)
    assert progress["next_full_scan"] == 1300
    prepare_interval_scan(config, ctx.state, progress, 1299)
    assert not ctx.state.get("rescan_requested", False)
    ctx.state.set("paused", True)
    prepare_interval_scan(config, ctx.state, progress, 1400)
    assert not ctx.state.get("rescan_requested", False)
    ctx.state.set("paused", False)
    prepare_interval_scan(config, ctx.state, progress, 1500)
    assert ctx.state.get("rescan_requested")
    assert progress["next_full_scan"] == 1800
    config["full_scan_interval_minutes"] = 10
    prepare_interval_scan(config, ctx.state, progress, 1501)
    assert progress["next_full_scan"] == 2101
    config["full_scan_enabled"] = False
    prepare_interval_scan(config, ctx.state, progress, 1502)
    assert "next_full_scan" not in progress
