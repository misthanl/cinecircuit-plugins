from pathlib import Path
import ast
import re

import pytest


@pytest.mark.parametrize("editor", [
    "cast_profile_enricher/CastProfileEditor.vue",
    "cookiecloud/ConnectionEditor.vue",
    "media_cover_generator/RunEditor.vue",
    "media_cover_generator/TargetSelector.vue",
    "media_cover_generator/StyleEditor.vue",
])
def test_custom_form_grids_use_host_geometry(editor):
    source = (Path(__file__).resolve().parents[1] / "cinecircuit_plugins" / editor).read_text(
        encoding="utf-8"
    )
    assert "plugin-config-grid" in source
    assert "--app-plugin-config-row-gap" in source
    assert "--app-plugin-config-column-gap" in source
    assert not re.search(r"v-selection-control[^{}]*\{[^}]*min-height:\s*\d", source)


def test_plugins_declare_shared_presentation_and_animation_exception():
    root = Path(__file__).resolve().parents[1] / "cinecircuit_plugins"
    sources = list(root.glob("*/plugin.py"))
    assert sources
    for source in sources:
        declaration_sources = [source]
        manifest_source = source.with_name("manifest.py")
        if manifest_source.exists():
            declaration_sources.append(manifest_source)
        schemas = [keyword.value
                   for declaration in declaration_sources
                   for node in ast.walk(ast.parse(declaration.read_text(encoding="utf-8")))
                   if isinstance(node, ast.Call)
                   for keyword in node.keywords if keyword.arg == "config_schema"]
        assert len(schemas) == 1, source.parent.name
        schema_node = schemas[0]
        schema = dict(zip((ast.literal_eval(key) for key in schema_node.keys), schema_node.values))
        assert ast.literal_eval(schema["description_display"]) == "hidden"
        assert ast.literal_eval(schema["layout"]) == {"columns": 2, "row_gap": 14, "column_gap": 16}
        fields = [{ast.literal_eval(key): ast.literal_eval(value)
                   for key, value in zip(field.keys, field.values)
                   if ast.literal_eval(key) in {"key", "description_display"}}
                  for field in ast.walk(schema["fields"]) if isinstance(field, ast.Dict)
                  and all(isinstance(key, ast.Constant) for key in field.keys)
                  and any(key.value == "description_display" for key in field.keys)]
        persistent = [field["key"] for field in fields
                      if field.get("description_display") == "always"]
        expected = (["animation_format", "animation_duration", "animation_fps", "animation_resolution"]
                    if source.parent.name == "media_cover_generator" else [])
        assert persistent == expected
