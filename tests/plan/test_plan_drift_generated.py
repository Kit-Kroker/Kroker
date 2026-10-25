"""Tests for plan_drift ignoring generated artifacts (017 T005, US5, FR-050)."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sdlc.core.models import (
    GateDecision,
    GateOutcome,
    HarnessKind,
    PipelineConfig,
)
from sdlc.harness.models import HarnessRunResult
from sdlc.stages import code
from sdlc.stages.code.models import HandoffClaim, HandoffSummary
from sdlc.stages.plan.models import (
    _DRIFT_V2,
    PLAN_DRIFT_PATCH,
    DevTask,
    ValidationContract,
    compute_plan_drift,
)
from sdlc.stages.qa.models import QAReport
from sdlc.stages.review.models import DeepReviewReport, ReviewReport


def _task(files_hint: list[str]) -> DevTask:
    return DevTask(
        id="t-1",
        title="Test task",
        description="Testing drift",
        acceptance_criteria=["AC1"],
        files_hint=files_hint,
    )


class _StubCtx:
    def __init__(self) -> None:
        self.recorded: list[dict] = []
        self.retained: list[dict] = []
        self.emitted: list[tuple] = []
        self.gates_called: list[str] = []
        self.stages_called: list[tuple[str, str]] = []

    async def gate(
        self,
        name: str,
        settings: dict,
        round: int = 1,
        context=None,
        default_policy=None,
    ) -> GateDecision:
        self.gates_called.append(name)
        return GateDecision(gate="task", outcome=GateOutcome.APPROVE, decided_by="human")

    async def record(self, cfg, record) -> None:
        self.recorded.append({"stage": record.stage, "outcome": record.outcome})

    async def retain(self, cfg, kind, bank, text, metadata=None) -> None:
        self.retained.append({"kind": kind, "text": text, "metadata": metadata})

    def emit(self, kind, **kwargs) -> None:
        self.emitted.append((kind, kwargs))

    def stage(self, status: str, stage_name: str) -> None:
        self.stages_called.append((status, stage_name))

    async def judge(self, cfg, artifact_json, stage, author_model):
        j = MagicMock()
        j.score = 1.0
        j.judge = "contract"
        return j


@pytest.mark.clause("MERGE-1.7")
def test_plan_drift_unfiltered_when_drop_generated_is_false():
    task = _task(["src/app.py"])
    touched = ["src/app.py", ".pytest_cache/v/cache/nodeids", "build/foo.egg-info/PKG-INFO"]
    drift = compute_plan_drift(task, touched, drop_generated=False)
    assert drift is not None
    assert drift.files_hinted == 1
    assert drift.files_touched == 3
    assert drift.hinted_untouched == []
    # Note: _norm_path strips leading '.', and touched_unhinted is sorted.
    assert drift.touched_unhinted == [
        "build/foo.egg-info/PKG-INFO",
        "pytest_cache/v/cache/nodeids",
    ]


@pytest.mark.clause("MERGE-1.7")
def test_plan_drift_filters_generated_when_drop_generated_is_true():
    task = _task(["src/app.py"])
    touched = [
        "src/app.py",
        ".pytest_cache/v/cache/nodeids",
        ".ruff_cache/content",
        "src/__pycache__/module.cpython-313.pyc",
        "build/lib.egg-info/SOURCES.txt",
    ]
    drift = compute_plan_drift(task, touched, drop_generated=True)
    assert drift is not None
    assert drift.files_hinted == 1
    assert drift.files_touched == 1
    assert drift.hinted_untouched == []
    assert drift.touched_unhinted == []


@pytest.mark.clause("MERGE-1.7")
def test_plan_drift_all_generated_yields_none():
    task = _task(["src/app.py"])
    touched = [
        ".pytest_cache/v/cache/nodeids",
        "__pycache__/module.cpython-313.pyc",
        "foo.egg-info/SOURCES.txt",
    ]
    drift = compute_plan_drift(task, touched, drop_generated=True)
    assert drift is None


@pytest.mark.clause("MERGE-1.7")
def test_plan_drift_empty_diff_or_no_hint_yields_none():
    task_no_hint = _task([])
    assert compute_plan_drift(task_no_hint, ["src/app.py"], drop_generated=True) is None
    assert compute_plan_drift(task_no_hint, ["src/app.py"], drop_generated=False) is None

    task_with_hint = _task(["src/app.py"])
    assert compute_plan_drift(task_with_hint, [], drop_generated=True) is None
    assert compute_plan_drift(task_with_hint, [], drop_generated=False) is None


@pytest.mark.clause("MERGE-1.7")
def test_plan_models_does_not_import_temporalio_at_module_level():
    """Layering: plan/models.py must stay pure without top-level temporalio import."""
    cmd = [
        sys.executable,
        "-c",
        "import sys, sdlc.stages.plan.models; "
        "assert 'temporalio' not in sys.modules, 'temporalio leaked'",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"stdout: {res.stdout}, stderr: {res.stderr}"


@pytest.mark.clause("MERGE-1.7")
def test_drift_v2_direct_call_and_patched_workflow():
    assert PLAN_DRIFT_PATCH == "017-plan-drift-generated"
    # When called outside a workflow, _DRIFT_V2 returns True directly
    assert _DRIFT_V2() is True

    # Inside a workflow runtime, _DRIFT_V2 calls workflow.patched
    with (
        patch("temporalio.workflow.in_workflow", return_value=True),
        patch("temporalio.workflow.patched", return_value=False) as mock_patched,
    ):
        res = _DRIFT_V2()
        assert res is False
        mock_patched.assert_called_once_with("017-plan-drift-generated")


@pytest.mark.clause("MERGE-1.7")
@pytest.mark.asyncio
async def test_code_step_drift_unpatched_passes_unfiltered_diff():
    """Pin the unpatched code-step path (patched -> False): generated files remain in drift."""
    ctx = _StubCtx()
    cfg = PipelineConfig()
    task = _task(["app.py"])
    contract = ValidationContract(task_id="t-1", assertions=["AC1"])

    run_result = HarnessRunResult(
        harness=HarnessKind.CLAUDE_CODE,
        exit_code=0,
        commit_sha="c1",
        cost_usd=0.5,
        summary="success",
    )
    qa_report = QAReport(tests_passed=True, issues=[])
    review_report = ReviewReport(approve=True, issues=[])
    deep_review = DeepReviewReport(verdict="LGTM", passed=True)
    handoff = HandoffSummary(
        task_id="t-1",
        files_touched=["app.py", ".pytest_cache/cache.json"],
        what_changed=[HandoffClaim(text="done", evidence="session")],
    )

    with (
        patch("sdlc.stages.code.step._DRIFT_V2", return_value=False),
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("sdlc.stages.code.step._run_handoff", new_callable=AsyncMock) as mock_ho,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = run_result
        mock_qa.return_value = qa_report
        mock_rev.return_value = review_report
        mock_deep.return_value = deep_review
        mock_ho.return_value = handoff
        mock_act.side_effect = [
            QAReport(tests_passed=True, issues=[]),  # qa_raw
            {"files": ["app.py", ".pytest_cache/cache.json"]},  # diff
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            contract=contract,
            worktree="/worktree",
            notes=["Note 1"],
            dev_agent=None,
            crew_layout=None,
            branch="feature-1",
        )

    assert tr.status == "done"
    assert tr.plan_drift is not None
    assert tr.plan_drift.files_touched == 2
    assert tr.plan_drift.touched_unhinted == ["pytest_cache/cache.json"]


@pytest.mark.clause("MERGE-1.7")
@pytest.mark.asyncio
async def test_code_step_drift_patched_filters_generated_diff():
    """Pin the patched code-step path (patched -> True): generated files are filtered out."""
    ctx = _StubCtx()
    cfg = PipelineConfig()
    task = _task(["app.py"])
    contract = ValidationContract(task_id="t-1", assertions=["AC1"])

    run_result = HarnessRunResult(
        harness=HarnessKind.CLAUDE_CODE,
        exit_code=0,
        commit_sha="c1",
        cost_usd=0.5,
        summary="success",
    )
    qa_report = QAReport(tests_passed=True, issues=[])
    review_report = ReviewReport(approve=True, issues=[])
    deep_review = DeepReviewReport(verdict="LGTM", passed=True)
    handoff = HandoffSummary(
        task_id="t-1",
        files_touched=["app.py", ".pytest_cache/cache.json"],
        what_changed=[HandoffClaim(text="done", evidence="session")],
    )

    with (
        patch("sdlc.stages.code.step._DRIFT_V2", return_value=True),
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("sdlc.stages.code.step._run_handoff", new_callable=AsyncMock) as mock_ho,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = run_result
        mock_qa.return_value = qa_report
        mock_rev.return_value = review_report
        mock_deep.return_value = deep_review
        mock_ho.return_value = handoff
        mock_act.side_effect = [
            QAReport(tests_passed=True, issues=[]),  # qa_raw
            {"files": ["app.py", ".pytest_cache/cache.json"]},  # diff
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            contract=contract,
            worktree="/worktree",
            notes=["Note 1"],
            dev_agent=None,
            crew_layout=None,
            branch="feature-1",
        )

    assert tr.status == "done"
    assert tr.plan_drift is not None
    assert tr.plan_drift.files_touched == 1
    assert tr.plan_drift.touched_unhinted == []
