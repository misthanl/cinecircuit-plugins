"""Check shared helpers and cross-package edges without importing plugin code."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT.parent / "cinecircuit"
sys.path.insert(0, str(HOST))

from scripts.dependency_graph import collect_imports, cycles, python_modules, runtime_edges
from scripts.plugin_dependency_guard import PUBLIC_HOST_MODULES


def check_repository(root: Path) -> list[str]:
    modules = python_modules(root, ("cinecircuit_plugins",))
    modules = {
        name: module
        for name, module in modules.items()
        if "_vendor" not in module.path.parts
        and not module.path.name.startswith("test_")
        # Local build/test discovery is not shipped in any plugin ZIP.
        and name != "cinecircuit_plugins.catalog"
    }
    edges, unresolved = collect_imports(modules)
    violations = [
        f"{modules[edge.source].path}:{edge.line}: private host import {edge.target}"
        for edge in sorted(edges)
        if (edge.target == "app" or edge.target.startswith("app."))
        and edge.target not in PUBLIC_HOST_MODULES
    ]
    violations.extend(
        f"{modules[item.source].path}:{item.line}: unresolved dynamic import {item.expression}"
        for item in unresolved
    )
    violations.extend(
        "Plugin runtime dependency cycle: " + " -> ".join(component)
        for component in cycles(runtime_edges(edges), modules)
    )
    return violations


if __name__ == "__main__":
    violations = check_repository(ROOT)
    print(
        "\n".join(violations)
        if violations
        else "Repository dependency guard passed (including shared helpers)."
    )
    raise SystemExit(bool(violations))
