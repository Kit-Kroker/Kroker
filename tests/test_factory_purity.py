"""Structural purity check for the benchmark wiring.

We attempted a full time-skipping Temporal integration test, but the
proposer agents' TemporalAgent-generated ``model_request`` activities
(``agent__<name>_agent__model_request``) require faking an undocumented
pydantic-ai ``ModelResponse`` shape, and that proved intractable without
deeper research. Instead we regression-protect the production-safety
invariant STRUCTURALLY:

    When ``cfg.benchmark.case_id is None``, ``FeatureWorkflow`` must make
    ZERO ``record_benchmark`` and ZERO ``judge_artifact`` activity calls.

The invariant is enforced by two gated helpers — ``_record`` and ``_judge``
— whose FIRST statement is ``if not self._benchmarking(cfg): return``. These
tests assert (a) those guards exist and come first, and (b) the benchmark
activities are called ONLY through those helpers (no unguarded direct
``execute_activity`` calls anywhere else in the workflow). This catches the
realistic regression — someone adding a record/judge call on an unguarded
path — without depending on a brittle full-workflow runtime test.

A future hardening task can add the runtime time-skipping test once the
proposer agents honor ``cfg.roles`` (so a real worker can run the workflow
end-to-end with ``TestModel`` rather than faking the TemporalAgent
activity surface).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

FEATURE_PY = (Path(__file__).resolve().parents[1]
              / "src" / "sdlc" / "workflows" / "feature.py")

_BENCHMARK_ACTIVITIES = {"record_benchmark", "judge_artifact"}
_GATED_HELPERS = {"_record", "_judge"}


def _load_class(tree: ast.AST, class_name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    pytest.fail(f"class {class_name!r} not found in {FEATURE_PY}")


def _methods(cls: ast.ClassDef) -> dict[str, ast.AsyncFunctionDef]:
    out: dict[str, ast.AsyncFunctionDef] = {}
    for stmt in cls.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[stmt.name] = stmt
    return out


def _is_benchmarking_guard(stmt: ast.stmt) -> bool:
    """True iff ``stmt`` is ``if not self._benchmarking(cfg): return``."""
    if not isinstance(stmt, ast.If):
        return False
    test = stmt.test
    if not (isinstance(test, ast.UnaryOp)
            and isinstance(test.op, ast.Not)
            and isinstance(test.operand, ast.Call)):
        return False
    call = test.operand
    func = call.func
    return (isinstance(func, ast.Attribute)
            and func.attr == "_benchmarking"
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
            and len(call.args) == 1
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "cfg"
            and len(stmt.body) == 1
            and isinstance(stmt.body[0], ast.Return))


def _activity_names_in(stmt: ast.stmt) -> set[str]:
    """workflow.execute_activity(X, ...) activity names referenced in stmt."""
    names: set[str] = set()
    for node in ast.walk(stmt):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute)
                and func.attr == "execute_activity"
                and isinstance(func.value, ast.Name)
                and func.value.id == "workflow"):
            continue
        if node.args and isinstance(node.args[0], ast.Name):
            names.add(node.args[0].id)
    return names


def _benchmarking_guard_precedes_activity(
        fn: ast.FunctionDef | ast.AsyncFunctionDef,
        activity_name: str) -> bool:
    """True iff a ``_benchmarking`` early-return guard appears in the function
    body BEFORE the first ``execute_activity(activity_name, ...)`` call. (The
    guard may be preceded by setup like a fallback assignment.)"""
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value,
                                                             ast.Constant):
        body = body[1:]      # skip docstring
    guard_seen = False
    for stmt in body:
        if not guard_seen and _is_benchmarking_guard(stmt):
            guard_seen = True
        if activity_name in _activity_names_in(stmt):
            return guard_seen
    # no activity call found in this function — nothing to protect
    return True


def _activity_calls_in_method(fn: ast.FunctionDef | ast.AsyncFunctionDef
                              ) -> set[str]:
    """Names of all activities invoked via workflow.execute_activity(X, ...)
    anywhere in ``fn`` (walked, not just top-level)."""
    names: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute)
                and func.attr == "execute_activity"
                and isinstance(func.value, ast.Name)
                and func.value.id == "workflow"):
            continue
        if node.args and isinstance(node.args[0], ast.Name):
            names.add(node.args[0].id)
    return names


@pytest.fixture(scope="module")
def feature_class() -> ast.ClassDef:
    source = FEATURE_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(FEATURE_PY))
    return _load_class(tree, "FeatureWorkflow")


def test_record_helper_is_guarded(feature_class):
    methods = _methods(feature_class)
    assert "_record" in methods, "_record helper missing"
    assert _benchmarking_guard_precedes_activity(methods["_record"],
                                                 "record_benchmark"), (
        "_record must guard its record_benchmark call with "
        "`if not self._benchmarking(cfg): return` BEFORE the call — this is "
        "the production purity invariant (no recorder calls when case_id is "
        "None)")


def test_judge_helper_is_guarded(feature_class):
    methods = _methods(feature_class)
    assert "_judge" in methods, "_judge helper missing"
    assert _benchmarking_guard_precedes_activity(methods["_judge"],
                                                 "judge_artifact"), (
        "_judge must guard its judge_artifact call with "
        "`if not self._benchmarking(cfg): return <fallback>` BEFORE the call "
        "— this is the production purity invariant (no judge calls when "
        "case_id is None)")


def test_benchmark_activities_only_called_through_gated_helpers(
        feature_class):
    """No direct ``workflow.execute_activity(record_benchmark/judge_artifact,
    ...)`` calls outside ``_record``/``_judge``. Prevents an unguarded
    call sneaking in on any other code path."""
    methods = _methods(feature_class)
    for name, fn in methods.items():
        if name in _GATED_HELPERS:
            continue
        calls = _activity_calls_in_method(fn) & _BENCHMARK_ACTIVITIES
        assert not calls, (
            f"method {name!r} calls benchmark activity/activities {calls} "
            f"directly — benchmark activities must only be invoked through "
            f"the gated _record/_judge helpers")


def test_gated_helpers_call_the_right_activities(feature_class):
    """_record calls record_benchmark; _judge calls judge_artifact."""
    methods = _methods(feature_class)
    assert "record_benchmark" in _activity_calls_in_method(methods["_record"])
    assert "judge_artifact" in _activity_calls_in_method(methods["_judge"])


def test_benchmarking_predicate_is_the_case_id_check(feature_class):
    """The guard predicate must actually check case_id (the v1 'benchmarking
    on' signal). If someone redefines _benchmarking to always-True, every
    production run would emit records."""
    methods = _methods(feature_class)
    assert "_benchmarking" in methods, "_benchmarking predicate missing"
    src = ast.unparse(methods["_benchmarking"])
    assert "case_id" in src, (
        "_benchmarking must gate on cfg.benchmark.case_id; predicate was: "
        f"{src!r}")
