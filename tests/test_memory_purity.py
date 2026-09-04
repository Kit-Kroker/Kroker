"""Structural purity check for memory wiring — same approach as
test_factory_purity.py's benchmark guard, applied to recall/retain."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from test_factory_purity import (
    FEATURE_PY,
    _activity_calls_in_method,
    _load_class,
    _methods,
)

# Spec A "stage surgery": _recall/_retain moved off FeatureWorkflow onto the
# MemoryHost mixin; the workflow composes it via its MRO.
MEMORY_HOST_PY = (
    Path(__file__).resolve().parents[1] / "src" / "sdlc" / "workflows" / "memory_host.py"
)

_MEMORY_ACTIVITIES = {"recall_snapshot", "retain"}
_GATED_HELPERS = {"_recall", "_retain"}


@pytest.fixture(scope="module")
def feature_class():
    source = FEATURE_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(FEATURE_PY))
    return _load_class(tree, "FeatureWorkflow")


@pytest.fixture(scope="module")
def memory_host_class():
    source = MEMORY_HOST_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MEMORY_HOST_PY))
    return _load_class(tree, "MemoryHost")


def _is_memory_enabled_guard(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.If):
        return False
    test = stmt.test
    if not (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)):
        return False
    src = ast.unparse(test.operand)
    return (
        src in ("cfg.memory.enabled",)
        and len(stmt.body) == 1
        and isinstance(stmt.body[0], ast.Return)
    )


def test_recall_helper_is_guarded(memory_host_class):
    methods = _methods(memory_host_class)
    assert "_recall" in methods
    body = methods["_recall"].body
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    assert any(_is_memory_enabled_guard(s) for s in body)


def test_retain_helper_is_guarded(memory_host_class):
    methods = _methods(memory_host_class)
    assert "_retain" in methods
    body = methods["_retain"].body
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    assert any(_is_memory_enabled_guard(s) for s in body)


def test_memory_activities_only_called_through_gated_helpers(feature_class, memory_host_class):
    for cls in (feature_class, memory_host_class):
        methods = _methods(cls)
        for name, fn in methods.items():
            if name in _GATED_HELPERS:
                continue
            calls = _activity_calls_in_method(fn) & _MEMORY_ACTIVITIES
            assert not calls, (
                f"method {name!r} calls memory activity/activities {calls} "
                f"directly — must go through _recall/_retain"
            )
