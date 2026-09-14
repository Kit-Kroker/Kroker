"""E-72 import rules (spec §4): sdlc.graph must not open a new route into the
benchmarks <-> stages import cycle, so its MODULE-LEVEL imports are pinned.
Function-local imports (check_node_types) are legal and not inspected."""

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
    "__init__.py": {
        STDLIB,
        "sdlc.graph.io",
        "sdlc.graph.model",
        "sdlc.graph.node_types",
        "sdlc.graph.payloads",
    },
}


def _classify(module: str) -> str:
    root = module.split(".")[0]
    if root == "__future__" or root in sys.stdlib_module_names:
        return STDLIB
    if root == "sdlc":
        return module
    return root


def _top_level_imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Import):
            found |= {_classify(a.name) for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = "sdlc.graph".split(".")[: 2 - (node.level - 1)]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            found.add(_classify(module))
    return found


def test_every_module_is_covered():
    assert {p.name for p in GRAPH_DIR.glob("*.py")} == set(ALLOWED)


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_module_level_imports_are_pinned(name):
    imported = _top_level_imports(GRAPH_DIR / name)
    assert imported <= ALLOWED[name], sorted(imported - ALLOWED[name])


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
