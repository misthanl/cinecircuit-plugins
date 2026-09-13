import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cinecircuit_plugins.brush_flow.cleanup import check_downloads
from cinecircuit_plugins.brush_flow.plugin import SiteTrafficPlugin


@pytest.mark.parametrize("key,metric,limit,actual,expected", [
    ("delete_upload_gib", "uploaded_bytes", 2, 2 * 1024 ** 3, True),
    ("delete_upload_gib", "uploaded_bytes", 2, 2 * 1024 ** 3 - 1, False),
    ("delete_download_hours", "download_hours", 2, 2, True),
    ("delete_download_hours", "download_hours", 2, 1.9, False),
    ("delete_inactive_hours", "inactive_hours", 2, 2, True),
    ("delete_inactive_hours", "inactive_hours", 2, 1.9, False),
    ("delete_avg_upload_kib", "avg_upload_kib_s", 10, 0, True),
    ("delete_avg_upload_kib", "avg_upload_kib_s", 10, 10, False),
    ("delete_avg_upload_kib", "avg_upload_kib_s", 10, 11, False),
    ("delete_avg_upload_kib", "avg_upload_kib_s", 0, 0, False),
    ("delete_avg_upload_kib", "avg_upload_kib_s", 10, None, False),
    ("delete_avg_upload_kib", "avg_upload_kib_s", 10, float("nan"), False),
    ("delete_avg_upload_kib", "avg_upload_kib_s", 10, -1, False),
])
def test_new_rules_work_without_original_thresholds(key, metric, limit, actual, expected):
    ctx, rule, task = fixture()
    rule.pop("delete_ratio")
    rule[key] = limit
    task[metric] = actual
    summary = asyncio.run(check_downloads(ctx, [rule]))
    assert summary["deleted"] == int(expected)
    assert ctx.downloads.delete.await_count == int(expected)


class Items:
    def __init__(self, rows):
        self.rows = deepcopy(rows)

    def list(self, limit, *, offset=0, status=None):
        rows = [row for row in self.rows if not status or row["status"] == status]
        return deepcopy(rows[offset:offset + limit])

    def record(self, key, status, **values):
        row = next((row for row in self.rows if row["item_key"] == key), None)
        if row is None:
            row = {"item_key": key}
            self.rows.append(row)
        row.update(status=status, **values)


def fixture():
    receipt = dict(hash="a" * 40, downloader_id="d1", ownership_verified=True,
                   ownership_tag="owner-test", task_added_on=100, brush_task_id="r1")
    row = dict(item_key="one", status="added", result=receipt, payload={"title": "example"})
    task = dict(hash="a" * 40, downloader_id="d1", added_on=100, tags="app, owner-test",
                progress=100, ratio=2, seed_hours=48, paused=False)
    context = SimpleNamespace(config={"cleanup_enabled": True}, items=Items([row]),
        downloads=SimpleNamespace(task=AsyncMock(return_value=task),
                                  delete=AsyncMock(), pause=AsyncMock()))
    rule = dict(id="r1", enabled=True, delete_task=True, delete_ratio=2)
    return context, rule, task


@pytest.mark.parametrize("enabled,expiry,progress,tags,expected", [
    (True, "2000-01-01 00:00:00", 50, "", 1),
    (False, "2000-01-01 00:00:00", 50, "", 0),
    (True, "2099-01-01 00:00:00", 50, "", 0),
    (True, "", 50, "", 0),
    (True, "invalid", 50, "", 0),
    (True, "2000-01-01 00:00:00", 100, "", 0),
    (True, "2000-01-01 00:00:00", 50, ",H&R", 0),
    (True, "2000-01-01 00:00:00", 50, ",CineCircuit", 0),
])
def test_expired_promotion_only_deletes_unfinished_owned_unprotected_tasks(enabled, expiry, progress, tags, expected):
    ctx, rule, task = fixture()
    rule.pop("delete_ratio")
    rule["delete_expired_promotion"] = enabled
    task["progress"] = progress
    task["tags"] += tags
    ctx.items.rows[0]["payload"]["promotion_expires_at"] = expiry
    summary = asyncio.run(check_downloads(ctx, [rule]))
    assert summary["deleted"] == expected
    assert ctx.downloads.delete.await_count == expected


@pytest.mark.parametrize("tags", ["CineCircuit", "H&R", "CineCircuit,H&R", " cinecircuit ", "其他,H&R"])
def test_excluded_labels_prevent_deletion_and_pause(tags):
    ctx, rule, task = fixture()
    task["tags"] += "," + tags
    for delete in (True, False):
        rule["delete_task"] = delete
        summary = asyncio.run(check_downloads(ctx, [rule]))
        assert summary["deleted"] == summary["paused"] == 0
    ctx.downloads.delete.assert_not_awaited()
    ctx.downloads.pause.assert_not_awaited()


def test_exclusion_is_exact_and_can_be_customized_or_cleared():
    ctx, rule, task = fixture()
    task["tags"] += ",CineCircuit-backup"
    assert asyncio.run(check_downloads(ctx, [rule]))["deleted"] == 1
    ctx, rule, task = fixture()
    rule["exclude_tags"] = "app，other"
    assert asyncio.run(check_downloads(ctx, [rule]))["deleted"] == 0
    rule["exclude_tags"] = ""
    assert asyncio.run(check_downloads(ctx, [rule]))["deleted"] == 1


@pytest.mark.parametrize("config", [{}, {"cleanup_enabled": False}, {"cleanup_enabled": True, "enabled": False}])
def test_default_off(config):
    ctx, rule, _ = fixture()
    ctx.config = config
    assert asyncio.run(check_downloads(ctx, [rule]))["status"] == "disabled"
    ctx.downloads.task.assert_not_awaited()
    ctx.downloads.delete.assert_not_awaited()


@pytest.mark.parametrize("change", [
    {"progress": 99}, {"amount_left": 1}, {"ratio": None, "seed_hours": None}, {"hash": "b" * 40},
    {"downloader_id": "d2"}, {"added_on": 101}, {"added_on": 0}, {"tags": "app"},
])
def test_only_completed_matching_generation_is_actionable(change):
    ctx, rule, task = fixture()
    task.update(change)
    asyncio.run(check_downloads(ctx, [rule]))
    ctx.downloads.delete.assert_not_awaited()
    ctx.downloads.pause.assert_not_awaited()


@pytest.mark.parametrize("change", [{"ownership_verified": False}, {"brush_task_id": "other"},
                                    {"ownership_tag": ""}, {"task_added_on": None}])
def test_historical_or_foreign_receipts_are_not_adopted(change):
    ctx, rule, _ = fixture()
    ctx.items.rows[0]["result"].update(change)
    asyncio.run(check_downloads(ctx, [rule]))
    ctx.downloads.delete.assert_not_awaited()


@pytest.mark.parametrize("files", [False, True])
def test_deletes_once_and_files_require_explicit_option(files):
    ctx, rule, _ = fixture()
    ctx.config["allow_delete_files"] = files
    assert asyncio.run(check_downloads(ctx, [rule]))["deleted"] == 1
    asyncio.run(check_downloads(ctx, [rule]))
    ctx.downloads.delete.assert_awaited_once_with("d1", "a" * 40, delete_files=files)


def test_hours_or_ratio_and_pause_default():
    ctx, rule, task = fixture()
    rule.update(delete_task=False, delete_ratio=5, delete_seed_hours=48)
    task["ratio"] = 1
    assert asyncio.run(check_downloads(ctx, [rule]))["paused"] == 1
    ctx.downloads.pause.assert_awaited_once_with("d1", "a" * 40)
    ctx.downloads.delete.assert_not_awaited()


@pytest.mark.parametrize("rule_changes", [{"enabled": False}, {"delete_ratio": 0}])
def test_inactive_or_zero_rules_skip(rule_changes):
    ctx, rule, _ = fixture()
    rule.update(rule_changes)
    asyncio.run(check_downloads(ctx, [rule]))
    ctx.downloads.task.assert_not_awaited()


def test_reads_beyond_first_page_and_deduplicates():
    ctx, rule, _ = fixture()
    original = ctx.items.rows[0]
    ctx.items.rows = [dict(item_key=str(i), status="added", result={}) for i in range(501)]
    ctx.items.rows.extend([original, {**original, "item_key": "duplicate"}])
    assert asyncio.run(check_downloads(ctx, [rule]))["deleted"] == 1
    ctx.downloads.delete.assert_awaited_once()


def test_lookup_failure_is_recorded_and_next_task_continues():
    ctx, rule, task = fixture()
    second = deepcopy(ctx.items.rows[0])
    second["item_key"] = "two"
    second["result"]["hash"] = "b" * 40
    ctx.items.rows.append(second)
    ctx.downloads.task.side_effect = [TimeoutError("offline"), {**task, "hash": "b" * 40}]
    result = asyncio.run(check_downloads(ctx, [rule]))
    assert len(result["errors"]) == 1
    assert result["deleted"] == 1
    assert ctx.items.rows[0]["status"] == "added"


def test_missing_task_marked_without_delete():
    ctx, rule, _ = fixture()
    ctx.downloads.task.return_value = None
    asyncio.run(check_downloads(ctx, [rule]))
    assert ctx.items.rows[0]["status"] == "missing"
    ctx.downloads.delete.assert_not_awaited()


def test_scheduled_run_checks_cleanup_and_old_host_is_safe():
    ctx, rule, _ = fixture()
    ctx.config["tasks"] = [rule]
    plugin = SiteTrafficPlugin()
    plugin._run_tasks = AsyncMock(return_value={"added": 0})
    assert asyncio.run(plugin.run(ctx))["cleanup"]["deleted"] == 1
    del ctx.downloads.task
    assert asyncio.run(check_downloads(ctx, [rule]))["status"] == "unsupported"
    fields = {field["key"]: field for field in plugin.manifest.config_schema["fields"]}
    assert fields["cleanup_enabled"]["default"] is False
    assert plugin.manifest.version == "1.0.0"


def test_preview_uses_latest_and_inherits_default_site():
    sites = SimpleNamespace(latest=AsyncMock(return_value={"items": [{"id": "1", "title": "WEB", "size": 1024}]}), feed=AsyncMock())
    context = SimpleNamespace(config={"default_site_id": "site-default"}, sites=sites)
    request = SimpleNamespace(action="preview", method="POST", payload={"include": "WEB", "promotion": "all"})
    result = asyncio.run(SiteTrafficPlugin().handle_api(request, context))
    assert result["count"] == 1
    sites.latest.assert_awaited_once_with("site-default", limit=100)
    sites.feed.assert_not_awaited()


def test_old_host_keeps_rss_selection():
    sites = SimpleNamespace(feed=AsyncMock(return_value={"items": []}))
    assert asyncio.run(SiteTrafficPlugin._latest(sites, "site", limit=20)) == {"items": []}
    sites.feed.assert_awaited_once_with("site", limit=20)


@pytest.mark.parametrize("item", [
    {"size": 2 * 1024**3},
    {"size": "2.00 GB", "size_bytes": 2 * 1024**3},
    {"size": "--", "size_bytes": 0},
])
def test_selection_accepts_rss_bytes_and_pt_display_size(item):
    assert SiteTrafficPlugin._matches(item, {"promotion": "all"})
    assert SiteTrafficPlugin._matches(item, {"promotion": "all", "min_size": 1}) == (item.get("size_bytes", item["size"]) != 0)
    assert not SiteTrafficPlugin._matches(item, {"promotion": "all", "min_size": 3})


def test_brush_has_no_navigation_or_menu_switch():
    manifest = SiteTrafficPlugin.manifest
    assert not manifest.navigation
    assert "plugin_page" not in manifest.capabilities
    fields = {field["key"]: field for field in manifest.config_schema["fields"]}
    assert "show_sidebar_nav" not in fields
    assert fields["enabled"]["default"] is True


def test_statistics_failure_is_observable_without_blocking_owned_cleanup(monkeypatch, caplog):
    from cinecircuit_plugins.brush_flow import statistics

    def fail_capture(*args):
        raise RuntimeError("secret-url-token")

    monkeypatch.setattr(statistics, "capture", fail_capture)
    ctx, rule, _ = fixture()
    summary = asyncio.run(check_downloads(ctx, [rule]))
    assert summary["deleted"] == 1
    ctx.downloads.delete.assert_awaited_once()
    assert "statistics capture failed" in caplog.text
    assert "secret-url-token" not in caplog.text
