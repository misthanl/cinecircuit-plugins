import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.model_registry import Base
from app.modules.plugins.contracts import PluginApiRequest
from app.modules.plugins.gateways import ItemGateway
from app.modules.plugins.service import PluginService
from .plugin import DoubanWatchlistPlugin
from .statistics import _rating, subscription_history


def test_history_counts_all_subscribed_records_and_keeps_board_metadata(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    Base.metadata.create_all(engine)
    service = PluginService(sessionmaker(bind=engine))
    for index in range(10):
        service.record_item("douban-hot", str(index), status="subscribed", payload={
            "title": f"作品 {index}", "media_type": "movie" if index < 4 else "tv",
            "board": "热门综艺" if index == 9 else "一周口碑电影榜",
            "rating": "8.6", "poster": "https://img9.doubanio.com/poster.jpg",
            "private_field": "must-not-be-returned",
        })
    for status in ("ignored", "duplicate"):
        service.record_item("douban-hot", status, status=status, payload={})
    service.record_item("maoyan-rank", "other", status="subscribed", payload={})
    items = ItemGateway(service, "douban-hot")
    first = subscription_history(items)
    last = subscription_history(items, 99)
    assert (first["total"], first["movie_count"], first["tv_count"], first["board_count"]) == (10, 4, 6, 2)
    assert len(first["items"]) == 8
    assert last["page"] == 2
    assert len(last["items"]) == 2
    assert first["items"][0]["title"] == "作品 9"
    assert first["items"][0]["media_label"] == "综艺"
    assert first["items"][0]["rating"] == 8.6
    assert first["items"][0]["board"] == "热门综艺"
    assert "private_field" not in str(first)
    assert {row["id"] for row in first["items"]}.isdisjoint(row["id"] for row in last["items"])
    engine.dispose()


def test_statistics_reads_all_gateway_pages_and_handles_missing_metadata():
    class Items:
        def list(self, limit, *, offset, status):
            assert status == "subscribed"
            return [{"id": index, "payload": {"media_type": "movie"}, "updated_at": ""} for index in range(offset, min(offset + limit, 501))]

    result = subscription_history(Items(), 63)
    assert result["total"] == result["movie_count"] == 501
    assert result["board_count"] == 0
    assert len(result["items"]) == 5
    assert result["items"][0]["board"] == "未知榜单"
    assert result["items"][0]["rating"] is None
    assert result["items"][0]["poster"] == ""


@pytest.mark.parametrize("value", [None, "", "unknown", "NaN", "inf", 0, -1, 11])
def test_invalid_ratings_are_not_presented_as_scores(value):
    assert _rating(value) is None


def test_plugin_api_handles_empty_history_and_frontend_stays_in_plugin():
    from app.api.routes_extension_catalogs import _frontend_module_path

    context = SimpleNamespace(items=SimpleNamespace(list=lambda *args, **kwargs: []))
    plugin = DoubanWatchlistPlugin()
    result = asyncio.run(plugin.handle_api(PluginApiRequest(action="statistics"), context))
    assert result["total"] == 0
    assert result["pages"] == 1
    with pytest.raises(KeyError):
        asyncio.run(plugin.handle_api(PluginApiRequest(action="statistics", method="POST"), context))
    path = _frontend_module_path({"id": "douban-hot", "source": "zip", "enabled": True, "trusted": True, "install_path": str(__import__("pathlib").Path(__file__).parent), "manifest": DoubanWatchlistPlugin.manifest.to_dict()})
    assert path is not None
    assert path.parent.name == "douban_rank"
    assert _frontend_module_path({"id": "douban-hot", "source": "builtin", "enabled": False, "trusted": True}) is None
