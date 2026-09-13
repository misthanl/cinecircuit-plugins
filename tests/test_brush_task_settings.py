import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import datetime
from zoneinfo import ZoneInfo

from cinecircuit_plugins.brush_flow import task_settings
from cinecircuit_plugins.brush_flow.plugin import SiteTrafficPlugin
from cinecircuit_plugins.brush_flow.cleanup import check_downloads
from test_brush_flow_cleanup import fixture


@pytest.mark.parametrize("period,hour,minute,allowed", [
    ("", 12, 0, True), ("00:00-08:00", 0, 0, True),
    ("00:00-08:00", 7, 59, True), ("00:00-08:00", 8, 0, False),
    ("22:00-08:00", 23, 0, True), ("22:00-08:00", 1, 0, True),
    ("22:00-08:00", 12, 0, False),
])
def test_intake_time_boundaries(period, hour, minute, allowed):
    now = datetime(2026, 9, 11, hour, minute, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
    assert task_settings.intake_allowed({"intake_time_range": period}, now) is allowed


@pytest.mark.parametrize("period", ["24:00-08:00", "00:60-08:00", "8:00-9:00", "00:00-00:00"])
def test_invalid_intake_time_rejected(period):
    with pytest.raises(ValueError):
        task_settings.intake_allowed({"intake_time_range": period})


def test_outside_intake_window_skips_reads_but_keeps_cleanup(monkeypatch):
    from cinecircuit_plugins.brush_flow import plugin
    monkeypatch.setattr(plugin, "intake_allowed", lambda task: False)
    cleanup = AsyncMock(return_value={"checked": 1})
    monkeypatch.setattr(plugin, "check_downloads", cleanup)
    ctx = SimpleNamespace(config={"tasks": [{"id": "a", "intake_time_range": "00:00-08:00"}]})
    result = asyncio.run(SiteTrafficPlugin().run(ctx))
    cleanup.assert_awaited_once()
    assert result["added"] == 0


def test_removed_cleanup_switches_are_enabled_while_other_settings_inherit():
    tasks = SiteTrafficPlugin._tasks(dict(cleanup_enabled=True, allow_delete_files=True,
        default_site_id="s1", notification_enabled=True, cron="0 3 * * *",
        tasks=[dict(id="one", allow_delete_files=False), dict(id="two")]))
    assert tasks[0]["allow_delete_files"] is True
    assert all(task["cleanup_enabled"] and task["delete_task"] for task in tasks)
    assert tasks[1]["allow_delete_files"] is True
    assert tasks[0]["cleanup_enabled"] is True
    assert tasks[1]["cron"] == "0 3 * * *"
    assert tasks[1]["site_id"] == "s1"


def test_task_delete_permission_overrides_global_without_touching_other_tasks():
    ctx, rule, _ = fixture()
    ctx.config.update(cleanup_enabled=False, allow_delete_files=True)
    rule.update(cleanup_enabled=True, allow_delete_files=False)
    assert asyncio.run(check_downloads(ctx, [rule]))["deleted"] == 1
    assert ctx.downloads.delete.call_args.kwargs["delete_files"] is False


def test_disabled_task_cleanup_never_queries_downloader():
    ctx, rule, _ = fixture()
    rule["cleanup_enabled"] = False
    assert asyncio.run(check_downloads(ctx, [rule]))["status"] == "disabled"
    ctx.downloads.task.assert_not_awaited()


def test_independent_task_cadences_and_no_double_execution(monkeypatch):
    saved = {}
    state = SimpleNamespace(scoped=lambda _: SimpleNamespace(get=lambda k, d: saved.get(k, d), set=lambda k, v: saved.update({k: v})))
    ctx = SimpleNamespace(trigger="scheduled", state=state)
    tasks = [dict(id="a", interval_minutes=5), dict(id="b", interval_minutes=15)]
    monkeypatch.setattr(task_settings, "time", lambda: 10000)
    assert len(task_settings.due_tasks(ctx, tasks)) == 2
    assert task_settings.due_tasks(ctx, tasks) == []
    monkeypatch.setattr(task_settings, "time", lambda: 10301)
    assert [r["id"] for r in task_settings.due_tasks(ctx, tasks)] == ["a"]


def test_legacy_cron_keeps_beijing_schedule():
    at = datetime(2026, 9, 10, 3, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
    assert task_settings.cron_matches("0 3 * * *", at)
    assert not task_settings.cron_matches("0 3 * * *", at + 60)


def test_refresh_and_check_keep_independent_persisted_clocks(monkeypatch):
    saved = {}
    def scoped(scope):
        bucket = saved.setdefault(scope, {})
        return SimpleNamespace(get=lambda key, default: bucket.get(key, default),
                               set=lambda key, value: bucket.update({key: value}))
    ctx = SimpleNamespace(trigger="scheduled", state=SimpleNamespace(scoped=scoped))
    tasks = [dict(id="a", interval_minutes=10, check_interval_minutes=2)]
    monkeypatch.setattr(task_settings, "time", lambda: 10000)
    assert task_settings.due_tasks(ctx, tasks) == tasks
    assert task_settings.due_tasks(ctx, tasks, check=True) == tasks
    monkeypatch.setattr(task_settings, "time", lambda: 10120)
    assert task_settings.due_tasks(ctx, tasks) == []
    assert task_settings.due_tasks(ctx, tasks, check=True) == tasks
    assert task_settings.due_tasks(ctx, tasks, check=True) == []
    monkeypatch.setattr(task_settings, "time", lambda: 10600)
    assert task_settings.due_tasks(ctx, tasks) == tasks


def test_check_ignores_intake_cron_and_time_window(monkeypatch):
    ctx = SimpleNamespace(trigger="scheduled", state=SimpleNamespace(
        scoped=lambda _: SimpleNamespace(get=lambda *args: 0, set=lambda *args: None)))
    now = datetime(2026, 9, 11, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
    monkeypatch.setattr(task_settings, "time", lambda: now)
    tasks = [dict(id="a", cron="0 3 * * *", intake_time_range="00:00-08:00")]
    assert task_settings.due_tasks(ctx, tasks) == []
    assert task_settings.due_tasks(ctx, tasks, check=True) == tasks


def test_no_due_tasks_does_not_query_downloaders():
    ctx = SimpleNamespace(downloads=SimpleNamespace(list_tasks=AsyncMock()))
    assert asyncio.run(SiteTrafficPlugin()._run_tasks(ctx, []))["tasks"] == 0
    ctx.downloads.list_tasks.assert_not_awaited()


def test_task_capacity_counts_only_its_owned_download_generation():
    ctx, rule, task = fixture()
    rule["task_limit"] = 1
    assert task_settings.task_capacity(ctx, rule, [task]) == 0
    assert task_settings.task_capacity(ctx, {**rule, "id": "another"}, [task]) == 1
    assert task_settings.task_capacity(ctx, rule, [{**task, "added_on": 101}]) == 1


def test_notifications_follow_result_task_id_after_other_task_is_skipped():
    ctx = SimpleNamespace(config={}, notifications=SimpleNamespace(send=AsyncMock()))
    tasks = [dict(id="full", name="Full", notification_enabled=True),
             dict(id="run", name="Running", notification_enabled=False)]
    results = [dict(task_id="run", matched=2, added=1)]
    asyncio.run(SiteTrafficPlugin._notify_tasks(ctx, tasks, results))
    ctx.notifications.send.assert_not_awaited()
    tasks[1]["notification_enabled"] = True
    asyncio.run(SiteTrafficPlugin._notify_tasks(ctx, tasks, results))
    assert ctx.notifications.send.call_args.args[0].endswith("Running")
