"""Exercise brush intake using resources produced by the host parsers."""
import xml.etree.ElementTree as ET

import pytest

from app.modules.explore.acquisition_service import AcquisitionExploreService
from app.modules.explore.pt_search.plugins._candidate_mapping import (
    _rss_item,
    normalize_api_item,
    parse_nexusphp_items,
)
from app.modules.plugins.gateway_sites import SiteGateway
from app.modules.plugins.sdk import SecureSiteActions
from cinecircuit_plugins.brush_flow.selection import matches
from cinecircuit_plugins.brush_flow.task_limits import size_bytes


SIZE = 4 * 1024**3
SITE = {"id": "fixture", "name": "Fixture", "base_url": "https://fixture.example"}


def host_item(kind):
    if kind == "nexusphp":
        document = (
            '<table class="torrents"><tr><td>'
            '<a href="details.php?id=7">Example</a></td><td>4 GB</td>'
            '<td><a href="details.php?id=7#seeders">8</a></td></tr></table>'
        )
        return parse_nexusphp_items(AcquisitionExploreService, SITE, document)[0]
    if kind == "api":
        return normalize_api_item(
            AcquisitionExploreService,
            SITE,
            {"id": 7, "name": "Example", "size": SIZE,
             "downloadvolumefactor": 0, "uploadvolumefactor": 2},
        )
    node = ET.fromstring(
        '<item><title>Example</title><guid>7</guid>'
        '<link>https://fixture.example/details.php?id=7</link>'
        f'<enclosure length="{SIZE}" url="https://fixture.example/download.php?id=7"/>'
        '</item>'
    )
    if kind == "rss_engine":
        return _rss_item(AcquisitionExploreService, SITE, node, "Example")
    return SiteGateway._feed_item(node, SITE["id"], SITE)


@pytest.mark.parametrize("kind", ["nexusphp", "api", "rss_engine", "rss_gateway"])
def test_volume_reads_bytes_from_host_resource_after_sdk_redaction(kind):
    item = SecureSiteActions._public_mapping(host_item(kind))
    assert size_bytes(item) == SIZE


def test_double_free_rule_accepts_actual_host_api_promotion():
    item = SecureSiteActions._public_mapping(host_item("api"))
    assert item["promotion"] == "2X FREE"
    assert matches(item, {"promotion": "2xfree", "size_range": "0-100"})
