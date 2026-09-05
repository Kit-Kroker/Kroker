"""Code stage slice contract test (spec A §3.3)."""

from __future__ import annotations

import inspect
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sdlc.benchmarks.models import BenchmarkOutcome
from sdlc.core.models import (
    GateDecision,
    GateOutcome,
    HarnessKind,
    PipelineConfig,
)
from sdlc.harness.models import HarnessRunResult
from sdlc.stages import code
from sdlc.stages.code.activities import (
    run_coding_task,
)
from sdlc.stages.code.models import HandoffClaim, HandoffSummary
from sdlc.stages.plan.models import DevTask, ValidationContract
from sdlc.stages.qa.models import QAReport
from sdlc.stages.review.models import DeepReviewReport, ReviewReport
from sdlc.workflows.models import TaskResult


class _StubCtx:
    def __init__(
        self,
        gate_decisions: list[GateDecision] | None = None,
    ) -> None:
        self.gate_decisions = gate_decisions or [
            GateDecision(gate="task", outcome=GateOutcome.APPROVE, decided_by="human")
        ]
        self.gate_call_count = 0
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
        decision = self.gate_decisions[min(self.gate_call_count, len(self.gate_decisions) - 1)]
        self.gate_call_count += 1
        return decision

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


@pytest.mark.clause("CODE-1.1")
def test_slice_exports_step_and_activities():
    assert callable(code.step)
    assert callable(code.prompt_digest)
    assert isinstance(code.ACTIVITIES, list)
    assert run_coding_task in code.ACTIVITIES

    params = inspect.signature(code.step).parameters
    param_names = list(params)
    assert param_names[0] == "ctx"
    assert "cfg" in param_names
    assert "task" in param_names
    assert "contract" in param_names
    assert "worktree" in param_names
    assert "notes" in param_names
    assert "dev_agent" in param_names
    assert "crew_layout" in param_names


@pytest.mark.clause("CODE-1.2")
def test_code_step_pure_over_inputs():
    src = pathlib.Path("src/sdlc/stages/code/step.py").read_text(encoding="utf-8")
    assert "@workflow.defn" not in src
    assert "@workflow.signal" not in src
    assert "@workflow.query" not in src


@pytest.mark.clause("CODE-1.3")
@pytest.mark.asyncio
async def test_code_step_executes_and_returns_task_result():
    ctx = _StubCtx()
    cfg = PipelineConfig()
    task = DevTask(
        id="task-1",
        title="Implement feature",
        description="Write code",
        role="dev",
        acceptance_criteria=["Tests pass"],
    )
    contract = ValidationContract(task_id="task-1", assertions=["Tests pass"])

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
        task_id="task-1",
        files_touched=["app.py"],
        what_changed=[HandoffClaim(text="done", evidence="session")],
    )

    with (
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
            {"files": ["app.py"]},  # diff
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

    assert isinstance(tr, TaskResult)
    assert tr.status == "done"
    assert tr.task_id == "task-1"
    assert tr.branch == "feature-1"
    assert any(r["stage"] == "code" and r["outcome"] == BenchmarkOutcome.PASS for r in ctx.recorded)


@pytest.mark.clause("CODE-1.4")
@pytest.mark.asyncio
async def test_code_step_records_benchmark_records():
    ctx = _StubCtx()
    cfg = PipelineConfig()
    task = DevTask(
        id="task-2",
        title="Add auth",
        description="Auth",
        role="dev",
        acceptance_criteria=["auth ok"],
    )

    run_result = HarnessRunResult(
        harness=HarnessKind.CLAUDE_CODE,
        exit_code=0,
        commit_sha="c2",
        cost_usd=0.2,
        summary="auth ok",
    )
    qa_report = QAReport(tests_passed=True, issues=[])
    review_report = ReviewReport(approve=True, issues=[])

    with (
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
        mock_deep.return_value = None
        mock_ho.return_value = HandoffSummary(task_id="task-2")
        mock_act.side_effect = [
            QAReport(tests_passed=True, issues=[]),
            {"files": ["auth.py"]},
        ]

        await code.step(
            ctx,
            cfg=cfg,
            task=task,
            worktree="/worktree",
            notes=[],
            dev_agent=None,
            crew_layout=None,
        )

    stages_recorded = [r["stage"] for r in ctx.recorded]
    assert "code" in stages_recorded
    assert "qa" in stages_recorded


@pytest.mark.clause("CODE-1.5")
@pytest.mark.asyncio
async def test_code_step_escalates_to_task_gate_on_exhaustion():
    ctx = _StubCtx(
        gate_decisions=[
            GateDecision(gate="task:task-3", outcome=GateOutcome.REJECT, decided_by="human")
        ]
    )
    cfg = PipelineConfig(max_fix_attempts=1)
    task = DevTask(
        id="task-3",
        title="Buggy task",
        description="Fails",
        role="dev",
        acceptance_criteria=["works"],
    )

    run_result = HarnessRunResult(
        harness=HarnessKind.CLAUDE_CODE,
        exit_code=1,
        commit_sha="c3",
        cost_usd=0.1,
        summary="failed",
    )
    qa_failing = QAReport(tests_passed=False, issues=["tests failed"])
    review_report = ReviewReport(approve=False, issues=["tests red"])

    with (
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = run_result
        mock_qa.return_value = qa_failing
        mock_rev.return_value = review_report
        mock_deep.return_value = None
        mock_act.side_effect = [
            QAReport(tests_passed=False, issues=["failure"]),
            {"files": ["buggy.py"]},
            QAReport(tests_passed=False, issues=["failure"]),
            {"files": ["buggy.py"]},
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            worktree="/worktree",
            notes=[],
            dev_agent=None,
            crew_layout=None,
            branch="buggy-branch",
        )

    assert tr.status == "quarantined"
    assert "task:task-3" in ctx.gates_called
