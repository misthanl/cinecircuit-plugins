"""Build independently installable ZIPs. Run with the host development Python."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
FRONTEND_BUILD_ROOT = ROOT / ".build"
sys.path.insert(0, str(ROOT.parent / "cinecircuit"))


def build_frontends() -> None:
    """Compile TypeScript and Vue SFC sources into one browser ESM file per plugin."""
    executable = shutil.which("node")
    script = ROOT / "scripts/build-frontends.mjs"
    if not executable or not script.is_file():
        raise RuntimeError("Frontend builder missing; run `pnpm install` before building plugins")
    subprocess.run(
        [executable, str(script)],
        cwd=ROOT,
        check=True,
    )


def preserve_published_version(package: Path) -> None:
    """Keep an existing version byte-stable and reject changed same-version contents."""
    published = ROOT / "packages" / package.name
    if not published.is_file():
        return
    with ZipFile(package) as candidate, ZipFile(published) as existing:
        candidate_names = sorted(candidate.namelist())
        existing_names = sorted(existing.namelist())
        unchanged = candidate_names == existing_names and all(
            candidate.read(name) == existing.read(name) for name in candidate_names
        )
    if not unchanged:
        raise RuntimeError(f"Published package version changed without a version bump: {package.name}")
    shutil.copyfile(published, package)


def build():
    from app.modules.plugins.registry import PluginRegistry
    from cinecircuit_plugins.catalog import factories

    build_frontends()
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    entries = []
    for directory, factory in factories():
        manifest = factory.manifest.to_dict()
        package = output / f"{manifest['id']}-{manifest['version']}.zip"
        with ZipFile(package, "w", ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or "__pycache__" in path.parts:
                    continue
                if path.name.startswith("test_") or path.name.endswith((".test.mjs", ".pyc")) or path.name == "legacy_http_reference.py":
                    continue
                if path.suffix == ".vue":
                    continue
                if path.name == "frontend.ts":
                    compiled = FRONTEND_BUILD_ROOT / path.relative_to(ROOT).with_suffix(".js")
                    if not compiled.is_file():
                        raise RuntimeError(f"Compiled frontend missing: {compiled}")
                    archive.write(compiled, "frontend.js")
                    continue
                archive.write(path, path.relative_to(directory).as_posix())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with ZipFile(package) as archive:
                archive.extractall(root)
            registry = PluginRegistry()
            registry.validate_package(root, factory.manifest)
            loaded = registry.load({"id": manifest["id"], "source": "zip", "install_path": str(root), "entrypoint": manifest["entrypoint"], "manifest": manifest})
            assert loaded.manifest.to_dict() == manifest
        preserve_published_version(package)
        entries.append({"manifest": manifest, "package": package.name, "sha256": hashlib.sha256(package.read_bytes()).hexdigest()})
        print(f"built={package.name} bytes={package.stat().st_size}")
    (output / "packages.json").write_text(json.dumps({"plugins": entries}, ensure_ascii=False, indent=2), encoding="utf-8")
    publish_catalog(entries, output)


def publish_catalog(entries, output):
    """Publish portable relative GitHub URLs alongside the independent ZIPs."""
    from app.modules.plugins.package_manager import PluginCatalogClient

    published = ROOT / "packages"
    published.mkdir(exist_ok=True)
    online = []
    for entry in entries:
        package = entry["package"]
        source = (output / package).resolve()
        if source.parent != output.resolve():
            raise ValueError("Package path must stay inside the build output directory")
        if hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Package digest changed before publication")
        item = {
            "manifest": entry["manifest"],
            "package_url": f"packages/{package}",
            "sha256": entry["sha256"],
        }
        # Verify the exact format consumed by the host, without a network request.
        PluginCatalogClient._catalog_item(
            item, {"id": 1, "name": "fixture/catalog"},
            "https://raw.githubusercontent.com/fixture/catalog/main/plugins.json",
        )
        shutil.copyfile(source, published / package)
        online.append(item)
    (ROOT / "plugins.json").write_text(
        json.dumps({"plugins": online}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"github_catalog=plugins.json packages={len(online)}")


if __name__ == "__main__":
    build()
