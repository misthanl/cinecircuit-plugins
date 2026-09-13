import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cinecircuit_plugins.cast_profile_enricher import CastProfileEnricherPlugin


def test_foreign_identity_never_reaches_douban_detail():
    media = SimpleNamespace(
        search_source_identity=AsyncMock(return_value={"source_key": "tmdb", "source_id": "314888"}),
        detail=AsyncMock(),
    )
    context = SimpleNamespace(media=media, logger=logging.getLogger(__name__))
    result = asyncio.run(CastProfileEnricherPlugin()._read_cast(context, {"name": "Fixture", "media_type": "Series", "year": "2019"}))
    assert result == []
    media.detail.assert_not_awaited()


def test_explicit_douban_id_does_not_need_identity_conversion():
    media = SimpleNamespace(search_source_identity=AsyncMock(), detail=AsyncMock(return_value={"cast": [{"name": "演员", "character": "角色"}]}))
    context = SimpleNamespace(media=media, logger=logging.getLogger(__name__))
    result = asyncio.run(CastProfileEnricherPlugin()._read_cast(context, {"provider_ids": {"Douban": "42"}}))
    assert result[0]["character"] == "角色"
    media.search_source_identity.assert_not_awaited()
    assert media.detail.await_args.args[1]["source_id"] == "42"


def test_occupation_labels_are_not_character_names():
    plugin = CastProfileEnricherPlugin()
    roles = plugin._role_map([
        {"name": "A", "character": "演员"},
        {"name": "B", "character": "演员 / 配音"},
        {"name": "C", "character": "柯布 Cobb"},
    ])
    assert "a" not in roles and "b" not in roles
    assert roles["c"] == "柯布 Cobb"
    assert plugin._localized_role({"works": [{"source_id": "42", "character": "演员"}]}, {"provider_ids": {"Tmdb": "42"}}, {}, person_name="A", person_role="Hero", localized_name="") == ""
