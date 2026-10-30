import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cinecircuit_plugins.brush_flow.notifications import notify_outcomes, notify_cleanup
from cinecircuit_plugins.brush_flow.plugin import SiteTrafficPlugin
from cinecircuit_plugins.brush_flow import plugin
from test_brush_flow_cleanup import fixture


def context():
    saved = {}
    state = SimpleNamespace(get=saved.get, set=lambda k, v: saved.update({k: v}))
    return SimpleNamespace(config={"notification_enabled": False}, trigger="scheduled",
        state=SimpleNamespace(scoped=lambda _: state),
        notifications=SimpleNamespace(send=AsyncMock(return_value={"results": [{"success": True}]})))


def test_task_switch_is_only_control_and_global_field_is_removed():
    ctx = context()
    tasks = [{"id": "one", "notification_enabled": True}]
    asyncio.run(notify_outcomes(ctx, tasks, [{"task_id": "one", "added": 1}]))
    ctx.notifications.send.assert_awaited_once()
    fields = SiteTrafficPlugin.manifest.config_schema["fields"]
    assert not any(row["key"] == "notification_enabled" for row in fields)
    defaults = SiteTrafficPlugin._tasks({"notification_enabled": True, "tasks": [{"id": "one"}]})
    assert defaults[0]["notification_enabled"] is False


def test_scheduled_limits_notify_once_until_recovery_manual_always_notifies():
    ctx = context()
    tasks = [{"id": "one", "notification_enabled": True}]
    blocked = [{"task_id": "one", "reason": "达到体积上限"}]
    for _ in range(2):
        asyncio.run(notify_outcomes(ctx, tasks, blocked))
    assert ctx.notifications.send.await_count == 1
    asyncio.run(notify_outcomes(ctx, tasks, [{"task_id": "one", "added": 1}]))
    asyncio.run(notify_outcomes(ctx, tasks, blocked))
    assert ctx.notifications.send.await_count == 3
    ctx.trigger = "manual"
    asyncio.run(notify_outcomes(ctx, tasks, blocked))
    assert ctx.notifications.send.await_count == 4


def test_failed_delivery_does_not_suppress_later_limit_notice():
    ctx = context()
    ctx.notifications.send.return_value = {"results": [], "skipped": True}
    tasks = [{"id": "one", "notification_enabled": True}]
    blocked = [{"task_id": "one", "reason": "达到任务数量上限"}]
    for _ in range(2):
        asyncio.run(notify_outcomes(ctx, tasks, blocked))
    assert ctx.notifications.send.await_count == 2


def test_cleanup_only_notifies_tasks_with_actual_actions_or_errors():
    ctx = context()
    tasks = [{"id": "on", "notification_enabled": True}, {"id": "off", "notification_enabled": False}]
    asyncio.run(notify_cleanup(ctx, tasks, {"checked": 10, "skipped": 10}))
    ctx.notifications.send.assert_not_awaited()
    asyncio.run(notify_cleanup(ctx, tasks, {"task_results": {"on": {"deleted": 2}, "off": {"failed": 1}}}))
    ctx.notifications.send.assert_awaited_once()
    assert "删除 2 个" in ctx.notifications.send.call_args.args[1]


def test_cleanup_deletion_reports_actual_task():
    ctx, rule, _ = fixture()
    rule["notification_enabled"] = True
    ctx.notifications = SimpleNamespace(send=AsyncMock())
    result = asyncio.run(plugin.check_downloads(ctx, [rule]))
    assert result["deleted"] == 1
    ctx.notifications.send.assert_awaited_once()
    assert "删除 1 个" in ctx.notifications.send.call_args.args[1]


def test_preflight_failure_notifies_without_masking_original_exception(monkeypatch):
    ctx = context()
    ctx.notifications.send.side_effect = RuntimeError("delivery error")
    monkeypatch.setattr(plugin, "owned_downloads", AsyncMock(side_effect=ValueError("original failure")))
    with pytest.raises(ValueError, match="original failure"):
        asyncio.run(SiteTrafficPlugin()._run_tasks(ctx, [{"id": "one", "notification_enabled": True}]))
    ctx.notifications.send.assert_awaited_once()
    assert "original failure" not in str(ctx.notifications.send.call_args)


def test_site_failure_notifies_before_reraising(monkeypatch):
    ctx = context()
    monkeypatch.setattr(plugin, "owned_downloads", AsyncMock(return_value=[]))
    monkeypatch.setattr(plugin, "load_index", AsyncMock(return_value=None))
    worker = SiteTrafficPlugin()
    worker._run_task = AsyncMock(side_effect=ValueError("private URL"))
    with pytest.raises(ValueError, match="private URL"):
        asyncio.run(worker._run_tasks(ctx, [{"id": "one", "notification_enabled": True}]))
    assert "站点读取" in ctx.notifications.send.call_args.args[1]
    assert "private URL" not in str(ctx.notifications.send.call_args)
