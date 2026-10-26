"""Resolve only the shared Python modules consumed by an independent package."""

import ast
from pathlib import Path


def shared_imports(source: str, *, inside_shared: bool = False) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 2 and (node.module or "").startswith("_shared."):
            modules.add(node.module.removeprefix("_shared.").split(".")[0])
        elif inside_shared and node.level == 1 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def shared_files(directory: Path, modules: set[str]) -> list[Path]:
    root = directory.parent / "_shared"
    pending = set(modules)
    resolved = set()
    while pending:
        name = pending.pop()
        if name in resolved:
            continue
        if not name.isidentifier():
            raise ValueError("Invalid shared module name")
        path = root / (name + ".py")
        resolved.add(name)
        pending.update(shared_imports(path.read_text(encoding="utf-8"), inside_shared=True))
    return [root / (name + ".py") for name in sorted(resolved)]
