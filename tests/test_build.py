from hashlib import sha256
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import json
from types import SimpleNamespace
import subprocess

import pytest

import build as plugin_build


def test_published_reuse_preserves_bytes_and_rejects_source_or_manifest_changes(tmp_path):
    from scripts.package_reuse import reuse_archive

    directory = tmp_path / "cinecircuit_plugins" / "fixture"
    directory.mkdir(parents=True)
    (directory / "plugin.py").write_text("VALUE = 1\n", encoding="utf-8")
    packages = tmp_path / "packages"
    packages.mkdir()
    package = packages / "fixture.zip"
    _write_zip(package, b"original", (2026, 1, 1, 0, 0, 0))
    manifest = {"id": "fixture", "version": "1.0.0"}
    entry = {
        "manifest": manifest,
        "package_url": "packages/fixture.zip",
        "sha256": sha256(package.read_bytes()).hexdigest(),
    }
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "baseline",
        ],
        cwd=tmp_path,
        check=True,
    )
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    output = tmp_path / "dist"
    output.mkdir()
    result = reuse_archive(tmp_path, output, directory, manifest, [entry], revision)
    assert result["sha256"] == entry["sha256"]
    assert (output / package.name).read_bytes() == package.read_bytes()
    with pytest.raises(RuntimeError, match="manifest changed"):
        reuse_archive(
            tmp_path, output, directory, {**manifest, "name": "changed"}, [entry], revision
        )
    (directory / "plugin.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="source inputs changed"):
        reuse_archive(tmp_path, output, directory, manifest, [entry], revision)


def _write_zip(path, content: bytes, timestamp: tuple[int, int, int, int, int, int]) -> None:
    info = ZipInfo("plugin.py", timestamp)
    info.compress_type = ZIP_DEFLATED
    with ZipFile(path, "w") as archive:
        archive.writestr(info, content)


def test_existing_version_keeps_published_bytes_when_contents_match(tmp_path, monkeypatch):
    published_dir = tmp_path / "packages"
    published_dir.mkdir()
    published = published_dir / "fixture-1.0.0.zip"
    candidate = tmp_path / "fixture-1.0.0.zip"
    _write_zip(published, b"same", (2026, 1, 1, 0, 0, 0))
    _write_zip(candidate, b"same", (2026, 2, 1, 0, 0, 0))
    expected_digest = sha256(published.read_bytes()).hexdigest()
    monkeypatch.setattr(plugin_build, "ROOT", tmp_path)

    plugin_build.preserve_published_version(candidate)

    assert sha256(candidate.read_bytes()).hexdigest() == expected_digest


def test_existing_version_rejects_changed_contents(tmp_path, monkeypatch):
    published_dir = tmp_path / "packages"
    published_dir.mkdir()
    published = published_dir / "fixture-1.0.0.zip"
    candidate = tmp_path / "fixture-1.0.0.zip"
    _write_zip(published, b"old", (2026, 1, 1, 0, 0, 0))
    _write_zip(candidate, b"changed", (2026, 2, 1, 0, 0, 0))
    monkeypatch.setattr(plugin_build, "ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="without a version bump"):
        plugin_build.preserve_published_version(candidate)


def test_hash_named_package_keeps_version_and_bundles_shared_source(tmp_path, monkeypatch):
    from app.modules.plugins.contracts import PluginManifest
    from cinecircuit_plugins import catalog

    directory = tmp_path / "cinecircuit_plugins" / "fixture"
    shared = directory.parent / "_shared"
    directory.mkdir(parents=True)
    shared.mkdir()
    (shared / "counter.py").write_text("VALUE = 42\n", encoding="utf-8")
    (shared / "unrelated.py").write_text("raise RuntimeError('must not ship')\n", encoding="utf-8")
    manifest = PluginManifest(id="fixture-shared", name="Fixture", version="1.0.0")
    source = f"""from app.modules.plugins.contracts import PluginBase, PluginManifest
from .._shared.counter import VALUE
class Plugin(PluginBase):
    manifest = PluginManifest.from_dict({manifest.to_dict()!r})
    async def run(self, context):
        return {{"value": VALUE}}
"""
    (directory / "plugin.py").write_text(source, encoding="utf-8")
    for notice in ("LICENSE", "LICENSE_SCOPE.md"):
        (tmp_path / notice).write_bytes((plugin_build.ROOT / notice).read_bytes())
    (tmp_path / "frontend-activation.json").write_text('{"plugins":{}}', encoding="utf-8")
    monkeypatch.setattr(plugin_build, "ROOT", tmp_path)
    monkeypatch.setattr(plugin_build, "check_dependencies", lambda: None)
    monkeypatch.setattr(plugin_build, "build_frontends", lambda: None)
    monkeypatch.setattr(
        catalog, "factories", lambda: [(directory, SimpleNamespace(manifest=manifest))]
    )
    plugin_build.build(content_addressed=True)
    first = json.loads((tmp_path / "dist/packages.json").read_text())["plugins"][0]
    original = tmp_path / "packages" / first["package"]
    old_bytes = original.read_bytes()
    with ZipFile(original) as archive:
        assert b"from ._shared.counter import VALUE" in archive.read("plugin.py")
        assert "_shared/unrelated.py" not in archive.namelist()
        assert archive.read("_shared/counter.py") == (shared / "counter.py").read_bytes()
        assert json.loads(archive.read("manifest.json"))["version"] == "1.0.0"
        for notice in ("LICENSE", "LICENSE_SCOPE.md"):
            assert archive.read(notice) == (tmp_path / notice).read_bytes()
    plugin_build.build(content_addressed=True)
    repeated = json.loads((tmp_path / "dist/packages.json").read_text())["plugins"][0]
    assert repeated["sha256"] == first["sha256"]
    (shared / "counter.py").write_text("VALUE = 43\n", encoding="utf-8")
    plugin_build.build(content_addressed=True)
    second = json.loads((tmp_path / "dist/packages.json").read_text())["plugins"][0]
    assert second["manifest"]["version"] == first["manifest"]["version"]
    assert second["package"] != first["package"]
    assert original.read_bytes() == old_bytes
    (shared / "counter.py").write_text(
        "from app.core.config import get_settings\nVALUE = 42\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="Packaged plugin dependency boundary"):
        plugin_build.build(content_addressed=True)
