"""Reuse exact published archives when all their source inputs are unchanged."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from .package_shared import shared_files, shared_imports


def source_inputs(directory: Path) -> set[Path]:
    inputs = {p for p in directory.rglob("*") if p.suffix in {".py", ".ts", ".vue", ".css"}}
    modules = set()
    for path in inputs:
        if path.suffix == ".py":
            modules.update(shared_imports(path.read_text(encoding="utf-8")))
    inputs.update(shared_files(directory, modules))
    pending = list(inputs)
    while pending:
        path = pending.pop()
        if path.suffix not in {".ts", ".vue"}:
            continue
        for relative in re.findall(
            r"(?:from\s*|import\s*)['\"]([^'\"]+)['\"]", path.read_text(encoding="utf-8")
        ):
            if not relative.startswith("."):
                continue
            candidate = (path.parent / relative).resolve()
            candidate = next(
                (
                    p
                    for p in (
                        candidate,
                        candidate.with_suffix(".ts"),
                        candidate.with_suffix(".vue"),
                    )
                    if p.is_file()
                ),
                candidate,
            )
            if candidate.is_file() and candidate not in inputs:
                inputs.add(candidate)
                pending.append(candidate)
    return inputs


def published_entries(root: Path, revision: str) -> list[dict]:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Published baseline must be a full verified Git commit SHA")
    content = subprocess.check_output(["git", "show", revision + ":plugins.json"], cwd=root)
    return json.loads(content)["plugins"]


def reuse_archive(
    root: Path, output: Path, directory: Path, manifest: dict, entries: list[dict], revision: str
):
    entry = next(
        (
            e
            for e in entries
            if e["manifest"]["id"] == manifest["id"]
            and e["manifest"]["version"] == manifest["version"]
        ),
        None,
    )
    if entry is None:
        return None
    if entry["manifest"] != manifest:
        raise RuntimeError("Published manifest changed without a version bump")
    paths = [str(p.resolve().relative_to(root.resolve())) for p in source_inputs(directory)]
    paths.extend(
        (
            str(directory.relative_to(root)),
            "sdk",
        )
    )
    if subprocess.check_output(["git", "diff", "--name-only", revision, "--", *paths], cwd=root):
        raise RuntimeError("Published source inputs changed without a version bump")
    if subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "--", *paths], cwd=root
    ):
        raise RuntimeError("Published package has new source inputs without a version bump")
    package = (root / entry["package_url"]).resolve()
    if package.parent != (root / "packages").resolve():
        raise ValueError("Published archive must be in packages")
    if hashlib.sha256(package.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError("Published archive digest mismatch")
    shutil.copyfile(package, output / package.name)
    return {"manifest": manifest, "package": package.name, "sha256": entry["sha256"]}
