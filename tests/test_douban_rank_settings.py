import asyncio
from pathlib import Path
from types import SimpleNamespace

from cinecircuit_plugins.douban_rank.plugin import DoubanWatchlistPlugin
from cinecircuit_plugins.douban_rank.statistics import save_run_snapshot


def test_supported_icon_and_configuration():
    manifest = DoubanWatchlistPlugin.manifest
    registry = Path(__file__).resolve().parents[2] / "cinecircuit/frontend/src/icons/mdiRegistry.generated.ts"
    assert f'"{manifest.icon}":' in registry.read_text(encoding="utf-8")
    assert not manifest.config_schema.get("sections")
    assert all(not field.get("icon") for field in manifest.config_schema["fields"])


def test_subscription_origin_and_statistics_keep_candidate_details():
    received = []

    async def create(key, payload):
        received.append(payload)
        return {"status": "subscribed"}

    context = SimpleNamespace(items=SimpleNamespace(processed=lambda key: key == "old"),
                              subscriptions=SimpleNamespace(create_checked=create))
    actions = asyncio.run(DoubanWatchlistPlugin._apply_candidates(context, {
        "new": {"title": "新电影", "board": "热门电影"},
        "old": {"title": "旧电影", "board": "热门电影"},
    }))
    assert received[0]["subscription_origin"] == "豆瓣榜单"
    assert [item["title"] for item in actions] == ["新电影", "旧电影"]
    data = {}
    state = SimpleNamespace(get=data.get, set=lambda key, value: data.update({key: value}))
    for _ in range(2):
        save_run_snapshot(state, [], "running")
        save_run_snapshot(state, actions, "completed")
    result = data["latest_run_statistics"]
    assert result["cumulative"]["checked"] == 4
    assert result["cumulative"]["subscribed"] == 2
    assert result["cumulative"]["existing"] == 2
    assert result["items"][0]["board"] == "热门电影"
