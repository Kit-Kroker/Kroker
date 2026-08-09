"""E-30: stage-12 wires the toolchain adapter and the worker registers it.

NOTE: ordering/count assertions use the AST (the sequence of activity names
passed to ``workflow.execute_activity``), not substring ``.find()``. The plan's
original substring form could not pass against its own code: the Step-6 comment
contains the literal ``measure_coverage`` (matched before the call site), and
the Temporal calling convention ``execute_activity(measure_coverage, Input(...))``
never yields a ``measure_coverage(`` token. The AST form verifies the same
stated intent robustly.
"""
import ast
import inspect
import pathlib

FEATURE = pathlib.Path(
    "src/sdlc/workflows/feature.py").read_text(encoding="utf-8")
_TREE = ast.parse(FEATURE)


def _build_and_merge_node():
    for n in ast.walk(_TREE):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_build_and_merge":
            return n
    raise AssertionError("_build_and_merge not found")


def _activity_calls_in_order(node) -> list[str]:
    """Names passed as the first arg to workflow.execute_activity(...), in
    source order. Robust to comments (a bare substring .find would match
    'measure_coverage' inside an explanatory comment)."""
    calls = [
        c for c in ast.walk(node)
        if isinstance(c, ast.Call)
        and isinstance(c.func, ast.Attribute)
        and c.func.attr == "execute_activity"
        and c.args and isinstance(c.args[0], ast.Name)
    ]
    calls.sort(key=lambda c: (c.lineno, c.col_offset))
    return [c.args[0].id for c in calls]


def test_merge_stage_runs_integration_checks_then_coverage_then_gate():
    order = _activity_calls_in_order(_build_and_merge_node())
    assert "run_integration_checks" in order, \
        "merge stage must call run_integration_checks"
    assert "measure_coverage" in order and "evaluate_gate" in order
    assert order.index("run_integration_checks") < order.index("measure_coverage"), \
        "coverage must be measured AFTER the integration test run"
    assert order.index("measure_coverage") < order.index("evaluate_gate"), \
        "coverage must be measured before the gate is evaluated"


def test_measure_coverage_called_exactly_once_in_pipeline():
    # It moved from analyze to merge — must not be left in both places.
    assert _activity_calls_in_order(_build_and_merge_node()).count(
        "measure_coverage") == 1


def test_worker_registers_run_integration_checks():
    from sdlc import worker
    assert "run_integration_checks" in inspect.getsource(worker)


def test_feature_imports_run_integration_checks():
    assert "run_integration_checks" in FEATURE
