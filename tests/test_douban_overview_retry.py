import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cinecircuit_plugins.douban_rank.metadata import supplement


def item(overview=""):
    return {
        "source_key": "douban",
        "source_id": "42",
        "media_type": "tv",
        "title": "Example",
        "overview": overview,
    }


@pytest.mark.parametrize("first", [item(), item("  "), RuntimeError("temporary")])
def test_missing_overview_retries_once_and_keeps_other_fields(first):
    media = SimpleNamespace(detail=AsyncMock(side_effect=[first, item("简介")]))
    result = asyncio.run(supplement(media, {**item(), "board": "榜单"}))
    assert result["overview"] == "简介"
    assert result["board"] == "榜单"
    assert media.detail.await_count == 2
    assert "refresh" not in media.detail.call_args_list[0].args[1]
    assert media.detail.call_args_list[1].args[1]["refresh"] is True


def test_complete_overview_does_not_add_a_request():
    media = SimpleNamespace(detail=AsyncMock(return_value=item("简介")))
    assert asyncio.run(supplement(media, item()))["overview"] == "简介"
    assert media.detail.await_count == 1


@pytest.mark.parametrize(
    "last", [item(), RuntimeError("temporary"), {**item("别的作品"), "source_id": "99"}]
)
def test_exhausted_retry_returns_candidate_and_logs_without_using_wrong_identity(last, caplog):
    media = SimpleNamespace(detail=AsyncMock(side_effect=[item(), last]))
    result = asyncio.run(supplement(media, item()))
    assert not result["overview"]
    assert result["source_id"] == "42"
    assert media.detail.await_count == 2
    assert "重试后简介仍为空" in caplog.text
