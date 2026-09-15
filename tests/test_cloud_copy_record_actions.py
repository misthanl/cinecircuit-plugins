import asyncio
from types import SimpleNamespace

import pytest

from cinecircuit_plugins.cloud_copy import CloudCopyPlugin
from test_cloud_copy_manual import setup, request


def call(plugin, ctx, action, **payload):
    return asyncio.run(
        plugin.handle_api(
            SimpleNamespace(
                action=action,
                method="GET" if action == "status" else "POST",
                payload=payload,
                query=payload,
            ),
            ctx,
        )
    )


def completed_batch(status="completed"):
    ctx, gateway = setup()
    gateway.copy_file.return_value = {"status": status, "method": "rapid", "file_id": "target-file"}
    plugin = CloudCopyPlugin()
    task = asyncio.run(plugin.handle_api(request(), ctx))
    asyncio.run(plugin.run(ctx))
    return ctx, gateway, plugin, task


def test_manual_statistics_without_rule_and_origin_filter():
    ctx, _, plugin, _ = completed_batch()
    data = call(plugin, ctx, "status")
    assert data["configured"] and not data["rule_configured"]
    assert data["counts"]["completed"] == 1
    assert data["records"][0]["origin"] == "manual"
    assert data["records"][0]["can_delete"]
    assert not data["records"][0]["can_retry"]
    assert call(plugin, ctx, "status", origin="rule")["records"] == []


def test_rule_and_manual_same_file_are_distinct_and_deletion_retains_journal():
    ctx, gateway, plugin, task = completed_batch()
    row = call(plugin, ctx, "status")["records"][0]
    ctx.config.update(task["config"])
    rule = plugin.settings(ctx)[-1]
    rule_state = ctx.state.scoped("copy-" + rule)
    key = "records-" + row["identity"][:3]
    rule_state.set(key, {row["identity"]: row})
    data = call(plugin, ctx, "status")
    assert len(data["records"]) == 2
    assert len({r["row_key"] for r in data["records"]}) == 2
    assert len(call(plugin, ctx, "status", origin="manual")["records"]) == 1
    call(plugin, ctx, "record-delete", origin="rule", identity=row["identity"])
    assert rule_state.get(key)[row["identity"]]["status"] == "completed"
    assert rule_state.get(key)[row["identity"]]["hidden"]
    asyncio.run(
        plugin.copy_one(
            ctx, gateway, rule_state, "source", "target", "destination", row["source_item"]
        )
    )
    assert gateway.copy_file.await_count == 1
    call(plugin, ctx, "batch-delete", id=task["id"])
    assert call(plugin, ctx, "status")["total"] == 0
    assert ctx.state.scoped("manual-" + task["id"]).get(key)


@pytest.mark.parametrize("status", ["skipped", "uncertain", "conflict", "failed"])
def test_retry_queues_only_selected_file_and_prevents_double_submit(status):
    ctx, gateway, plugin, task = completed_batch(status)
    row = call(plugin, ctx, "status")["records"][0]
    payload = {"origin": "manual", "batch_id": task["id"], "identity": row["identity"]}
    call(plugin, ctx, "record-retry", **payload)
    progress = ctx.state.scoped("manual-" + task["id"]).get("progress")
    assert [item["file_id"] for item in progress["pending"]] == ["file"]
    assert progress["folders"] == []
    with pytest.raises(ValueError, match="尚未结束"):
        call(plugin, ctx, "record-retry", **payload)
    with pytest.raises(ValueError, match="尚未结束"):
        call(plugin, ctx, "batch-delete", id=task["id"])
    gateway.copy_file.return_value = {
        "status": "completed",
        "file_id": "target-file",
        "method": "existing",
    }
    before = gateway.copy_file.await_count
    asyncio.run(plugin.run(ctx))
    assert gateway.copy_file.await_count == before + 1
    assert call(plugin, ctx, "status")["counts"]["completed"] == 1


def test_failed_scan_retry_preserves_remaining_directories():
    ctx, _, plugin, task = completed_batch()
    index = ctx.state.scoped("manual-batches")
    task = index.get("task-" + task["id"])
    task["status"] = "failed"
    index.set("task-" + task["id"], task)
    state = ctx.state.scoped("manual-" + task["id"])
    folders = [{"id": "remaining", "prefix": "folder", "cursor": None}]
    state.set("progress", {"pending": [], "folders": folders})
    call(plugin, ctx, "batch-retry", id=task["id"])
    assert state.get("progress")["folders"] == folders


def test_old_record_retry_resolves_identity_and_missing_temp_blocks():
    ctx, _, plugin, task = completed_batch("skipped")
    row = call(plugin, ctx, "status")["records"][0]
    state = ctx.state.scoped("manual-" + task["id"])
    key = "records-" + row["identity"][:3]
    rows = state.get(key)
    rows[row["identity"]].pop("source_item")
    state.set(key, rows)
    call(
        plugin, ctx, "record-retry", origin="manual", batch_id=task["id"], identity=row["identity"]
    )
    assert state.get("progress")["pending"][0]["file_id"] == "file"
    index = ctx.state.scoped("manual-batches")
    task = index.get("task-" + task["id"])
    task.update(status="failed")
    task["config"]["policy"] = "relay"
    index.set("task-" + task["id"], task)
    with pytest.raises(ValueError, match="临时目录"):
        call(plugin, ctx, "batch-retry", id=task["id"])


@pytest.mark.parametrize("mutation", ["running", "hidden", "record", "deleted"])
def test_retry_rechecks_state_after_source_lookup(mutation):
    ctx, gateway, plugin, task = completed_batch("skipped")
    row = call(plugin, ctx, "status")["records"][0]
    state = ctx.state.scoped("manual-" + task["id"])
    key = "records-" + row["identity"][:3]
    rows = state.get(key)
    rows[row["identity"]].pop("source_item")
    state.set(key, rows)
    original_progress = state.get("progress")
    original_page = gateway.file_page.return_value

    async def lookup(*_):
        if mutation in ("record", "deleted"):
            records = state.get(key)
            records[row["identity"]].update(
                status="completed" if mutation == "record" else "skipped",
                hidden=mutation == "deleted",
            )
            state.set(key, records)
        else:
            index = ctx.state.scoped("manual-batches")
            current = index.get("task-" + task["id"])
            current.update(
                status="running" if mutation == "running" else "completed",
                hidden=mutation == "hidden",
            )
            index.set("task-" + task["id"], current)
        await asyncio.sleep(0)
        return original_page

    gateway.file_page.side_effect = lookup
    with pytest.raises(ValueError, match="状态已变化"):
        call(
            plugin,
            ctx,
            "record-retry",
            origin="manual",
            batch_id=task["id"],
            identity=row["identity"],
        )
    assert state.get("progress") == original_progress
    assert state.get(key)[row["identity"]]["status"] != "retry"


def test_retry_rejects_duplicate_path_across_directory_pages():
    from cinecircuit_plugins.cloud_copy.record_actions import unique_child

    ctx, gateway = setup()
    item = {"file_id": "one", "name": "movie.mkv"}
    gateway.file_page.side_effect = [
        {"items": [item], "cursor": "next"},
        {"items": [{**item, "file_id": "two"}], "cursor": None},
    ]
    with pytest.raises(ValueError, match="路径不唯一"):
        asyncio.run(unique_child(gateway, "source", "0", "movie.mkv"))
