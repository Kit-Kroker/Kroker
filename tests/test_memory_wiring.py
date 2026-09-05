"""Structural check: every proposer stage recalls before running, retains
a stage summary after, gate decisions retain gate feedback, and the
fix-loop retains a gotcha on failure. AST-based like test_memory_purity.py
— a full time-skipping run would require faking the TemporalAgent
activity surface (see test_factory_purity.py's docstring for why that's
out of scope here)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from test_factory_purity import FEATURE_PY, _load_class, _methods

# Spec A "stage surgery": clarify's recall moved into the clarify slice
# (ctx.recall in step.py); _dev_task moved onto the TaskHost mixin.
CLARIFY_STEP_PY = (
    Path(__file__).resolve().parents[1] / "src" / "sdlc" / "stages" / "clarify" / "step.py"
)
ARCH_STEP_PY = (
    Path(__file__).resolve().parents[1] / "src" / "sdlc" / "stages" / "architecture" / "step.py"
)
PLAN_STEP_PY = Path(__file__).resolve().parents[1] / "src" / "sdlc" / "stages" / "plan" / "step.py"
CODE_STEP_PY = Path(__file__).resolve().parents[1] / "src" / "sdlc" / "stages" / "code" / "step.py"
TASK_HOST_PY = Path(__file__).resolve().parents[1] / "src" / "sdlc" / "workflows" / "task_host.py"


@pytest.fixture(scope="module")
def feature_class():
    source = FEATURE_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(FEATURE_PY))
    return _load_class(tree, "FeatureWorkflow")


@pytest.fixture(scope="module")
def task_host_class():
    source = TASK_HOST_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(TASK_HOST_PY))
    return _load_class(tree, "TaskHost")


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


def test_run_calls_recall_at_least_three_times_source_count(feature_class):
    methods = _methods(feature_class)
    # E-32: the pipeline body lives in _pipeline now (run wraps it + _retro).
    # Spec A: clarify, architecture, and plan recall moved into their slices
    # (ctx.recall in step.py).
    src = ast.unparse(methods["_pipeline"])
    slice_src = ast.unparse(ast.parse(CLARIFY_STEP_PY.read_text(encoding="utf-8")))
    arch_slice_src = ast.unparse(ast.parse(ARCH_STEP_PY.read_text(encoding="utf-8")))
    plan_slice_src = ast.unparse(ast.parse(PLAN_STEP_PY.read_text(encoding="utf-8")))
    assert (
        src.count("self._recall(")
        + slice_src.count("ctx.recall(")
        + arch_slice_src.count("ctx.recall(")
        + plan_slice_src.count("ctx.recall(")
        >= 3
    ), "expected recall before clarify/architect/plan at minimum"


def test_run_calls_retain_for_stage_summaries(feature_class):
    methods = _methods(feature_class)
    assert _calls_self_method(methods["_pipeline"], "_retain")


def test_gate_helper_retains_gate_feedback(feature_class):
    methods = _methods(feature_class)
    # E-42: _gate moved to GateHost; the retain is now in the _on_gate_decided
    # hook override, which runs for every gate decision (human, policy, timeout).
    assert "_on_gate_decided" in methods
    assert _calls_self_method(methods["_on_gate_decided"], "_retain")


def test_dev_task_retains_gotcha_on_fix_loop(task_host_class):
    methods = _methods(task_host_class)
    assert "_dev_task" in methods
    code_slice_src = CODE_STEP_PY.read_text(encoding="utf-8")
    assert _calls_self_method(methods["_dev_task"], "_retain") or "ctx.retain(" in code_slice_src
