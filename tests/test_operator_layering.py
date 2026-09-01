"""Spec D3: the tool layer must stay framework-free so E-11 can reuse it.

Two checks, because the syntactic one alone is not the property we care
about. The original version of this test only parsed import statements, so
it passed while `from ..cli import slug` -- one regex helper -- transitively
loaded pydantic_ai, temporalio and the whole agent registry, constructing
every TemporalAgent at import time. What matters is what ACTUALLY loads.
"""

import ast
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "sdlc" / "operator"
FORBIDDEN = ("pydantic_ai", "fastapi", "starlette")


def imported_roots(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    return roots


def test_only_agent_py_may_name_a_framework():
    for path in SRC.glob("*.py"):
        if path.name == "agent.py":
            continue
        offenders = imported_roots(path) & set(FORBIDDEN)
        assert not offenders, f"{path.name} imports {offenders}"


def test_agent_py_is_the_one_that_does():
    assert "pydantic_ai" in imported_roots(SRC / "agent.py")


def test_importing_tools_does_not_load_a_framework_transitively():
    """The check that has teeth: import tools in a clean interpreter and see
    what came with it. Runs in a subprocess because pytest has already
    imported half the world into this one."""
    probe = (
        "import sys; import sdlc.operator.tools; "
        "print(','.join(sorted(m for m in "
        "('pydantic_ai', 'fastapi', 'starlette', 'temporalio') "
        "if m in sys.modules)))"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, cwd=REPO, timeout=300
    )
    assert out.returncode == 0, out.stderr
    loaded = [m for m in out.stdout.strip().split(",") if m]
    assert loaded == [], (
        f"importing sdlc.operator.tools loaded {loaded}; E-11's MCP server "
        f"imports this module expecting a leaf"
    )
