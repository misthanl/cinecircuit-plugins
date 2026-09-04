import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.model_registry import Base
from types import SimpleNamespace
from app.modules.plugins.contracts import PluginApiRequest, PluginManifest
from app.modules.plugins.gateways import ItemGateway
from .statistics import subscription_history
from .plugin import MaoyanWatchlistPlugin
from app.modules.plugins.service import PluginService


@pytest.fixture
def service(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    Base.metadata.create_all(engine)
    service = PluginService(sessionmaker(bind=engine))
    service.install(PluginManifest(id="maoyan-rank", name="猫眼", version="1"), owner_user_id=1, source="builtin", trusted=True)
    yield service
    engine.dispose()


def test_history_totals_cover_all_pages_and_only_successful_subscriptions(service):
    for index in range(10):
        service.record_item("maoyan-rank", f"item-{index}", status="subscribed", payload={
            "title": f"作品 {index}", "media_type": "movie" if index < 4 else "tv",
            "poster": "https://image.tmdb.org/t/p/w500/poster.jpg",
            "rank_source": {"platform": "爱奇艺" if index % 2 else "腾讯视频", "release_info": "上线2天", "board": "综艺榜" if index == 9 else "电视剧榜"},
            "private_field": "must-not-be-returned",
        })
    for status in ("ignored", "duplicate", "seen"):
        service.record_item("maoyan-rank", status, status=status, payload={"title": "未新增订阅"})
    service.record_item("another-plugin", "other", status="subscribed", payload={"title": "其他插件"})
    first = subscription_history(ItemGateway(service, "maoyan-rank"))
    second = subscription_history(ItemGateway(service, "maoyan-rank"), 2)
    assert (first["total"], first["movie_count"], first["tv_count"], first["platform_count"]) == (10, 4, 6, 2)
    assert len(first["items"]) == 8
    assert len(second["items"]) == 2
    assert second["total"] == 10
    assert first["items"][0]["title"] == "作品 9"
    assert first["items"][0]["media_label"] == "综艺"
    assert first["items"][0]["release_info"] == "上线2天"
    assert first["items"][0]["subscribed_at"]
    assert "private_field" not in str(first)
    assert {item["id"] for item in first["items"]}.isdisjoint(item["id"] for item in second["items"])
    assert subscription_history(ItemGateway(service, "maoyan-rank"), 99)["page"] == 2


def test_history_handles_empty_and_missing_metadata(service):
    empty = subscription_history(ItemGateway(service, "maoyan-rank"))
    assert empty["total"] == 0
    assert empty["items"] == []
    assert empty["pages"] == 1
    service.record_item("maoyan-rank", "legacy", status="subscribed", payload={"title": "旧记录", "media_type": "movie"})
    result = subscription_history(ItemGateway(service, "maoyan-rank"))
    assert result["platform_count"] == 0
    assert result["items"][0]["platform"] == "未知"
    assert result["items"][0]["poster"] == ""
    assert result["items"][0]["release_info"] == ""


def test_statistics_is_owned_by_plugin_api(service):
    context = SimpleNamespace(items=ItemGateway(service, "maoyan-rank"))
    plugin = MaoyanWatchlistPlugin()
    result = asyncio.run(plugin.handle_api(PluginApiRequest(action="statistics"), context))
    assert result["total"] == 0
    with pytest.raises(KeyError):
        asyncio.run(plugin.handle_api(PluginApiRequest(action="statistics", method="POST"), context))


def test_statistics_reads_all_gateway_pages():
    class Items:
        def list(self, limit, *, offset, status):
            assert status == "subscribed"
            return [{"id": index, "payload": {"title": str(index), "media_type": "movie"}, "updated_at": ""} for index in range(offset, min(offset + limit, 501))]
    result = subscription_history(Items(), page=63)
    assert result["total"] == result["movie_count"] == 501
    assert len(result["items"]) == 5


def test_statistics_frontend_is_served_from_the_plugin_directory(tmp_path):
    from app.api.routes_extension_catalogs import _frontend_module_path

    built_root = tmp_path / "maoyan_rank"
    built_root.mkdir()
    (built_root / "frontend.js").write_text("export function install() {}", encoding="utf-8")
    path = _frontend_module_path({"id": "maoyan-rank", "source": "zip", "enabled": True, "trusted": True, "install_path": str(built_root), "manifest": MaoyanWatchlistPlugin.manifest.to_dict()})
    assert path is not None
    assert path.parent.name == "maoyan_rank"
    assert path.name == "frontend.js"
    assert _frontend_module_path({"id": "maoyan-rank", "source": "builtin", "enabled": False, "trusted": True}) is None
