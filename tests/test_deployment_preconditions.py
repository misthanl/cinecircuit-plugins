"""Maintenance guards remain active with Python optimization and preserve rollback."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_update():
    spec = importlib.util.spec_from_file_location(
        "reviewed_update", ROOT / "update_installed_package.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("field", ["id", "entrypoint", "api_version", "permissions"])
def test_manifest_change_rejected_before_staging(field):
    module = load_update()
    manifest = dict(id="fixture", entrypoint="plugin:Plugin", api_version="1", permissions=[])
    changed = {**manifest, field: "changed"}
    with pytest.raises(RuntimeError, match=field):
        module.validate_manifest({"source": "zip", "manifest": manifest}, changed)


def test_optimized_python_still_rejects_permission_change():
    program = """
import runpy, sys
module=runpy.run_path(sys.argv[1], run_name='review')
manifest=dict(id='fixture', entrypoint='plugin:Plugin', api_version='1', permissions=[])
try:
    module['validate_manifest']({'source':'zip','manifest':manifest}, {**manifest,'permissions':['new']})
except RuntimeError:
    sys.exit(0)
sys.exit(5)
"""
    environment = dict(os.environ, PYTHONPATH=str(ROOT.parent / "cinecircuit"))
    result = subprocess.run(
        [sys.executable, "-O", "-c", program, str(ROOT / "update_installed_package.py")],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_retired_migration_rejects_before_connecting():
    spec = importlib.util.spec_from_file_location("retired_deploy", ROOT / "deploy_installed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(RuntimeError, match="retired"):
        module.main()


def test_failed_post_install_state_check_rolls_back(tmp_path, monkeypatch):
    module = load_update()
    manifest = dict(
        id="fixture", entrypoint="plugin:Plugin", api_version="1", permissions=[], version="1"
    )
    path = tmp_path / "fixture.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    old = dict(
        source="zip", manifest=manifest, owner_user_id=1, config={}, enabled=True, trusted=True
    )
    service = SimpleNamespace(
        get=Mock(return_value=old), snapshot_update_state=Mock(return_value={})
    )
    staged = SimpleNamespace(finalize=Mock(), rollback=Mock())
    monkeypatch.setattr(module, "PluginService", lambda: service)
    monkeypatch.setattr(
        module,
        "PluginPackageManager",
        lambda _: SimpleNamespace(stage_install_zip=Mock(return_value=staged)),
    )
    monkeypatch.setattr(
        module, "verify_restored_state", Mock(side_effect=RuntimeError("state mismatch"))
    )
    with pytest.raises(RuntimeError, match="state mismatch"):
        module.update(path, hashlib.sha256(path.read_bytes()).hexdigest())
    staged.rollback.assert_called_once_with()
    staged.finalize.assert_not_called()


@pytest.mark.parametrize("field", ["source_url", "owner_user_id", "granted_permissions"])
def test_restored_state_checks_provenance_and_grants(field, monkeypatch):
    module = load_update()
    manifest = {"id": "fixture"}
    old = dict(
        source_url="https://example.invalid/plugin.zip", owner_user_id=2, granted_permissions=[]
    )
    current = {**old, field: "changed"}
    service = SimpleNamespace(get=Mock(return_value=current), restore_update_state=Mock())
    loaded = SimpleNamespace(manifest=SimpleNamespace(to_dict=lambda: manifest))
    monkeypatch.setattr(module, "PluginRegistry", lambda: SimpleNamespace(load=lambda _: loaded))
    with pytest.raises(RuntimeError, match="state was not preserved"):
        module.verify_restored_state(service, manifest, old, {})
