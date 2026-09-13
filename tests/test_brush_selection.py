from datetime import datetime, timezone
import pytest
from cinecircuit_plugins.brush_flow.selection import bounds, matches


def item(**values):
    return {"title": "Example", "promotion": "FREE", "hit_and_run": False,
            "size_bytes": 10 * 1024**3, "seeders": 10, **values}


def test_defaults_and_promotions():
    assert matches(item(), {})
    assert not matches(item(promotion="NORMAL"), {})
    assert not matches(item(hit_and_run=True), {})
    assert not matches(item(), {"site_hr": True})
    assert matches(item(hit_and_run=True), {"exclude_hr": False})
    assert matches(item(promotion="NORMAL"), {"promotion": "all"})
    assert matches(item(promotion="2XFREE"), {"promotion": "2xfree"})
    assert not matches(item(), {"promotion": "2xfree"})


def test_ranges_and_missing_values():
    assert matches(item(), {"size_range": "0-10", "seeders_range": "10"})
    assert not matches(item(), {"size_range": "0-9"})
    assert not matches(item(seeders_known=False), {"seeders_range": "0-100"})
    assert not matches(item(size_bytes=None), {"size_range": "0-100"})
    assert matches(item(), {"min_size": 1, "max_size": 20})
    assert not matches(item(), {"min_size": 11})


def test_publish_age_and_timezone_offset():
    now = datetime(2026, 9, 11, 2, tzinfo=timezone.utc)
    rule = {"publish_range": "0-60", "timezone_offset": 8}
    assert matches(item(publish_time="2026-09-11 09:00:00"), rule, now=now)
    assert matches(item(published_at="Fri, 11 Sep 2026 09:00:00 +0800"), rule, now=now)
    assert not matches(item(publish_time="2026-09-11 08:59:00"), rule, now=now)
    assert not matches(item(), rule, now=now)


@pytest.mark.parametrize("value", ["100-0", "-1", "1-2-3", "nan", "inf"])
def test_invalid_ranges(value):
    with pytest.raises(ValueError):
        bounds(value)


def test_title_filters():
    assert matches(item(), {"include": "Example", "exclude": "Other"})
    assert not matches(item(), {"exclude": "Example"})
    assert not matches(item(), {"include": "Other"})
