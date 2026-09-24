from pathlib import Path

from cinecircuit_plugins.maoyan_rank.plugin import MaoyanWatchlistPlugin


def test_manifest_icon_is_supported_by_host():
    icon = MaoyanWatchlistPlugin.manifest.icon
    assert icon == "mdi-movie-search-outline"
    registry = Path(__file__).resolve().parents[2] / "cinecircuit/frontend/src/icons/mdiRegistry.generated.ts"
    assert f'"{icon}":' in registry.read_text(encoding="utf-8")


def test_configuration_sections_have_no_descriptions_or_field_icons():
    schema = MaoyanWatchlistPlugin.manifest.config_schema
    assert not schema.get("sections")
    assert all("section" not in field for field in schema["fields"])
    assert all(not field.get("icon") for field in schema["fields"])
    assert len(schema["fields"]) == 13
    assert schema["layout"]["columns"] == 2


def test_platform_switches_are_followed_by_their_own_limits():
    fields = MaoyanWatchlistPlugin.manifest.config_schema["fields"]
    assert [field["key"] for field in fields[5:]] == [
        "tx_enabled", "tx_num", "iqy_enabled", "iqy_num", "mg_enabled", "mg_num", "yk_enabled", "yk_num",
    ]
