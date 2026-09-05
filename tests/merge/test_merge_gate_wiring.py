import ast
import pathlib

import pytest

SRC = pathlib.Path("src/sdlc/stages/merge/step.py")
FEATURE_SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def _fn(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == name:
            return n
    raise AssertionError(f"function {name} not found")


@pytest.fixture(scope="module")
def step_src():
    return SRC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def step_tree(step_src):
    return ast.parse(step_src)


def test_merge_stage_calls_evaluate_gate_before_merge_verdict(step_tree, step_src):
    """SC-5: the deterministic gate is a hard precondition. Its activity
    call must textually precede any merge_verdict call in the pipeline."""
    run = _fn(step_tree, "step")
    src = ast.get_source_segment(step_src, run)
    assert src is not None
    g = src.find("evaluate_gate")
    v = src.find("merge_verdict")
    assert g != -1, "merge stage does not call evaluate_gate activity"
    if v != -1:
        assert g < v, "MergeVerdict consulted before DeterministicQualityGate"


def test_merge_stage_terminates_on_absolute_failure(step_src):
    """An absolute gate failure is terminal — the stage must return
    before any human-gate wait or MergeVerdict consult."""
    needle = "absolute-gate-failed"
    assert needle in step_src, (
        "merge stage must short-circuit on absolute gate failure "
        f"(looked for return marker containing {needle!r})"
    )


def test_feature_workflow_delegates_to_merge_step():
    f_src = FEATURE_SRC.read_text(encoding="utf-8")
    assert "merge.step" in f_src


from sdlc.gate import (
    CheckClass,
    GateOverride,
    build_check,
    evaluate_quality_gate,
)


def test_absolute_failure_blocks_despite_override():
    """SC-5: an absolute check failure cannot be waived by a human override."""
    checks = [
        build_check("build_integration_green", False, CheckClass.ABSOLUTE, detail="tests red")
    ]
    report = evaluate_quality_gate(
        checks,
        overrides=[
            GateOverride(check="build_integration_green", approved_by="human", reason="ship it")
        ],
    )
    assert not report.passed
    assert "build_integration_green" in report.blocking
    assert report.overridden == []


def test_advisory_failure_passes_with_audited_override():
    checks = [build_check("coverage_gate", False, CheckClass.ADVISORY)]
    report = evaluate_quality_gate(
        checks,
        overrides=[GateOverride(check="coverage_gate", approved_by="human", reason="accepted")],
    )
    assert report.passed
    assert "coverage_gate" in report.overridden


from sdlc.stages.qa.models import QAReport
from sdlc.workflows.feature import _merge_evidence_all_green
from sdlc.workflows.models import TaskResult


def test_merge_evidence_treats_missing_qa_as_failure():
    """SC-5: an escalation-approved task (qa=None) must NOT be filtered to a
    vacuous all([]) pass."""
    no_qa = TaskResult(task_id="t1", status="done", attempts=1, branch="b")
    assert not _merge_evidence_all_green([no_qa]), (
        "missing QA evidence must fail the merge absolute check"
    )


def test_merge_evidence_all_green_passes():
    ok = TaskResult(
        task_id="t1", status="done", attempts=1, branch="b", qa=QAReport(tests_passed=True)
    )
    assert _merge_evidence_all_green([ok])


def test_merge_evidence_one_failing_fails():
    ok = TaskResult(
        task_id="t1", status="done", attempts=1, branch="b", qa=QAReport(tests_passed=True)
    )
    bad = TaskResult(
        task_id="t2", status="done", attempts=1, branch="b", qa=QAReport(tests_passed=False)
    )
    assert not _merge_evidence_all_green([ok, bad])
