import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from .feed import parse_feed, resolve_wish, user_ids
from .plugin import DoubanWishPlugin

NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def entry(title="想看测试影片", identity="123", date="Fri, 30 Oct 2026 11:00:00 GMT"):
    return f"<item><title>{title}</title><link>https://movie.douban.com/subject/{identity}/</link><pubDate>{date}</pubDate></item>"


def context():
    saved = {}
    state = SimpleNamespace(get=saved.get, set=lambda k, v: saved.update({k: v}))
    media = SimpleNamespace(detail=AsyncMock(return_value={"title": "测试影片", "source_key": "douban", "source_id": "123", "media_type": "movie"}), search=AsyncMock(return_value={"items": [{"title": "测试影片", "source_id": "123", "source_key": "douban", "media_type": "movie"}]}), resolve_identity=AsyncMock(return_value={"title": "测试影片", "source_key": "tmdb", "source_id": "456", "media_type": "movie"}))
    return SimpleNamespace(config={"users": "one,two", "days": 7}, state=state, items=SimpleNamespace(processed=Mock(return_value=False), clear_once=Mock()), media=media, subscriptions=SimpleNamespace(create_checked=AsyncMock(return_value={"status": "subscribed"})), notifications=SimpleNamespace(send=AsyncMock()))


def test_only_recent_wishes_are_read():
    data = "<rss><channel>" + entry() + entry("看过不应订阅", "456") + entry(identity="789", date="Wed, 01 Oct 2025 11:00:00 GMT") + entry(identity="321", date="invalid") + "</channel></rss>"
    assert parse_feed(data.encode(), "one", 7, NOW) == [{"title": "测试影片", "source_id": "123", "account": "one"}]


def test_namespaced_feed_and_invalid_login_html():
    xml = '<rss xmlns="urn:test"><channel>' + entry() + '</channel></rss>'
    assert len(parse_feed(xml.encode(), "one", 7, NOW)) == 1
    with pytest.raises(ValueError):
        parse_feed(b"<html><body>login</body></html>", "one", 7, NOW)


@pytest.mark.parametrize("value", ["", "https://douban.com/people/a/", "../secret", "a?query=1"])
def test_profile_identifiers_cannot_be_urls(value):
    with pytest.raises(ValueError):
        user_ids(value)


def test_multiple_user_formats_and_duplicates():
    assert user_ids("one, two\none，three") == ["one", "two", "three"]


def test_cross_account_duplicates_create_one_checked_subscription(monkeypatch):
    ctx = context()
    fetch = AsyncMock(side_effect=[[dict(title="测试影片", source_id="123", account="one")], [dict(title="测试影片", source_id="123", account="two")]])
    monkeypatch.setattr("cinecircuit_plugins.douban_wish.plugin.read_user", fetch)
    result = asyncio.run(DoubanWishPlugin().run(ctx))
    assert result["updated_count"] == 1
    args = ctx.subscriptions.create_checked.await_args.args
    assert args[0] == "wish:123"
    assert args[1]["subscription_origin"] == "豆瓣想看"
    assert ctx.subscriptions.create_checked.await_count == 1
    assert ctx.state.get("latest_run_statistics")["cumulative"]["subscribed"] == 1


def test_failed_user_does_not_block_other_users(monkeypatch):
    ctx = context()
    monkeypatch.setattr("cinecircuit_plugins.douban_wish.plugin.read_user", AsyncMock(side_effect=[RuntimeError("private upstream error"), [dict(title="测试影片", source_id="123", account="two")]]))
    result = asyncio.run(DoubanWishPlugin().run(ctx))
    assert result["failed_users"] == ["one"]
    assert result["updated_count"] == 1
    assert "private upstream error" not in str(result)
    assert ctx.state.get("latest_run_statistics")["status"] == "failed"


def test_unresolved_media_remains_retryable(monkeypatch):
    ctx = context()
    ctx.config["users"] = "one"
    ctx.media.detail.return_value = {}
    monkeypatch.setattr("cinecircuit_plugins.douban_wish.plugin.read_user", AsyncMock(return_value=[dict(title="测试影片", source_id="123", account="one")]))
    result = asyncio.run(DoubanWishPlugin().run(ctx))
    assert result["actions"][0]["status"] == "not_recognized"
    ctx.subscriptions.create_checked.assert_not_awaited()
    assert ctx.state.get("latest_run_statistics")["retry"] == 1


def test_processed_entries_skip_identity_and_library_lookup():
    ctx = context()
    ctx.items.processed.return_value = True
    assert asyncio.run(DoubanWishPlugin._admit(ctx, "wish:123", {}))["status"] == "skipped"
    ctx.media.search.assert_not_awaited()


def test_incomplete_library_check_never_claims_subscription():
    ctx = context()
    ctx.subscriptions.create_checked.return_value = {"status": "unknown", "reason": "library_unavailable"}
    result = asyncio.run(DoubanWishPlugin._admit(ctx, "wish:123", dict(title="测试影片", source_id="123", account="one")))
    assert result["status"] == "unknown"
    assert result["reason"] == "library_unavailable"


@pytest.mark.parametrize("detail", [
    {"source_key": "douban", "source_id": "999", "media_type": "movie", "title": "同名影片"},
    {"source_key": "tmdb", "source_id": "123", "media_type": "movie", "title": "同名影片"},
    {"source_key": "douban", "source_id": "123", "media_type": "person", "title": "演员"},
])
def test_foreign_or_invalid_source_detail_never_admitted(detail):
    ctx = context()
    ctx.media.detail.return_value = detail
    assert asyncio.run(resolve_wish(ctx.media, dict(title="测试影片", source_id="123", account="one"))) is None
    ctx.media.resolve_identity.assert_not_awaited()


def test_exact_subject_does_not_require_keyword_suggestions():
    ctx = context()
    ctx.media.search.return_value = {"items": []}
    result = asyncio.run(resolve_wish(ctx.media, dict(title="测试影片", source_id="123", account="one")))
    assert result["source_key"] == "tmdb"
    assert result["source_id"] == "456"
    ctx.media.search.assert_not_awaited()
    ctx.media.resolve_identity.assert_awaited_once_with(source="douban", source_id="123", media_type="movie")


def test_exact_tv_subject_preserves_type_and_douban_recognition():
    ctx = context()
    identity = {"title": "测试剧集", "source_key": "douban", "source_id": "123", "media_type": "tv"}
    ctx.media.detail.return_value = identity
    ctx.media.resolve_identity.return_value = identity
    result = asyncio.run(resolve_wish(ctx.media, dict(title="测试剧集", source_id="123", account="one")))
    assert result["media_type"] == "tv"
    assert result["source_key"] == "douban"


@pytest.mark.parametrize("identity", [None, {}, {"title": "测试影片", "source_key": "tmdb", "source_id": "456", "media_type": "tv"}])
def test_unresolved_or_wrong_type_identity_is_retryable(identity):
    ctx = context()
    ctx.media.resolve_identity.return_value = identity
    result = asyncio.run(DoubanWishPlugin._admit(ctx, "wish:123", dict(title="测试影片", source_id="123", account="one")))
    assert result["status"] == "not_recognized"
    ctx.subscriptions.create_checked.assert_not_awaited()


def test_clear_is_plugin_scoped_and_optional_notification(monkeypatch):
    ctx = context()
    ctx.config.update(users="one", clear=True, notification_enabled=True)
    monkeypatch.setattr("cinecircuit_plugins.douban_wish.plugin.read_user", AsyncMock(return_value=[dict(title="测试影片", source_id="123", account="one")]))
    asyncio.run(DoubanWishPlugin().run(ctx))
    ctx.items.clear_once.assert_called_once_with("clear")
    ctx.notifications.send.assert_awaited_once()
    assert ctx.config["clear"] is False


def test_manifest_uses_standard_configuration_and_read_only_statistics():
    manifest = DoubanWishPlugin.manifest
    assert manifest.id == "douban-wish"
    assert len(manifest.configuration_fields()) == 6
    assert manifest.configuration_fields()[0].rows == 1
    assert DoubanWishPlugin.disabled_read_actions == ("statistics",)


@pytest.mark.parametrize("enabled", [True, False])
def test_notification_configuration_reaches_host_gateway(monkeypatch, enabled):
    from app.modules.plugins.gateways import NotificationGateway, _plugin_notification_enabled
    from app.modules.plugins.permissions import PluginPermission

    ctx = context()
    ctx.config.update(users="one", notification_enabled=enabled)
    manifest = {"config_schema": DoubanWishPlugin.manifest.config_schema}
    gateway = NotificationGateway(SimpleNamespace(audit=Mock()), "test-wish", 1,
        {PluginPermission.NOTIFICATION_SEND}, config_service=object(),
        enabled=_plugin_notification_enabled({"manifest": manifest, "config": ctx.config}))
    service = SimpleNamespace(broadcast=AsyncMock(return_value=[]))
    gateway.service = service
    ctx.notifications = gateway
    monkeypatch.setattr("cinecircuit_plugins.douban_wish.plugin.read_user",
        AsyncMock(return_value=[dict(title="测试影片", source_id="123", account="one")]))
    asyncio.run(DoubanWishPlugin().run(ctx))
    assert service.broadcast.await_count == int(enabled)
    if enabled:
        assert service.broadcast.call_args.args == ("豆瓣想看同步完成", "新增订阅 1 项")
        assert service.broadcast.call_args.kwargs["notification_type"] == "plugin"
    assert "notify" not in {field["key"] for field in manifest["config_schema"]["fields"]}
