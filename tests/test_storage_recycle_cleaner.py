import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from cinecircuit_plugins.storage_recycle_cleaner import StorageRecycleCleanerPlugin


def context(config, trigger="manual"):
    gateway = SimpleNamespace(clear_recycle_bin=AsyncMock(return_value={"ok": True}))
    return SimpleNamespace(config=config, trigger=trigger, sdk=Mock(require=Mock(return_value=gateway)),
                           logger=Mock(), notifications=SimpleNamespace(send=AsyncMock()))


@pytest.mark.parametrize("config,trigger", [({}, "manual"), ({"storage_id": "one"}, "manual"),
    ({"storage_id": "one", "confirm_permanent": True}, "scheduled")])
def test_no_implicit_cleanup(config, trigger):
    ctx = context(config, trigger)
    assert asyncio.run(StorageRecycleCleanerPlugin().run(ctx))["status"] == "skipped"
    ctx.sdk.require.assert_not_called()


def test_clears_only_selected_storage_and_keeps_password_out_of_result():
    ctx = context({"storage_id": "one", "confirm_permanent": True, "password": "123456"})
    result = asyncio.run(StorageRecycleCleanerPlugin().run(ctx))
    ctx.sdk.require.return_value.clear_recycle_bin.assert_awaited_once_with("one", password="123456", confirm=True)
    assert result["status"] == "success"
    assert "123456" not in str(result) + str(ctx.logger.mock_calls)


def test_failure_not_retried_or_notified_as_success():
    ctx = context({"storage_id": "one", "confirm_permanent": True, "notification_enabled": True})
    ctx.sdk.require.return_value.clear_recycle_bin.side_effect = TimeoutError()
    with pytest.raises(TimeoutError):
        asyncio.run(StorageRecycleCleanerPlugin().run(ctx))
    assert ctx.sdk.require.return_value.clear_recycle_bin.await_count == 1
    ctx.notifications.send.assert_not_awaited()


def test_safety_key_is_secret_and_schedule_defaults_off():
    fields = {item["key"]: item for item in StorageRecycleCleanerPlugin.manifest.config_schema["fields"]}
    assert fields["password"]["secret"] is True
    assert fields["enabled"]["default"] is False
    assert fields["storage_id"]["required_capabilities"] == ["recycle_bin_clear"]
    assert fields["storage_id"]["default"] is None
    assert fields["storage_id"]["description_display"] == "hidden"
    assert fields["password"]["description_display"] == "hidden"
    assert StorageRecycleCleanerPlugin.manifest.frontend_module == "frontend.js"
