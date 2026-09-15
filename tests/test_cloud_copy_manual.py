import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cinecircuit_plugins.cloud_copy import CloudCopyPlugin
from test_cloud_copy import context


class NamespacedState:
    def __init__(self, values=None, namespace="default"):
        self.values = values if values is not None else {}
        self.namespace = namespace

    def scoped(self, namespace):
        return NamespacedState(self.values, namespace)

    def get(self, key, default=None):
        return copy.deepcopy(self.values.get((self.namespace, key), default))

    def set(self, key, value):
        self.values[self.namespace, key] = copy.deepcopy(value)

    def delete(self, key):
        self.values.pop((self.namespace, key), None)

    def list(self, *, prefix="", limit=100, after=""):
        return [{"key": key, "value": copy.deepcopy(value)} for (namespace, key), value in sorted(self.values.items())
                if namespace == self.namespace and key.startswith(prefix) and key > after][:limit]


def setup():
    ctx = context("source", "target")
    ctx.state = NamespacedState()
    ctx.config = {}
    ctx.trigger = "scheduled"
    gateway = ctx.sdk.require.return_value
    gateway.file_relative_to = AsyncMock(return_value=None)
    return ctx, gateway


def request(**overrides):
    return SimpleNamespace(action="submit", method="POST", payload={
        "id": "11111111-1111-4111-a111-111111111111", "source": "source", "target": "target",
        "source_root": "0", "target_root": "destination", "selected": ["file"], **overrides}, query={})


def test_selected_file_runs_without_automatic_config_and_is_idempotent():
    ctx, gateway = setup()
    plugin = CloudCopyPlugin()
    task = asyncio.run(plugin.handle_api(request(), ctx))
    again = asyncio.run(plugin.handle_api(request(), ctx))
    assert task == again
    gateway.copy_file.assert_not_called()
    assert ctx.config == {}
    outcome = asyncio.run(plugin.run(ctx))
    assert outcome["status"] == "success"
    assert outcome["batch_id"] == task["id"]
    assert ctx.logger.info.call_count >= 3
    gateway.copy_file.assert_awaited_once()
    assert gateway.copy_file.call_args.args[1] == "file"
    asyncio.run(plugin.run(ctx))
    assert gateway.copy_file.await_count == 1
    result = asyncio.run(plugin.handle_api(SimpleNamespace(action="batch", method="GET", query={"id": task["id"]}), ctx))
    assert result["completed"] == 1
    assert result["records"][0]["path"] == "movie.mkv"


def test_manual_progress_is_visible_while_copy_is_awaiting_and_failure_is_logged():
    ctx, gateway = setup()
    ctx.config["temporary_directory"] = "/media/copy-temp"
    plugin = CloudCopyPlugin()
    task = asyncio.run(plugin.handle_api(request(policy="verify"), ctx))

    async def copying(*args, **kwargs):
        live = ctx.state.scoped("manual-batches").get("task-" + task["id"])
        assert live["status"] == "running"
        assert live["current_file"] == "movie.mkv"
        assert "校验" in live["phase"]
        raise RuntimeError("fixture transfer failure")

    gateway.copy_file.side_effect = copying
    outcome = asyncio.run(plugin.run(ctx))
    assert outcome["status"] == "failed"
    assert "fixture transfer failure" in outcome["error"]
    ctx.logger.exception.assert_called_once()


@pytest.mark.parametrize("policy", ["verify", "relay"])
def test_missing_directory_blocks_manual_content_copy(policy):
    ctx, gateway = setup()
    with pytest.raises(ValueError, match="临时目录"):
        asyncio.run(CloudCopyPlugin().handle_api(request(policy=policy, temporary_directory="/untrusted/request"), ctx))
    gateway.copy_file.assert_not_called()


def test_clearing_directory_blocks_already_queued_content_copy():
    ctx, gateway = setup()
    ctx.config["temporary_directory"] = "/media/copy-temp"
    plugin = CloudCopyPlugin()
    asyncio.run(plugin.handle_api(request(policy="verify"), ctx))
    ctx.config["temporary_directory"] = ""
    result = asyncio.run(plugin.run(ctx))
    assert result["status"] == "failed"
    assert "临时目录" in result["error"]
    gateway.copy_file.assert_not_called()


def test_folder_selection_keeps_name_and_does_not_scan_unselected_folder():
    ctx, gateway = setup()
    async def page(storage, parent, cursor):
        if storage == "target":
            return {"items": [], "cursor": None}
        if parent == "0":
            return {"items": [{"file_id": "folder", "name": "Movies", "directory": True},
                              {"file_id": "other", "name": "Other", "directory": True}], "cursor": None}
        assert parent == "folder"
        return {"items": [{"file_id": "child", "name": "film.mkv", "directory": False}], "cursor": None}
    gateway.file_page.side_effect = page
    plugin = CloudCopyPlugin()
    asyncio.run(plugin.handle_api(request(selected=["folder"]), ctx))
    gateway.file_page.reset_mock()
    asyncio.run(plugin.run(ctx))
    gateway.file_page.assert_awaited_once_with("source", "folder", None)
    gateway.ensure_directory.assert_awaited_once_with("target", "destination", "Movies")
    assert gateway.copy_file.call_args.args[1] == "child"


def test_same_account_descendant_is_rejected():
    ctx, gateway = setup()
    gateway.same_account.return_value = True
    gateway.file_page.return_value = {"items": [{"file_id": "folder", "name": "Movies", "directory": True}], "cursor": None}
    gateway.file_relative_to.return_value = {"relative_path": "child"}
    with pytest.raises(ValueError, match="目标目录不能"):
        asyncio.run(CloudCopyPlugin().handle_api(request(selected=["folder"]), ctx))
    assert not ctx.state.scoped("manual-batches").list()


def test_stale_selection_is_rejected():
    ctx, gateway = setup()
    with pytest.raises(ValueError, match="所选文件已变化"):
        asyncio.run(CloudCopyPlugin().handle_api(request(selected=["missing"]), ctx))
    gateway.copy_file.assert_not_called()


def test_large_batch_continues_after_new_plugin_instance():
    ctx, gateway = setup()
    files = [{"file_id": str(i), "name": f"{i}.mkv", "directory": False} for i in range(25)]
    gateway.file_page.return_value = {"items": files, "cursor": None}
    plugin = CloudCopyPlugin()
    asyncio.run(plugin.handle_api(request(selected=[str(i) for i in range(25)]), ctx))
    asyncio.run(plugin.run(ctx))
    assert gateway.copy_file.await_count == 20
    asyncio.run(CloudCopyPlugin().run(ctx))
    assert gateway.copy_file.await_count == 25


def test_remote_failure_is_reported_without_blind_background_retry():
    ctx, gateway = setup()
    plugin = CloudCopyPlugin()
    task = asyncio.run(plugin.handle_api(request(), ctx))
    gateway.copy_file.side_effect = TimeoutError("remote timeout")
    asyncio.run(plugin.run(ctx))
    asyncio.run(plugin.run(ctx))
    assert gateway.copy_file.await_count == 1
    result = asyncio.run(plugin.handle_api(SimpleNamespace(action="batch", method="GET", query={"id": task["id"]}), ctx))
    assert result["status"] == "failed"
    assert result["records"][0]["status"] == "uncertain"


def test_explicit_retry_recovers_pending_file_without_duplicate_batch():
    ctx, gateway = setup()
    plugin = CloudCopyPlugin()
    task = asyncio.run(plugin.handle_api(request(), ctx))
    gateway.copy_file.side_effect = TimeoutError("remote timeout")
    asyncio.run(plugin.run(ctx))
    retry_request = SimpleNamespace(action="batch-retry", method="POST", payload={"id": task["id"]})
    asyncio.run(plugin.handle_api(retry_request, ctx))
    gateway.copy_file.side_effect = None
    asyncio.run(plugin.run(ctx))
    assert gateway.copy_file.await_count == 2
    result = asyncio.run(plugin.handle_api(SimpleNamespace(action="batch", method="GET", query={"id": task["id"]}), ctx))
    assert result["status"] == "completed"
