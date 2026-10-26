"""Build independently installable ZIPs. Run with the host development Python."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from scripts.package_shared import shared_imports, shared_files
from scripts.package_reuse import published_entries, reuse_archive
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent
FRONTEND_BUILD_ROOT = ROOT / ".build"
sys.path.insert(0, str(ROOT.parent / "cinecircuit"))


class PackageArchive(ZipFile):
    """Reproducible bytes: source timestamps and platform permissions are not inputs."""

    def writestr(self, zinfo_or_arcname, data, compress_type=None, compresslevel=None):
        name = getattr(zinfo_or_arcname, "filename", zinfo_or_arcname)
        info = ZipInfo(str(name).replace("\\", "/"), (1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        return super().writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)

    def write(self, filename, arcname=None, compress_type=None, compresslevel=None):
        self.writestr(arcname or Path(filename).name, Path(filename).read_bytes())


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
        raise RuntimeError(
            f"Published package version changed without a version bump: {package.name}"
        )
    shutil.copyfile(published, package)


def build(*, content_addressed=False, published_ref=""):
    from cinecircuit_plugins.catalog import factories

    check_dependencies()
    build_frontends()
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    entries = []
    baseline = published_entries(ROOT, published_ref) if published_ref else []
    for directory, factory in factories():
        manifest = factory.manifest.to_dict()
        reused = (
            reuse_archive(ROOT, output, directory, manifest, baseline, published_ref)
            if baseline
            else None
        )
        if reused:
            validate_package(output / reused["package"], factory, manifest)
            entries.append(reused)
            print(f"reused={reused['package']}")
            continue
        suffix = ".building.zip" if content_addressed else ".zip"
        package = output / f"{manifest['id']}-{manifest['version']}{suffix}"
        write_package(directory, manifest, package)
        validate_package(package, factory, manifest)
        if content_addressed:
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            addressed = package.with_name(
                f"{manifest['id']}-{manifest['version']}-{digest[:16]}.zip"
            )
            package.replace(addressed)
            package = addressed
        preserve_published_version(package)
        entries.append(
            {
                "manifest": manifest,
                "package": package.name,
                "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
            }
        )
        print(f"built={package.name} bytes={package.stat().st_size}")
    (output / "packages.json").write_text(
        json.dumps({"plugins": entries}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    publish_catalog(entries, output)


def write_package(directory, manifest, package):
    shared = set()
    with PackageArchive(package, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for notice in ("LICENSE", "LICENSE_SCOPE.md"):
            archive.writestr(notice, (ROOT / notice).read_bytes())
        for path in sorted(directory.rglob("*")):
            if not include_source(path, manifest):
                continue
            write_source(archive, directory, manifest, path, shared)
        if shared:
            archive.writestr("_shared/__init__.py", "")
            for path in shared_files(directory, shared):
                archive.write(path, "_shared/" + path.name)


def validate_package(package, factory, manifest):
    from app.modules.plugins.registry import PluginRegistry

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with ZipFile(package) as archive:
            archive.extractall(root)
        from scripts.plugin_dependency_guard import check_plugin

        violations = check_plugin(root)
        if violations:
            raise RuntimeError(
                "Packaged plugin dependency boundary failed:\n" + "\n".join(violations)
            )
        registry = PluginRegistry()
        registry.validate_package(root, factory.manifest)
        loaded = registry.load(
            {
                "id": manifest["id"],
                "source": "zip",
                "install_path": str(root),
                "entrypoint": manifest["entrypoint"],
                "manifest": manifest,
            }
        )
        assert loaded.manifest.to_dict() == manifest


def include_source(path, manifest):
    if not path.is_file() or "__pycache__" in path.parts:
        return False
    if (
        path.name.startswith("test_")
        or path.name.endswith((".test.mjs", ".pyc"))
        or path.name == "legacy_http_reference.py"
    ):
        return False
    if path.suffix == ".vue":
        return False
    # Subtitle styles are already embedded in its frontend.js.
    if manifest["id"] == "subtitle-manager" and path.suffix == ".css":
        return False
    # These cover previews are already embedded verbatim by Vite.
    # Keep full-size JPEGs and source photos for the preview API, but
    # don't ship a second copy of inline thumbnails/animations.
    if (
        manifest["id"] == "emby-cover-generator"
        and path.parent.name == "assets"
        and (path.name.startswith("thumb-") or path.name == "sample-multi.jpg")
    ):
        return False
    return True


def write_source(archive, directory, manifest, path, shared):
    if path.name == "frontend.ts":
        compiled = FRONTEND_BUILD_ROOT / path.relative_to(ROOT).with_suffix(".js")
        if not compiled.is_file():
            raise RuntimeError(f"Compiled frontend missing: {compiled}")
        archive.write(compiled, "frontend.js")
        return
    # Helper TypeScript is bundled into frontend.js, not loaded at runtime.
    if path.suffix == ".ts":
        return
    if path.suffix == ".py":
        source = path.read_text(encoding="utf-8")
        if "from .._shared." in source:
            if path.parent != directory:
                raise ValueError("Shared imports must be declared in a plugin root module")
            shared.update(shared_imports(source))
            source = re.sub(r"(?m)^from \.\._shared\.", "from ._shared.", source)
            archive.writestr(path.relative_to(directory).as_posix(), source)
            return
    archive.write(path, path.relative_to(directory).as_posix())


def check_dependencies() -> None:
    """Reject private host imports and cycles before executing/package-building plugins."""
    from scripts.plugin_dependency_guard import check_plugin

    directories = sorted((ROOT / "cinecircuit_plugins").iterdir())
    failures = [
        finding
        for directory in directories
        if (directory / "plugin.py").is_file()
        for finding in check_plugin(directory)
    ]
    if failures:
        raise RuntimeError("Plugin dependency boundary failed:\n" + "\n".join(failures))


def publish_catalog(entries, output):
    """Publish portable relative GitHub URLs alongside the independent ZIPs."""
    from app.modules.plugins.package_manager import PluginCatalogClient

    published = ROOT / "packages"
    published.mkdir(exist_ok=True)
    online = []
    replacements_file = ROOT / "package-replacements.json"
    replacements = (
        json.loads(replacements_file.read_text(encoding="utf-8"))
        if replacements_file.is_file()
        else {}
    )
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
        manifest = entry["manifest"]
        supersedes = replacements.get(manifest["id"], {}).get(manifest["version"], [])
        if supersedes:
            item["supersedes_sha256"] = [sha for sha in supersedes if sha != entry["sha256"]]
        # Verify the exact format consumed by the host, without a network request.
        PluginCatalogClient._catalog_item(
            item,
            {"id": 1, "name": "fixture/catalog"},
            "https://raw.githubusercontent.com/fixture/catalog/main/plugins.json",
        )
        shutil.copyfile(source, published / package)
        online.append(item)
    (ROOT / "plugins.json").write_text(
        json.dumps({"plugins": online}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"github_catalog=plugins.json packages={len(online)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--content-addressed",
        action="store_true",
        help="Create distinct hash-named packages without changing manifest versions",
    )
    parser.add_argument(
        "--published-ref",
        default="",
        help="Verified published commit for byte-stable reuse of unchanged packages",
    )
    args = parser.parse_args()
    build(content_addressed=args.content_addressed, published_ref=args.published_ref)
