"""Apply a reviewed package update with unchanged permissions to a stopped host."""

import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from app.modules.plugins.package_manager import PluginPackageManager
from app.modules.plugins.registry import PluginRegistry
from app.modules.plugins.service import PluginService


def validate_manifest(old, manifest, *, sources=("zip", "local")):
    if old is None or old["source"] not in sources:
        raise RuntimeError("Plugin must already be installed from an allowed source")
    previous = old["manifest"]
    for field in ("id", "entrypoint", "api_version", "permissions"):
        if manifest[field] != previous[field]:
            raise RuntimeError(f"Plugin {field} changed; automatic update refused")


def verify_restored_state(service, manifest, old, state):
    current = service.get(manifest["id"], redact=False)
    if PluginRegistry().load(current).manifest.to_dict() != manifest:
        raise RuntimeError("Installed plugin manifest differs from reviewed package")
    service.restore_update_state(state)
    current = service.get(manifest["id"], redact=False)
    preserved = (
        "config",
        "enabled",
        "source",
        "trusted",
        "owner_user_id",
        "source_url",
        "granted_permissions",
    )
    if current is None or any(current.get(field) != old.get(field) for field in preserved):
        raise RuntimeError("Plugin installation state was not preserved")


def update(path, digest):
    content = path.read_bytes()
    if not (hashlib.sha256(content).hexdigest() == digest):
        raise RuntimeError("Deployment precondition failed (update_installed_package.py:15)")
    with ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    service = PluginService()
    old = service.get(manifest["id"], redact=False)
    validate_manifest(old, manifest)
    state = service.snapshot_update_state(manifest["id"])
    staged = PluginPackageManager(service).stage_install_zip(
        content,
        owner_user_id=old["owner_user_id"],
        source=old["source"],
        source_url=old.get("source_url", ""),
        expected_sha256=digest,
        expected_manifest=manifest,
    )
    try:
        verify_restored_state(service, manifest, old, state)
        staged.finalize()
    except BaseException:
        staged.rollback()
        raise
    print(
        json.dumps({"id": manifest["id"], "version": manifest["version"], "config_preserved": True})
    )


if __name__ == "__main__":
    if sys.argv[1] == "--catalog":
        catalog = Path(sys.argv[2])
        service = PluginService()
        pending = []
        for entry in json.loads(catalog.read_text(encoding="utf-8"))["plugins"]:
            manifest = entry["manifest"]
            old = service.get(manifest["id"], redact=False)
            if old is None:
                continue
            validate_manifest(old, manifest, sources=("zip",))
            path = (catalog.parent / entry["package"]).resolve()
            if not (path.parent == catalog.parent.resolve()):
                raise RuntimeError(
                    "Deployment precondition failed (update_installed_package.py:60)"
                )
            if not (hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]):
                raise RuntimeError(
                    "Deployment precondition failed (update_installed_package.py:61)"
                )
            pending.append((path, entry["sha256"]))
        for path, digest in pending:
            update(path, digest)
    else:
        update(Path(sys.argv[1]), sys.argv[2])
