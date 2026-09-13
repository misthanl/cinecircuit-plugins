import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock
import pytest
from test_brush_flow_cleanup import fixture
from cinecircuit_plugins.brush_flow.task_limits import owned_downloads, volume_remaining
from cinecircuit_plugins.brush_flow.task_settings import task_capacity, cron_values
from cinecircuit_plugins.brush_flow.cleanup import check_downloads
from cinecircuit_plugins.brush_flow.plugin import SiteTrafficPlugin


def test_inventory_over_100_without_default_tag_and_shared_lookup():
    ctx, rule, task = fixture()
    original = ctx.items.rows[0]
    rows, remote = [], {}
    for i in range(501):
        row = deepcopy(original)
        key = str(i)
        row['item_key'] = key
        row['result']['hash'] = key
        row['result']['brush_task_id'] = 'r1' if i < 300 else 'r2'
        rows.append(row)
        remote[key] = {**task, 'hash': key, 'size': 1024**3, 'tags': '刷流,owner-test'}
    ctx.items.rows = rows + [deepcopy(rows[0])]
    ctx.downloads.task = AsyncMock(side_effect=lambda d, h, **kw: remote[h])
    current = asyncio.run(owned_downloads(ctx))
    assert len(current) == 501
    assert ctx.downloads.task.await_count == 501
    assert task_capacity(ctx, {**rule, 'task_limit': 301}, current) == 1
    assert asyncio.run(volume_remaining(ctx, {**rule, 'seeding_limit_gib': 301}, current, complete=True)) == 1024**3
    assert ctx.downloads.task.await_count == 501


def test_failed_lookup_aborts_intake_before_dispatch():
    ctx, rule, _ = fixture()
    ctx.downloads.task.side_effect = RuntimeError('unavailable')
    host = SiteTrafficPlugin()
    host._add_candidate = AsyncMock()
    with pytest.raises(RuntimeError, match='unavailable'):
        asyncio.run(host._run_tasks(ctx, [rule]))
    host._add_candidate.assert_not_awaited()


@pytest.mark.parametrize('change', [{'added_on': 101}, {'hash': 'foreign'}, {'downloader_id': 'other'}, {'tags': '刷流'}])
def test_foreign_generation_not_counted(change):
    ctx, _, task = fixture()
    task.update(change)
    assert asyncio.run(owned_downloads(ctx)) == []


@pytest.mark.parametrize('key,metric,value', [
    ('delete_download_hours', 'download_hours', 2),
    ('delete_inactive_hours', 'inactive_hours', 2),
    ('delete_avg_upload_kib', 'avg_upload_kib_s', 0),
])
@pytest.mark.parametrize('protected', [False, True])
def test_unfinished_thresholds_respect_protected_tags(key, metric, value, protected):
    ctx, rule, task = fixture()
    rule[key] = 2
    task.update(progress=50, **{metric: value})
    if protected:
        task['tags'] += ',H&R'
    assert asyncio.run(check_downloads(ctx, [rule]))['deleted'] == int(not protected)


@pytest.mark.parametrize('expression,expected', [
    ('0/5', set(range(0, 60, 5))), ('*/5', set(range(0, 60, 5))),
    ('5-15/5', {5, 10, 15}), ('0,15,30,45', {0, 15, 30, 45}),
])
def test_cron_steps_and_lists(expression, expected):
    assert cron_values(expression, 0, 59) == expected


@pytest.mark.parametrize('expression', ['0/0', '60', '*/x', '1,,2', '5-1', '-1', '1/2/3'])
def test_cron_rejects_invalid_fields(expression):
    with pytest.raises(ValueError):
        cron_values(expression, 0, 59)


@pytest.mark.parametrize('global_limit,expected', [(1, 0), (2, 1)])
def test_global_capacity_reserves_success_across_rules(global_limit, expected):
    from types import SimpleNamespace
    ctx, rule, _ = fixture()
    ctx.config['max_tasks'] = global_limit
    rule.update(name='one', promotion='all', max_add=3)
    ctx.items.get = lambda key: None
    sites = SimpleNamespace(latest=AsyncMock(return_value={'items': [{'id': 'new'}]}))
    host = SiteTrafficPlugin()
    host._site_actions = lambda _: sites
    host._add_candidate = AsyncMock(return_value=True)
    host._notify_tasks = AsyncMock()
    result = asyncio.run(host._run_tasks(ctx, [rule, {**rule, 'id': 'r2'}]))
    assert result['added'] == expected
    assert host._add_candidate.await_count == expected
    ctx.downloads.task.assert_awaited_once()
