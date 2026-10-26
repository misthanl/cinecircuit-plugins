import asyncio

from test_brush_flow_cleanup import fixture
from cinecircuit_plugins.brush_flow.cleanup import check_downloads
from cinecircuit_plugins.brush_flow.task_limits import owned_downloads, volume_remaining
from cinecircuit_plugins.brush_flow.statistics import build_statistics


def test_receipt_controls_cleanup_without_random_ownership_tags():
    ctx, rule, task = fixture()
    task["tags"] = "刷流"
    ctx.items.rows[0]["result"].pop("ownership_tag")
    assert asyncio.run(check_downloads(ctx, [rule]))["deleted"] == 1
    ctx.downloads.task.assert_awaited_once_with("d1", "a" * 40, task_added_on=100)


def test_volume_and_statistics_keep_tracking_migrated_and_new_receipts():
    ctx, rule, task = fixture()
    task.update(
        tags="刷流",
        progress=50,
        size=1024**3,
        uploaded_bytes=123,
        downloaded=456,
        download_speed=1,
        upload_speed=2,
    )
    rule.update(seeding_limit_gib=2, name="Example")
    assert asyncio.run(owned_downloads(ctx)) == [task]
    assert asyncio.run(volume_remaining(ctx, rule, [task])) == 1024**3
    ctx.items.rows[0]["result"].pop("ownership_tag")
    assert asyncio.run(owned_downloads(ctx)) == [task]
    stats = asyncio.run(build_statistics(ctx, [rule]))
    assert stats["tasks"][0]["uploaded"] == 123
    assert stats["tasks"][0]["download_count"] == 1
