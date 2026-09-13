import asyncio
from unittest.mock import AsyncMock

import pytest

from cinecircuit_plugins.cast_profile_enricher.plugin import CastProfileEnricherPlugin
from test_cast_profile_enricher_plugin import _context


@pytest.mark.parametrize("enabled", [False, True])
def test_person_without_id_is_preserved_without_name_search(enabled):
    context = _context()
    context.config["remove_unresolved"] = enabled
    context.media_servers.item_metadata = AsyncMock(return_value={"name": "Unknown"})
    context.media.search_people = AsyncMock(return_value={"items": []})
    context.media.person_detail = AsyncMock(return_value={})
    context.media.detail = AsyncMock(return_value={"cast": [{"name": "Someone Else", "character": "配角"}]})
    result = asyncio.run(CastProfileEnricherPlugin().run(context))
    assert result["removed_people"] == 0
    assert result["updated_roles"] == 0
    context.media.search_people.assert_not_awaited()
    context.media.person_detail.assert_not_awaited()


def test_matched_person_without_chinese_data_is_never_removed():
    context = _context()
    context.config["remove_unresolved"] = True
    context.media_servers.item_metadata = AsyncMock(return_value={"name": "Example Actor"})
    context.media.search_people = AsyncMock(return_value={"items": [{"name": "Example Actor", "source_id": "7"}]})
    context.media.person_detail = AsyncMock(return_value={"name": "Example Actor"})
    context.media.detail = AsyncMock(return_value={"cast": [{"name": "Someone Else", "character": "配角"}]})
    result = asyncio.run(CastProfileEnricherPlugin().run(context))
    assert result["removed_people"] == 0


def test_restored_switch_defaults_off():
    field = next(f for f in CastProfileEnricherPlugin.manifest.config_schema["fields"] if f["key"] == "remove_unresolved")
    assert field["default"] is False
