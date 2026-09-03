"""Development/build discovery, owned exclusively by the external plugin project."""
import importlib
from pathlib import Path


def factories():
    for directory in sorted(Path(__file__).parent.iterdir()):
        if (directory / "plugin.py").is_file():
            yield directory, importlib.import_module(f"cinecircuit_plugins.{directory.name}").PLUGIN


def test_registry():
    from app.modules.plugins.registry import PluginRegistry
    registry = PluginRegistry()
    for _, factory in factories():
        registry.register_builtin(factory)
    return registry
