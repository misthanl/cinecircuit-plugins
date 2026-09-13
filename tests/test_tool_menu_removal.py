import inspect
from pathlib import Path

import pytest

from cinecircuit_plugins.auto_signin.plugin import SiteCheckinPlugin
from cinecircuit_plugins.media_cover_generator.plugin import LibraryArtworkPlugin


@pytest.mark.parametrize("plugin", [SiteCheckinPlugin, LibraryArtworkPlugin])
def test_tools_have_no_main_menu_but_keep_settings_and_statistics(plugin):
    assert not plugin.manifest.navigation
    assert plugin.manifest.config_schema["fields"]
    frontend = Path(inspect.getfile(plugin)).with_name("frontend.ts").read_text(encoding="utf-8")
    assert "plugin.statistics" in frontend
    assert "registerPage" not in frontend
    assert callable(plugin.run)


def test_every_plugin_menu_requires_a_visible_switch():
    from cinecircuit_plugins.catalog import factories
    for _, plugin in factories():
        manifest = plugin.manifest
        if not manifest.navigation:
            continue
        key = manifest.navigation.get("visibility_config_key")
        assert key, manifest.id
        field = next(item for item in manifest.config_schema["fields"] if item["key"] == key)
        assert field["input_type"] == "switch"
        assert field.get("visible", True) is True
        assert isinstance(field["default"], bool)
