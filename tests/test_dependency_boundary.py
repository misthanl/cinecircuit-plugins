from pathlib import Path

from scripts.plugin_dependency_guard import check_plugin


def test_all_published_plugins_use_public_sdk_without_dependency_cycles():
    root = Path(__file__).resolve().parents[1] / "cinecircuit_plugins"
    failures = [
        finding
        for directory in sorted(root.iterdir())
        if (directory / "plugin.py").is_file()
        for finding in check_plugin(directory)
    ]
    assert failures == []
