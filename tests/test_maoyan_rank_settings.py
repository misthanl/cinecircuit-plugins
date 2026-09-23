import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from cinecircuit_plugins.maoyan_rank.plugin import MaoyanWatchlistPlugin


@pytest.mark.parametrize("config,expected", [
    ({"num": "3", "web_movie_num": "7"}, (3, 7)),
    ({"num": "3"}, (3, 3)),
    ({"num": "3", "web_movie_num": None}, (3, 3)),
])
def test_movie_limits_are_independent_and_preserve_legacy_settings(config, expected):
    def response(url, **kwargs):
        if "dashboard-ajax/movie" in url:
            payload = {"movieList": {"list": [{"movieInfo": {"movieName": str(index)}} for index in range(10)]}}
        else:
            payload = {"data": {"list": [{"name": str(index)} for index in range(10)]}}
        return SimpleNamespace(status_code=200, json=lambda: payload)
    client = SimpleNamespace(get=AsyncMock(side_effect=response))
    rows = asyncio.run(MaoyanWatchlistPlugin()._movie_candidates(client, config, ["movie", "web-movie"]))
    assert tuple(sum(row["board"] == board for row in rows) for board in ["电影票房榜", "网络电影榜"]) == expected


def test_explicit_empty_selection_never_fetches_or_subscribes():
    with pytest.raises(ValueError, match="至少选择一个榜单"):
        asyncio.run(MaoyanWatchlistPlugin().run(SimpleNamespace(config={"type": []})))


def test_clear_precedes_schedule_and_defaults_off():
    fields = MaoyanWatchlistPlugin.manifest.config_schema["fields"]
    assert [field["key"] for field in fields[:2]] == ["clear", "cron"]
    assert fields[0]["default"] is False
    assert sum(field["input_type"] == "cron" for field in fields) == 1


@pytest.mark.parametrize("enabled", [False, True])
def test_clear_runs_before_fetch_and_is_not_repeated_after_fetch_failure(monkeypatch, enabled):
    context = SimpleNamespace(config={"clear": enabled}, items=SimpleNamespace(clear_once=Mock(return_value=3)), logger=Mock())
    def fail_http(**kwargs):
        assert context.config["clear"] is False
        raise RuntimeError("fetch failed")
    monkeypatch.setattr("cinecircuit_plugins.maoyan_rank.plugin.http_client", fail_http)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="fetch failed"):
            asyncio.run(MaoyanWatchlistPlugin().run(context))
    assert context.items.clear_once.call_count == int(enabled)
    if enabled:
        context.items.clear_once.assert_called_once_with("clear")


def test_old_host_rejects_clear_without_claiming_success():
    context = SimpleNamespace(config={"clear": True}, items=SimpleNamespace())
    with pytest.raises(RuntimeError, match="先更新主程序"):
        asyncio.run(MaoyanWatchlistPlugin().run(context))
    assert context.config["clear"] is True


def test_failed_clear_leaves_switch_on_and_does_not_fetch(monkeypatch):
    context = SimpleNamespace(config={"clear": True}, items=SimpleNamespace(clear_once=Mock(side_effect=RuntimeError("database failed"))))
    http = Mock()
    monkeypatch.setattr("cinecircuit_plugins.maoyan_rank.plugin.http_client", http)
    with pytest.raises(RuntimeError, match="database failed"):
        asyncio.run(MaoyanWatchlistPlugin().run(context))
    assert context.config["clear"] is True
    http.assert_not_called()


def test_platform_defaults_off_but_saved_selection_still_works():
    plugin = MaoyanWatchlistPlugin()
    fields = {field["key"]: field for field in plugin.manifest.config_schema["fields"]}
    assert fields["all_enabled"]["default"] is False
    client = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(status_code=200, json=lambda: {"dataList": {"list": []}})))
    assert asyncio.run(plugin._television_candidates(client, {}, ["web-heat"])) == []
    client.get.assert_not_awaited()
    asyncio.run(plugin._television_candidates(client, {"all_enabled": True}, ["web-heat"]))
    client.get.assert_awaited_once()
