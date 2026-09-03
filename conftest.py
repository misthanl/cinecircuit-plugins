import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "cinecircuit"))

import pytest


@pytest.fixture(autouse=True)
def external_plugin_registry(monkeypatch):
    """Legacy integration tests explicitly opt into this external fixture catalog."""
    from cinecircuit_plugins.catalog import test_registry
    from app.modules.plugins.registry import plugin_registry
    monkeypatch.setattr(plugin_registry, "_builtins", test_registry()._builtins)
