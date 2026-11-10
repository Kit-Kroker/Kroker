"""Structural check: every proposer stage recalls before running, retains
a stage summary after, gate decisions retain gate feedback, and the
fix-loop retains a gotcha on failure. AST-based like test_memory_purity.py
â€” a full time-skipping run would require faking the durability-capability
activity surface (see test_factory_purity.py's docstring for why that's
out of scope here)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from test_factory_purity import _load_class, _methods

# Spec A "stage surgery": clarify's recall lives in the clarify slice
# (ctx.recall in step.py); _dev_task lives on the TaskHost mixin.
# 020 T026: the _pipeline terms are gone with FeatureWorkflow — the slices
# carry the counts, and the stage-summary retain points at the graph's
# StageServices wiring (precode.py's ctx.retain).
CLARIFY_STEP_PY = (
    Path(__file__).resolve().parents[1] / "src" / "sdlc" / "stages" / "clarify" / "step.py"
)
ARCH_STEP_PY = (
    Path(__file__).resolve().parents[1] / "src" / "sdlc" / "stages" / "architecture" / "step.py"
)
PLAN_STEP_PY = Path(__file__).resolve().parents[1] / "src" / "sdlc" / "stages" / "plan" / "step.py"
CODE_STEP_PY = Path(__file__).resolve().parents[1] / "src" / "sdlc" / "stages" / "code" / "step.py"
TASK_HOST_PY = Path(__file__).resolve().parents[1] / "src" / "sdlc" / "workflows" / "task_host.py"
RUN_HOST_PY = Path(__file__).resolve().parents[1] / "src" / "sdlc" / "workflows" / "run_host.py"


@pytest.fixture(scope="module")
def task_host_class():
    source = TASK_HOST_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(TASK_HOST_PY))
    return _load_class(tree, "TaskHost")


@pytest.fixture(scope="module")
def run_host_class():
    source = RUN_HOST_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(RUN_HOST_PY))
    return _load_class(tree, "RunHost")


def _calls_self_method(fn: ast.AST, method: str) -> bool:
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == method
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            return True
    return False


def test_the_slices_recall_at_least_three_times_source_count():
    """Spec A: clarify, architecture, and plan recall live in their slices
    (ctx.recall in step.py); 020 T026 drops the workflow term."""
    slice_src = ast.unparse(ast.parse(CLARIFY_STEP_PY.read_text(encoding="utf-8")))
    arch_slice_src = ast.unparse(ast.parse(ARCH_STEP_PY.read_text(encoding="utf-8")))
    plan_slice_src = ast.unparse(ast.parse(PLAN_STEP_PY.read_text(encoding="utf-8")))
    assert (
        slice_src.count("ctx.recall(")
        + arch_slice_src.count("ctx.recall(")
        + plan_slice_src.count("ctx.recall(")
        >= 3
    ), "expected recall before clarify/architect/plan at minimum"


def test_the_graph_retains_stage_summaries():
    """020 T026: the stage-summary retain lives in the graph's StageServices
    wiring — precode.py's ctx.retain call."""
    precode = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "sdlc"
        / "workflows"
        / "graph_nodes"
        / "precode.py"
    ).read_text(encoding="utf-8")
    assert "ctx.retain(" in precode or "_retain(" in precode


def test_gate_helper_retains_gate_feedback(run_host_class):
    methods = _methods(run_host_class)
    # E-42: _gate moved to GateHost; the retain is in the _on_gate_decided
    # hook override, which runs for every gate decision (human, policy, timeout).
    # E-74: _on_gate_decided hook extracted to the RunHost mixin.
    assert "_on_gate_decided" in methods
    assert _calls_self_method(methods["_on_gate_decided"], "_retain")


def test_dev_task_retains_gotcha_on_fix_loop(task_host_class):
    methods = _methods(task_host_class)
    assert "_dev_task" in methods
    code_slice_src = CODE_STEP_PY.read_text(encoding="utf-8")
    assert _calls_self_method(methods["_dev_task"], "_retain") or "ctx.retain(" in code_slice_src
