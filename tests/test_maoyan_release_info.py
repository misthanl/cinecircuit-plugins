from cinecircuit_plugins.maoyan_rank.release_info import release_info
from cinecircuit_plugins.maoyan_rank.statistics import _record
from cinecircuit_plugins.maoyan_rank.plugin import MaoyanWatchlistPlugin


def test_source_text_has_priority():
    assert release_info({"date": "2024-01-01", "rank_source": {"release_info": "上线2天"}}) == "上线2天"


def test_history_uses_stored_premiere_without_network_or_mutation():
    media = {"date": "2015-03-04", "media_type": "tv", "rank_source": {"platform": "优酷"}, "season": "S02"}
    assert _record({"payload": media, "id": 1, "updated_at": "2026-09-24"})["release_info"] == "剧集首播：2015-03-04"
    assert "release_info" not in media["rank_source"]


def test_unknown_date_is_not_replaced_by_subscription_date_or_year():
    for value in ("", "2026", "2026-02-30"):
        assert release_info({"date": value, "year": "2026", "updated_at": "2026-09-24"}) == ""


def test_new_subscription_preserves_release_information():
    row = {"title": "测试", "media_type": "movie", "platform": "优酷"}
    candidate = MaoyanWatchlistPlugin()._subscription_candidate(row, {"date": "2024-02-03"})
    assert candidate["rank_source"]["release_info"] == "上映：2024-02-03"
    assert "release_info" not in row
