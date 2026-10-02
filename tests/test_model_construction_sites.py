"""Regression guard for spec A2/FR-016 C7 - every model-string construction
site goes through the shared seam.

pydantic-ai's ``Agent`` infers the model eagerly from a string unless a
model-id resolver capability is present, so a ``zai:...`` string only reaches
the coding endpoint if it passes through ``sdlc.agents.model_ids`` (plan D1).
That seam only holds if the ``Agent(...)`` / ``infer_model(...)`` /
``infer_provider(...)`` call sites stay enumerated: the seven construction
sites of plan D2 (``src/sdlc/agents/loader.py``, ``src/sdlc/agents/roles.py``,
``src/sdlc/stages/research/stage.py``, ``src/sdlc/eval/runner.py``,
``src/sdlc/benchmarks/judge.py``, ``src/sdlc/operator/agent.py``), the
``src/sdlc/agents/model_ids.py`` seam itself, and the 14
``agents/<role>/agent.py`` registry build functions (which only receive what
sites 1, 2 and 5 hand them).

Two assertions:

1. The AST scan of ``src/sdlc/**/*.py`` and ``agents/**/*.py`` finds no
   construction call outside that allow-list (GREEN on main today).
2. The three string-holding sites - eval runner, benchmark judge, operator
   chat - each reference ``resolve_model`` in their source (RED until tasks
   T011/T012/T013 wire the seam in).
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (ROOT / "src" / "sdlc", ROOT / "agents")
CONSTRUCTION_CALLS = {"Agent", "infer_model", "infer_provider"}

# Plan D2's seven sites, the model_ids seam, and the agents/<role>/agent.py
# build functions (matched structurally, so a new role is covered too).
ALLOW_LISTED = {
    "src/sdlc/agents/loader.py",
    "src/sdlc/agents/roles.py",
    "src/sdlc/stages/research/stage.py",
    "src/sdlc/eval/runner.py",
    "src/sdlc/benchmarks/judge.py",
    "src/sdlc/operator/agent.py",
    "src/sdlc/agents/model_ids.py",
}

# Sites 5, 6, 7 of plan D2 - the ones that hold a bare string today.
RESOLVE_MODEL_SITES = (
    "src/sdlc/eval/runner.py",
    "src/sdlc/benchmarks/judge.py",
    "src/sdlc/operator/agent.py",
)


def _call_name(func: ast.expr) -> str | None:
    """Name of a called function, for plain names and attribute accesses."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_allow_listed(rel_posix: str) -> bool:
    if rel_posix in ALLOW_LISTED:
        return True
    parts = rel_posix.split("/")
    return len(parts) == 3 and parts[0] == "agents" and parts[2] == "agent.py"


def _construction_sites() -> list[tuple[str, int, str]]:
    """Every (file, line, name) construction call under the scan roots."""
    hits: list[tuple[str, int, str]] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _call_name(node.func)
                if name in CONSTRUCTION_CALLS:
                    hits.append((path.relative_to(ROOT).as_posix(), node.lineno, name))
    return hits


def test_construction_sites_stay_allow_listed():
    offenders = [site for site in _construction_sites() if not _is_allow_listed(site[0])]
    assert not offenders, (
        "model-construction call(s) outside the plan D2 allow-list - "
        "every Agent/infer_model/infer_provider call must live in one of the "
        "seven construction sites, src/sdlc/agents/model_ids.py, or an "
        "agents/<role>/agent.py build function, so the model string reaches "
        "the shared seam:\n" + "\n".join(f"  - {f}:{ln} {n}" for f, ln, n in offenders)
    )


def test_string_model_sites_route_through_resolve_model():
    for rel in RESOLVE_MODEL_SITES:
        path = ROOT / rel
        assert path.exists(), f"{rel} is a plan D2 construction site; it must exist"
        source = path.read_text(encoding="utf-8")
        assert "resolve_model" in source, (
            f"{rel} builds its agent from a bare model string - route it "
            f"through sdlc.agents.model_ids.resolve_model so zai: model ids "
            f"reach the coding endpoint (plan D2 sites 5-7)"
        )
