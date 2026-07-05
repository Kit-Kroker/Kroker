"""Structural check: every proposer stage recalls before running, retains
a stage summary after, gate decisions retain gate feedback, and the
fix-loop retains a gotcha on failure. AST-based like test_memory_purity.py
— a full time-skipping run would require faking the TemporalAgent
activity surface (see test_factory_purity.py's docstring for why that's
out of scope here)."""
from __future__ import annotations

import ast

import pytest

from test_factory_purity import FEATURE_PY, _load_class, _methods


@pytest.fixture(scope="module")
def feature_class():
    source = FEATURE_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(FEATURE_PY))
    return _load_class(tree, "FeatureWorkflow")


def _calls_self_method(fn: ast.AST, method: str) -> bool:
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == method
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"):
            return True
    return False


def test_run_calls_recall_at_least_three_times_source_count(feature_class):
    methods = _methods(feature_class)
    src = ast.unparse(methods["run"])
    assert src.count("self._recall(") >= 3, (
        "expected recall before clarify/architect/plan at minimum")


def test_run_calls_retain_for_stage_summaries(feature_class):
    methods = _methods(feature_class)
    assert _calls_self_method(methods["run"], "_retain")


def test_gate_helper_retains_gate_feedback(feature_class):
    methods = _methods(feature_class)
    assert "_gate" in methods
    assert _calls_self_method(methods["_gate"], "_retain")


def test_dev_task_retains_gotcha_on_fix_loop(feature_class):
    methods = _methods(feature_class)
    assert "_dev_task" in methods
    assert _calls_self_method(methods["_dev_task"], "_retain")
