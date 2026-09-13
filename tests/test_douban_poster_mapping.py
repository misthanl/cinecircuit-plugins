import pytest

from cinecircuit_plugins.douban_rank.media import normalized_media


@pytest.mark.parametrize("fields", [
    {"cover": "https://example.com/poster.jpg"},
    {"cover": {"url": "https://example.com/poster.jpg"}},
    {"pic": {"normal": "https://example.com/poster.jpg"}},
])
def test_board_poster_variants(fields):
    item = normalized_media({"id": "42", "type": "tv", **fields})
    assert item["poster"] == "https://example.com/poster.jpg"
