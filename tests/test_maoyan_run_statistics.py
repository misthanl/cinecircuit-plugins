import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from cinecircuit_plugins.maoyan_rank.statistics import save_run_snapshot, cumulative_statistics
from cinecircuit_plugins.maoyan_rank.plugin import MaoyanWatchlistPlugin


def test_run_results_are_separate_from_deduplication_history():
    state = Mock()
    actions = [{"title": str(i), "status": status, "reason": "season_ambiguous"}
               for i, status in enumerate(["subscribed", "in_library", "already_subscribed", "unknown", "not_recognized", "skipped"])]
    save_run_snapshot(state, actions, "completed")
    key, value = state.set.call_args.args
    assert key == "latest_run_statistics"
    assert (value["checked"], value["subscribed"], value["existing"], value["retry"]) == (6, 1, 3, 2)
    assert value["items"][3]["reason"] == "目标季不明确"
    assert "subscription" not in value["items"][0]


@pytest.mark.parametrize("failed", [False, True])
def test_run_snapshot_overwrites_previous_run_and_preserves_partial_results(failed):
    plugin = MaoyanWatchlistPlugin()
    state = Mock()
    async def work(context, actions):
        actions.append({"title": "示例", "status": "unknown"})
        if failed:
            raise RuntimeError("failure")
        return {"actions": actions}
    plugin._run = work
    context = SimpleNamespace(state=state)
    if failed:
        with pytest.raises(RuntimeError):
            asyncio.run(plugin.run(context))
    else:
        asyncio.run(plugin.run(context))
    snapshots = [call.args[1] for call in state.set.call_args_list]
    assert snapshots[0]["status"] == "running"
    assert snapshots[0]["items"] == []
    assert snapshots[1]["status"] == ("failed" if failed else "completed")
    assert snapshots[1]["retry"] == 1


def test_cumulative_counts_survive_runs_failures_and_repeated_final_save():
    data = {}
    state = SimpleNamespace(get=data.get, set=lambda key, value: data.__setitem__(key, value))
    first = [{"title": "A", "status": "subscribed"}, {"title": "B", "status": "unknown"}]
    save_run_snapshot(state, [], "running")
    save_run_snapshot(state, first, "completed")
    save_run_snapshot(state, first, "completed")
    assert cumulative_statistics(data['latest_run_statistics'])['checked'] == 2
    save_run_snapshot(state, [], "running")
    assert cumulative_statistics(data['latest_run_statistics'])['checked'] == 2
    save_run_snapshot(state, [{"title": "A", "status": "skipped"}], "failed")
    totals = cumulative_statistics(data['latest_run_statistics'])
    assert tuple(totals[key] for key in ('checked', 'subscribed', 'existing', 'retry')) == (3, 1, 1, 1)
    assert len(data['latest_run_statistics']['items']) == 1


def test_legacy_snapshot_is_imported_once_and_marked_partial():
    data = {'latest_run_statistics': {'checked': 5, 'subscribed': 2, 'existing': 2, 'retry': 1,
                                    'updated_at': '2026-09-08T00:00:00Z'}}
    state = SimpleNamespace(get=data.get, set=lambda key, value: data.__setitem__(key, value))
    for _ in range(2):
        save_run_snapshot(state, [], 'running')
        save_run_snapshot(state, [{'status': 'subscribed'}], 'completed')
    totals = cumulative_statistics(data['latest_run_statistics'])
    assert totals['checked'] == 7
    assert totals['subscribed'] == 4
    assert totals['legacy_partial'] is True
    assert totals['since'] == '2026-09-08T00:00:00Z'


def test_empty_cumulative_counts_are_zero():
    totals = cumulative_statistics(None)
    assert all(totals[key] == 0 for key in ('checked', 'subscribed', 'existing', 'retry'))


@pytest.mark.parametrize('cleared', [0, 3, None])
def test_clear_resets_statistics_only_when_request_consumed(monkeypatch, cleared):
    data = {}
    state = SimpleNamespace(get=data.get, set=lambda key, value: data.__setitem__(key, value))
    save_run_snapshot(state, [{'title': 'old', 'status': 'subscribed'}], 'completed')
    plugin = MaoyanWatchlistPlugin()
    context = SimpleNamespace(config={'clear': True}, state=state,
        items=SimpleNamespace(clear_once=Mock(return_value=cleared)), logger=Mock())
    def failed_fetch(**kwargs):
        snapshot = data['latest_run_statistics']
        expected = 1 if cleared is None else 0
        assert cumulative_statistics(snapshot)['subscribed'] == expected
        assert snapshot['items'] == []
        raise RuntimeError('fetch failed')
    monkeypatch.setattr('cinecircuit_plugins.maoyan_rank.plugin.http_client', failed_fetch)
    with pytest.raises(RuntimeError, match='fetch failed'):
        asyncio.run(plugin.run(context))
    snapshot = data['latest_run_statistics']
    assert cumulative_statistics(snapshot)['subscribed'] == (1 if cleared is None else 0)
    save_run_snapshot(state, [], 'running')
    save_run_snapshot(state, [{'status': 'in_library'}], 'completed')
    assert cumulative_statistics(data['latest_run_statistics'])['existing'] == 1


def test_failed_history_clear_does_not_reset_cumulative_statistics(monkeypatch):
    data = {}
    state = SimpleNamespace(get=data.get, set=lambda key, value: data.__setitem__(key, value))
    save_run_snapshot(state, [{'status': 'subscribed'}], 'completed')
    context = SimpleNamespace(config={'clear': True}, state=state,
        items=SimpleNamespace(clear_once=Mock(side_effect=RuntimeError('clear failed'))))
    with pytest.raises(RuntimeError, match='clear failed'):
        asyncio.run(MaoyanWatchlistPlugin().run(context))
    assert cumulative_statistics(data['latest_run_statistics'])['subscribed'] == 1
    assert context.config['clear'] is True
