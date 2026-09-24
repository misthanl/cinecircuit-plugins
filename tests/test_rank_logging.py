import pytest

from cinecircuit_plugins._shared.rank_logging import result_text


@pytest.mark.parametrize("status,reason,expected", [
    ("in_library", "season_complete", "已入库，跳过（目标季已齐全）"),
    ("already_subscribed", "subscription_exists", "已订阅，跳过（已有对应订阅）"),
    ("subscribed", "created", "已添加订阅"),
    ("unknown", "library_lookup_failed", "无法确认，暂缓并在下次重试（媒体服务器查询失败）"),
    ("skipped", "达到每轮新增上限，下次重试", "已跳过（达到每轮新增上限，下次重试）"),
    ("future_status", "future_code", "结果待确认，请查看详情"),
])
def test_rank_logs_show_human_readable_outcomes(status, reason, expected):
    assert result_text({"status": status, "reason": reason}) == expected


def test_douban_logs_chinese_but_preserves_machine_readable_results(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    from cinecircuit_plugins.douban_rank.plugin import DoubanWatchlistPlugin

    candidate = {"title": "示例剧集", "season": "S02"}
    result = {"status": "in_library", "reason": "season_complete"}
    context = SimpleNamespace(logger=Mock())
    monkeypatch.setattr(DoubanWatchlistPlugin, "_prepare_candidate", AsyncMock(return_value=candidate))
    monkeypatch.setattr(DoubanWatchlistPlugin, "_create_candidate", AsyncMock(return_value=result))
    actions = asyncio.run(DoubanWatchlistPlugin._apply_candidates(context, {"key": candidate}))
    args = context.logger.info.call_args.args
    assert args[0] % args[1:] == "示例剧集 S02：已入库，跳过（目标季已齐全）"
    assert actions[0]["status"] == "in_library"
    assert actions[0]["reason"] == "season_complete"
