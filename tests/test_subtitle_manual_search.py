import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cinecircuit_plugins.subtitle_manager.plugin import SubtitleWorkspacePlugin


@pytest.mark.parametrize(
    "address",
    [
        "",
        "https://search.example",
        "javascript:alert(1)",
        "https://user:password@search.example",
    ],
)
def test_manual_search_config_is_not_exposed_by_media_catalog(address):
    context = SimpleNamespace(
        config={"assrt_search_url": address, "assrt_api_key": "private"},
        media_files=SimpleNamespace(recorded_catalog=AsyncMock(return_value={"items": []})),
    )
    result = asyncio.run(
        SubtitleWorkspacePlugin()._catalog(context, query="", limit=10)
    )
    assert result == {"items": [], "count": 0}
    field = next(
        field
        for field in SubtitleWorkspacePlugin.manifest.config_schema["fields"]
        if field["key"] == "assrt_search_url"
    )
    assert field["default"] == "https://2.assrt.net"
    assert field["section"] == "online"
