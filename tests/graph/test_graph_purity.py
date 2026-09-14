"""Import rules for sdlc.graph (E-72 spec §4, E-73 spec §4): the package must
not open a new route into the benchmarks <-> stages import cycle, so its
MODULE-LEVEL imports are pinned. Function-local imports (check_node_types,
validate's ADR-6 check) are legal and not inspected; imports guarded by
`if TYPE_CHECKING:`, `try:` or `with` ARE module-level and are inspected."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

import sdlc.graph

GRAPH_DIR = Path(sdlc.graph.__file__).parent
STDLIB = "<stdlib>"

ALLOWED: dict[str, set[str]] = {
    "model.py": {STDLIB, "pydantic", "sdlc.core.models"},
    "payloads.py": {STDLIB},
    "node_types.py": {STDLIB, "pydantic", "sdlc.graph.model", "sdlc.graph.payloads"},
    "io.py": {STDLIB, "yaml", "sdlc.graph.model"},
    "topology.py": {STDLIB, "sdlc.graph.model"},
    "__init__.py": {
        STDLIB,
        "sdlc.graph.io",
        "sdlc.graph.model",
        "sdlc.graph.node_types",
        "sdlc.graph.payloads",
    },
}

_SKIPPED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _classify(module: str) -> str:
    root = module.split(".")[0]
    if root == "__future__" or root in sys.stdlib_module_names:
        return STDLIB
    if root == "sdlc":
        return module
    return root


def _module_level_imports(source: str) -> set[str]:
    """Every import outside a function or lambda body, at any nesting depth
    (so `if TYPE_CHECKING:`, `try:` and `with` blocks are included)."""
    found: set[str] = set()

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _SKIPPED_SCOPES):
                continue
            if isinstance(child, ast.Import):
                found.update(_classify(a.name) for a in child.names)
            elif isinstance(child, ast.ImportFrom):
                if child.level:
                    base = "sdlc.graph".split(".")[: 2 - (child.level - 1)]
                    module = ".".join(base + ([child.module] if child.module else []))
                else:
                    module = child.module or ""
                found.add(_classify(module))
            visit(child)

    visit(ast.parse(source))
    return found


def test_every_module_is_covered():
    found = {p.relative_to(GRAPH_DIR).as_posix() for p in GRAPH_DIR.rglob("*.py")}
    assert found == set(ALLOWED)


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_module_level_imports_are_pinned(name):
    imported = _module_level_imports((GRAPH_DIR / name).read_text(encoding="utf-8"))
    assert imported <= ALLOWED[name], sorted(imported - ALLOWED[name])


def test_walker_sees_guarded_imports_but_not_function_bodies():
    source = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    import sdlc.agents.roles\n"
        "try:\n"
        "    import temporalio\n"
        "except ImportError:\n"
        "    pass\n"
        "class K:\n"
        "    import yaml\n"
        "    def method(self):\n"
        "        import sdlc.benchmarks.heatmap\n"
        "def f():\n"
        "    from sdlc.stages import plan\n"
        "g = lambda: __import__('os')\n"
    )
    assert _module_level_imports(source) == {STDLIB, "sdlc.agents.roles", "temporalio", "yaml"}


def test_cold_import_pulls_in_no_heavy_packages():
    code = (
        "import sys, sdlc.graph; "
        "heavy = ('sdlc.benchmarks', 'sdlc.stages', 'sdlc.agents', 'temporalio'); "
        "print(sorted(m for m in sys.modules "
        "if any(m == h or m.startswith(h + '.') for h in heavy)))"
    )
    src_root = str(GRAPH_DIR.parents[1])
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([src_root, os.environ.get("PYTHONPATH", "")]),
    }
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
    )
    assert proc.stdout.strip() == "[]", proc.stdout + proc.stderr
