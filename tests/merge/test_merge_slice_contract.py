"""Merge stage slice contract test (spec A §3.3)."""

from __future__ import annotations

import inspect
import pathlib
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.benchmarks.models import BenchmarkOutcome
from sdlc.core.models import (
    GateConfig,
    GateDecision,
    GateOutcome,
    GatePolicy,
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
)
from sdlc.gate import CheckClass, CheckResult, GateReport
from sdlc.stages import merge
from sdlc.stages.merge.activities import (
    evaluate_gate,
    measure_coverage,
    open_pull_request,
    run_integration_checks,
)
from sdlc.stages.merge.models import MergeVerdict
from sdlc.stages.qa.models import QAReport
from sdlc.stages.review.models import ReviewReport
from sdlc.workflows.models import TaskResult


class _StubRoleOutput:
    def __init__(self, output: MergeVerdict) -> None:
        self.output = output


class _StubCtx:
    def __init__(
        self,
        gate_decision: GateDecision | None = None,
        verdict: MergeVerdict | None = None,
    ) -> None:
        self.gate_decision = gate_decision or GateDecision(
            gate="merge", outcome=GateOutcome.APPROVE, decided_by="human"
        )
        self.verdict = verdict or MergeVerdict(
            approve=True, confidence=0.95, rationale="looks good"
        )
        self.recorded: list[dict] = []
        self.retained: list[dict] = []
        self.emitted: list[tuple] = []
        self.gates_called: list[str] = []
        self.roles_called: list[str] = []

    async def gate(self, name: str, settings: dict, context=None) -> GateDecision:
        self.gates_called.append(name)
        return self.gate_decision

    async def run_role(self, cfg, role, model, agent, prompt, into=None):
        self.roles_called.append(role)
        return _StubRoleOutput(self.verdict)

    async def record(self, cfg, record) -> None:
        self.recorded.append({"stage": record.stage, "outcome": record.outcome})

    async def retain(self, cfg, kind, bank, text, metadata=None) -> None:
        self.retained.append({"kind": kind, "text": text, "metadata": metadata})

    def emit(self, kind, **kwargs) -> None:
        self.emitted.append((kind, kwargs))


@pytest.mark.clause("MERGE-1.1")
def test_slice_exports_step_and_activities():
    assert callable(merge.step)
    assert callable(merge.prompt_digest)
    assert callable(merge.merge_verdict_prompt)
    assert isinstance(merge.ACTIVITIES, list)
    assert measure_coverage in merge.ACTIVITIES
    assert run_integration_checks in merge.ACTIVITIES
    assert open_pull_request in merge.ACTIVITIES
    assert evaluate_gate in merge.ACTIVITIES

    params = inspect.signature(merge.step).parameters
    param_names = list(params)
    assert param_names[0] == "ctx"
    assert "cfg" in param_names
    assert "task_results" in param_names
    assert "integration_wt" in param_names
    assert "idea" in param_names

    src = pathlib.Path("src/sdlc/stages/merge/step.py").read_text(encoding="utf-8")
    assert "@workflow.defn" not in src
    assert "@workflow.signal" not in src
    assert "@workflow.query" not in src


@pytest.mark.clause("MERGE-1.2")
@pytest.mark.asyncio
async def test_merge_fails_closed_on_absolute_gate_failure():
    ctx = _StubCtx()
    cfg = PipelineConfig()
    idea = IdeaBrief(
        title="Feature",
        description="Test",
        repo_url="/repo",
        mode=ProjectMode.GREENFIELD,
    )
    results = [TaskResult(task_id="t1", status="done", attempts=1, branch="b", qa=None)]

    # Mock evaluate_gate to simulate absolute check failure
    failing_gate = GateReport(
        passed=False,
        checks=[
            CheckResult(
                name="build_integration_green",
                passed=False,
                classification=CheckClass.ABSOLUTE,
                detail="missing QA",
            )
        ],
        blocking=["build_integration_green"],
        overridden=[],
    )

    with (
        patch("sdlc.stages.merge.step.evaluate_gate", new_callable=AsyncMock) as mock_eg,
        patch("sdlc.stages.merge.step.run_integration_checks", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.measure_coverage", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.security_scan", new_callable=AsyncMock),
    ):
        mock_eg.return_value = failing_gate
        res = await merge.step(
            ctx,
            cfg=cfg,
            task_results=results,
            integration_wt="/wt",
            idea=idea,
        )

    assert isinstance(res, str)
    assert res.startswith("rejected:merge:absolute-gate-failed")
    assert "build_integration_green" in res
    assert len(ctx.gates_called) == 0
    assert any(r["outcome"] == BenchmarkOutcome.FAIL for r in ctx.recorded)


@pytest.mark.clause("MERGE-1.3")
@pytest.mark.asyncio
async def test_merge_advisory_failure_presents_to_human_gate():
    ctx = _StubCtx(
        gate_decision=GateDecision(
            gate="merge",
            outcome=GateOutcome.APPROVE,
            decided_by="human",
            reviewer="lead",
            comments="waived",
        )
    )
    cfg = PipelineConfig()
    idea = IdeaBrief(
        title="Feature",
        description="Test",
        repo_url="/repo",
        mode=ProjectMode.GREENFIELD,
    )
    results = [
        TaskResult(
            task_id="t1",
            status="done",
            attempts=1,
            branch="b",
            qa=QAReport(tests_passed=True),
            review=ReviewReport(approve=False),
        )
    ]

    failing_advisory = GateReport(
        passed=False,
        checks=[
            CheckResult(
                name="review_severity",
                passed=False,
                classification=CheckClass.ADVISORY,
                detail="blocking finding",
            )
        ],
        blocking=["review_severity"],
        overridden=[],
    )
    passing_gate = GateReport(
        passed=True,
        checks=[
            CheckResult(
                name="review_severity",
                passed=True,
                classification=CheckClass.ADVISORY,
                detail="waived",
            )
        ],
        blocking=[],
        overridden=["review_severity"],
    )

    with (
        patch("sdlc.stages.merge.step.evaluate_gate", new_callable=AsyncMock) as mock_eg,
        patch("sdlc.stages.merge.step.run_integration_checks", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.measure_coverage", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.security_scan", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.open_pull_request", new_callable=AsyncMock) as mock_pr,
    ):
        mock_eg.side_effect = [failing_advisory, passing_gate]
        mock_pr.return_value = "https://github.com/org/repo/pull/123"

        res = await merge.step(
            ctx,
            cfg=cfg,
            task_results=results,
            integration_wt="/wt",
            idea=idea,
        )

    assert res == "https://github.com/org/repo/pull/123"
    assert "merge" in ctx.gates_called
    assert any(r["outcome"] == BenchmarkOutcome.REVISED for r in ctx.recorded)


@pytest.mark.clause("MERGE-1.4")
@pytest.mark.asyncio
async def test_merge_soft_policy_consults_verdict():
    verdict = MergeVerdict(approve=False, confidence=0.3, rationale="risk detected")
    ctx = _StubCtx(
        gate_decision=GateDecision(gate="merge", outcome=GateOutcome.REJECT, decided_by="human"),
        verdict=verdict,
    )
    cfg = PipelineConfig(gates={"merge": GateConfig(policy=GatePolicy.SOFT)})
    idea = IdeaBrief(
        title="Feature",
        description="Test",
        repo_url="/repo",
        mode=ProjectMode.GREENFIELD,
    )
    results = [
        TaskResult(
            task_id="t1",
            status="done",
            attempts=1,
            branch="b",
            qa=QAReport(tests_passed=True),
        )
    ]

    passing_gate = GateReport(passed=True, checks=[], blocking=[], overridden=[])

    with (
        patch("sdlc.stages.merge.step.evaluate_gate", new_callable=AsyncMock) as mock_eg,
        patch("sdlc.stages.merge.step.run_integration_checks", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.measure_coverage", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.security_scan", new_callable=AsyncMock),
    ):
        mock_eg.return_value = passing_gate
        res = await merge.step(
            ctx,
            cfg=cfg,
            task_results=results,
            integration_wt="/wt",
            idea=idea,
            merge_agent=object(),
        )

    assert "merge_verdict" in ctx.roles_called
    assert "merge" in ctx.gates_called
    assert res == "rejected:merge:soft-verdict"


@pytest.mark.clause("MERGE-1.5")
@pytest.mark.asyncio
async def test_merge_success_creates_pr():
    ctx = _StubCtx()
    cfg = PipelineConfig()
    idea = IdeaBrief(
        title="Feature",
        description="Test",
        repo_url="/repo",
        mode=ProjectMode.GREENFIELD,
    )
    results = [
        TaskResult(
            task_id="t1",
            status="done",
            attempts=1,
            branch="b",
            qa=QAReport(tests_passed=True),
        )
    ]
    passing_gate = GateReport(passed=True, checks=[], blocking=[], overridden=[])

    with (
        patch("sdlc.stages.merge.step.evaluate_gate", new_callable=AsyncMock) as mock_eg,
        patch("sdlc.stages.merge.step.run_integration_checks", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.measure_coverage", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.security_scan", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.open_pull_request", new_callable=AsyncMock) as mock_pr,
    ):
        mock_eg.return_value = passing_gate
        mock_pr.return_value = "https://github.com/org/repo/pull/999"

        res = await merge.step(
            ctx,
            cfg=cfg,
            task_results=results,
            integration_wt="/wt",
            idea=idea,
        )

    assert res == "https://github.com/org/repo/pull/999"
    assert any(r["outcome"] == BenchmarkOutcome.PASS for r in ctx.recorded)
