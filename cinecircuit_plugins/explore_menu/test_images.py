import pytest

from .images import iqiyi_poster


@pytest.mark.parametrize("suffix", ["", "_260_360", "_579_772"])
def test_iqiyi_cover_uses_large_portrait_without_duplicate_sizes(suffix):
    url = f"http://pic0.iqiyipic.com/image/2026/a_123_m_601_m3{suffix}.jpg?token=public"
    assert iqiyi_poster(url) == "https://pic0.iqiyipic.com/image/2026/a_123_m_601_m3_579_772.jpg?token=public"


@pytest.mark.parametrize("url", ["", "https://other.example/poster.jpg", "https://iqiyipic.com.other.example/poster.jpg"])
def test_other_image_hosts_are_unchanged(url):
    assert iqiyi_poster(url) == url
