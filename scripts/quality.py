"""Independent plugin budgets plus the public host SDK dependency contract."""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "cinecircuit_plugins"
HOST = ROOT.parent / "cinecircuit"


def sources():
    for path in sorted(SOURCE.rglob("*.py")):
        if "_vendor" in path.parts or path.name.startswith("test_"):
            continue
        yield path


def function_lengths():
    violations = []
    for path in sources():
        source = path.read_text(encoding="utf-8-sig")
        if len(source.splitlines()) > 1000:
            violations.append(f"{path.relative_to(ROOT)}: module exceeds 1000 lines")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = node.end_lineno - node.lineno + 1
                if length > 50:
                    violations.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: {node.name}: {length} > 50 lines"
                    )
    return violations


def dependency_boundaries():
    # Run the public SDK contract's existing static checker, never import
    # plugin implementations into the host production registry.
    command = [sys.executable, str(HOST / "scripts" / "plugin_dependency_guard.py")]
    for directory in sorted(SOURCE.iterdir()):
        if (directory / "plugin.py").is_file():
            command.extend(["--source-dir", str(directory)])
    return subprocess.run(command, cwd=HOST, check=False).returncode


def stylesheet_lengths():
    violations = []
    for path in sorted(SOURCE.rglob("*.css")):
        length = len(path.read_text(encoding="utf-8-sig").splitlines())
        if length > 1000:
            violations.append(f"{path.relative_to(ROOT)}: stylesheet {length} > 1000 lines")
    return violations


def main():
    violations = function_lengths() + stylesheet_lengths()
    print(
        "\n".join(violations)
        if violations
        else "Source lengths: Python functions <= 50, Python/CSS files <= 1000 lines."
    )
    lint = subprocess.run(
        [sys.executable, "-m", "ruff", "check", *map(str, sources())],
        cwd=ROOT,
        check=False,
    ).returncode
    types = subprocess.run(
        [sys.executable, "-m", "mypy", "--config-file", "mypy.ini"],
        cwd=ROOT,
        check=False,
    ).returncode
    boundary = dependency_boundaries()
    shared_boundary = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "repository_boundary.py")],
        cwd=ROOT,
        check=False,
    ).returncode
    return int(bool(violations or lint or types or boundary or shared_boundary))


if __name__ == "__main__":
    raise SystemExit(main())
