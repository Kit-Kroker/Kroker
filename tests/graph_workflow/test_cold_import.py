"""A cold import of the interpreter survives the benchmarks<->stages cycle
(.workspace/tasks/2026-09-12-b0-lazy-step-export-shadowing.md)."""

from __future__ import annotations

import subprocess
import sys


def test_graph_workflow_module_imports_cold():
    r = subprocess.run(
        [sys.executable, "-c", "import sdlc.workflows.graph, sdlc.workflows.pipeline_child"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
