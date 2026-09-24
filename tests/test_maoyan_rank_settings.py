import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from cinecircuit_plugins.maoyan_rank.plugin import MaoyanWatchlistPlugin


def test_explicit_empty_selection_never_fetches_or_subscribes():
    with pytest.raises(ValueError, match="请开启电影票房榜"):
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


def test_category_migration_and_explicit_new_choices():
    from cinecircuit_plugins.maoyan_rank.settings import normalized, CATEGORIES
    assert list(CATEGORIES.values()) == ["电影", "电视剧", "动漫", "综艺", "纪录片"]
    old = normalized({"type": ["movie", "web-heat", "web-tv", "zongyi"], "all_enabled": True})
    assert old["movie_enabled"] and old["platform_types"] == ["tv", "variety"]
    assert all(old[key + "_enabled"] for key in ("tx", "iqy", "mg", "yk"))
    new = normalized({**old, "platform_types": [], "movie_enabled": False, "tx_enabled": False})
    assert new["platform_types"] == [] and not new["tx_enabled"] and not new["movie_enabled"]


@pytest.mark.parametrize("platform", ["mg"])
def test_unsupported_only_category_never_fetches(platform):
    with pytest.raises(ValueError, match="支持该分类"):
        asyncio.run(MaoyanWatchlistPlugin().run(SimpleNamespace(config={"movie_enabled": False, "platform_types": ["documentary"], f"{platform}_enabled": True})))
