"""Statistics contributions use the SDK text refresh button consistently."""
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1] / "cinecircuit_plugins"


@pytest.mark.parametrize("view", [
    "cookiecloud/StatisticsView.vue",
    "auto_signin/StatisticsView.vue",
    "douban_rank/StatisticsView.vue",
    "maoyan_rank/StatisticsView.vue",
    "media_cover_generator/HistoryView.vue",
])
def test_statistics_refresh_button(view):
    source = (ROOT / view).read_text(encoding="utf-8")
    buttons = re.findall(r'<UiButton\b([^>]*)>刷新</UiButton>', source)
    assert len(buttons) == 1
    attributes = buttons[0]
    assert 'prepend-icon="mdi-refresh"' in attributes
    assert 'variant="text"' in attributes
    assert ':loading=' in attributes
    assert '@click=' in attributes
