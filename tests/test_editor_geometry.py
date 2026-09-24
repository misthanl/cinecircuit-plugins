from pathlib import Path
import re

import pytest


@pytest.mark.parametrize(
    "editor",
    [
        "cast_profile_enricher/CastProfileEditor.vue",
        "cookiecloud/ConnectionEditor.vue",
        "media_cover_generator/RunEditor.vue",
        "media_cover_generator/TargetSelector.vue",
        "media_cover_generator/StyleEditor.vue",
    ],
)
def test_custom_form_grids_use_host_geometry(editor):
    source = (Path(__file__).resolve().parents[1] / "cinecircuit_plugins" / editor).read_text(
        encoding="utf-8"
    )
    assert "plugin-config-grid" in source
    assert "--app-plugin-config-row-gap" in source
    assert "--app-plugin-config-column-gap" in source
    assert not re.search(r"v-selection-control[^{}]*\{[^}]*min-height:\s*\d", source)


def test_plugins_declare_shared_presentation_and_animation_exception():
    from cinecircuit_plugins.catalog import factories

    for directory, factory in factories():
        schema = factory.manifest.config_schema
        assert schema["description_display"] == "hidden", directory.name
        assert schema["layout"] == {"columns": 2, "row_gap": 14, "column_gap": 16}
        persistent = [
            field["key"]
            for field in schema["fields"]
            if field.get("description_display") == "always"
        ]
        expected = (
            ["animation_format", "animation_duration", "animation_fps", "animation_resolution"]
            if directory.name == "media_cover_generator"
            else []
        )
        assert persistent == expected
