import asyncio
from unittest.mock import AsyncMock
import pytest
from test_brush_flow_cleanup import fixture
from cinecircuit_plugins.brush_flow.cleanup import check_downloads
from cinecircuit_plugins.brush_flow.statistics import build_statistics
from cinecircuit_plugins.brush_flow.task_limits import owned_downloads


@pytest.mark.parametrize("tags", ["", "CineCircuit", "刷流-other"])
def test_unlabeled_tasks_are_filtered_before_limits_statistics_and_cleanup(tags):
    ctx, rule, task = fixture()
    task["tags"] = tags
    task.update(uploaded_bytes=123, downloaded=1)
    assert asyncio.run(owned_downloads(ctx)) == []
    assert asyncio.run(build_statistics(ctx, [rule]))["tasks"][0]["size"] == 0
    assert asyncio.run(check_downloads(ctx, [rule]))["checked"] == 0
    ctx.downloads.task.assert_not_awaited()
    ctx.downloads.delete.assert_not_awaited()
    ctx.downloads.list_tagged_tasks.assert_awaited_with("刷流", offset=0, limit=200)


def test_manual_tag_does_not_adopt_foreign_generation():
    ctx, rule, task = fixture()
    task.update(tags="刷流", added_on=101)
    assert asyncio.run(owned_downloads(ctx)) == []
    assert asyncio.run(check_downloads(ctx, [rule]))["deleted"] == 0
    ctx.downloads.task.assert_not_awaited()


def test_remote_inventory_error_stops_intake_and_cleanup():
    ctx, rule, _ = fixture()
    ctx.downloads.list_tagged_tasks = AsyncMock(
        return_value={"items": [], "errors": [{"error": "offline"}]}
    )
    with pytest.raises(RuntimeError):
        asyncio.run(owned_downloads(ctx))
    with pytest.raises(RuntimeError):
        asyncio.run(check_downloads(ctx, [rule]))
    ctx.downloads.delete.assert_not_awaited()
