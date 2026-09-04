from hashlib import sha256
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

import build as plugin_build


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
