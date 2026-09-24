import importlib.util
from pathlib import Path


def test_shared_helpers_cannot_import_private_host_modules(tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts" / "repository_boundary.py"
    spec = importlib.util.spec_from_file_location("plugin_repository_boundary", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    shared = tmp_path / "cinecircuit_plugins" / "_shared"
    shared.mkdir(parents=True)
    helper = shared / "example.py"
    helper.write_text("from app.modules.config.service import ConfigService\n", encoding="utf-8")
    assert any("private host import" in item for item in module.check_repository(tmp_path))
    helper.write_text("from app.modules.plugins.contracts import PluginContext\n", encoding="utf-8")
    assert module.check_repository(tmp_path) == []
