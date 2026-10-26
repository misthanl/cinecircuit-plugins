import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from cinecircuit_plugins.brush_flow.intake_retry import failure, ready
from cinecircuit_plugins.brush_flow.plugin import SiteTrafficPlugin


def test_old_network_and_media_failures_are_retried_after_route_fix():
    for error in (
        "种子文件请求失败，请稍后重试",
        "站点详情页请求失败，请稍后重试",
        "未识别到媒体信息，下载任务未提交",
    ):
        assert ready({"status": "failed", "result": {"error": error}})
    assert not ready({"status": "added", "result": {}})
    assert not ready({"status": "duplicate", "result": {}})
    assert not ready({"status": "failed", "result": {"error": "下载目录不存在"}})


def test_failed_submission_has_backoff_and_retains_attempt_count(monkeypatch):
    monkeypatch.setattr("cinecircuit_plugins.brush_flow.intake_retry.time", lambda: 100)
    first = failure("出站请求超时")
    assert not ready({"status": "failed", "result": first}, now=159)
    assert ready({"status": "failed", "result": first}, now=160)
    second = failure("出站请求超时", {"result": first})
    assert second["retry_count"] == 2 and second["retry_at"] == 220


def test_brush_does_not_fall_back_to_media_identification_dispatch():
    media_dispatch = AsyncMock()
    ctx = SimpleNamespace(
        downloads=SimpleNamespace(add=media_dispatch),
        items=SimpleNamespace(get=lambda _: None, record=Mock()),
    )
    sites = SimpleNamespace(dispatch=media_dispatch)
    assert not asyncio.run(
        SiteTrafficPlugin._add_candidate(ctx, sites, "site", {}, {"id": "7"}, "key")
    )
    media_dispatch.assert_not_awaited()
    assert "直接种子提交" in ctx.items.record.call_args.kwargs["result"]["error"]


def test_intake_retries_failed_candidate_but_keeps_successful_receipt_deduplicated():
    plugin = SiteTrafficPlugin()
    plugin._add_candidate = AsyncMock(return_value=True)
    item = {"id": "7", "size_bytes": 1024}
    record = {"status": "failed", "result": {"error": "种子文件请求失败，请稍后重试"}}
    context = SimpleNamespace(items=SimpleNamespace(get=lambda _: record))
    result = asyncio.run(
        plugin._submit_candidates(context, None, "site", {"id": "task"}, [item], 3, 2048)
    )
    assert result == (1, 0)
    record["status"] = "added"
    result = asyncio.run(
        plugin._submit_candidates(context, None, "site", {"id": "task"}, [item], 3, 2048)
    )
    assert result == (0, 0)
    plugin._add_candidate.assert_awaited_once()
