"""012 T020 (RED): every merge rejection is on the record (contract §6.2).

At base the absolute-failure record carries NO error text, and the
advisory (step.py:526) and soft-verdict (step.py:591) returns write NO
record at all — a merge record with quality 0.0 and no cause. These
tests capture the REAL record objects (not the slice-contract dict
projection) so the error assertions read actual fields.
"""

from __future__ import annotations

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
from sdlc.stages.merge.models import MergeVerdict
from sdlc.stages.qa.models import QAReport
from sdlc.workflows.models import TaskResult
from tests.merge.test_merge_slice_contract import _lenses_ran, _StubCtx


class _FullRecordCtx(_StubCtx):
    """_StubCtx keeps only {stage, outcome}; these tests need the record's
    error and quality, so keep the object too."""

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.full_records: list = []

    async def record(self, cfg, record) -> None:
        self.full_records.append(record)
        await super().record(cfg, record)


def _merge_records(ctx):
    return [r for r in ctx.full_records if r.stage == "merge"]


def _idea():
    return IdeaBrief(
        title="Feature", description="T", repo_url="/repo", mode=ProjectMode.GREENFIELD
    )


def _results():
    return [
        TaskResult(
            task_id="t1",
            status="done",
            attempts=1,
            branch="b",
            qa=QAReport(tests_passed=True),
            lens_outcomes=_lenses_ran(),
        )
    ]


def _gate_ctx(outcome=GateOutcome.REJECT):
    return _FullRecordCtx(
        gate_decision=GateDecision(gate="merge", outcome=outcome, decided_by="human", comments="no")
    )


# --- (1) the absolute record names what blocked (contract §6.2) --------------


@pytest.mark.asyncio
async def test_absolute_rejection_record_names_the_blocking_checks():
    failing = GateReport(
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
    ctx = _gate_ctx()
    with (
        patch("sdlc.stages.merge.step.evaluate_gate", new_callable=AsyncMock) as mock_eg,
        patch("sdlc.stages.merge.step.run_integration_checks", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.measure_coverage", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.scoped_security_scan", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.prepare_base_worktree", new_callable=AsyncMock),
    ):
        mock_eg.return_value = failing
        res = await merge.step(
            ctx,
            cfg=PipelineConfig(),
            task_results=_results(),
            integration_wt="/wt",
            idea=_idea(),
        )

    assert res.startswith("rejected:merge:absolute-gate-failed:")
    assert "build_integration_green" in res
    recs = _merge_records(ctx)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.quality.score == 0.0
    assert rec.outcome is BenchmarkOutcome.FAIL
    assert rec.error is not None, "the absolute record must name what blocked"
    assert "build_integration_green" in rec.error


# --- (2) the advisory rejection writes one record before the return ----------


@pytest.mark.asyncio
async def test_advisory_rejection_writes_one_record_naming_the_kind():
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
    ctx = _gate_ctx()  # the human gate does NOT approve
    with (
        patch("sdlc.stages.merge.step.evaluate_gate", new_callable=AsyncMock) as mock_eg,
        patch("sdlc.stages.merge.step.run_integration_checks", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.measure_coverage", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.scoped_security_scan", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.prepare_base_worktree", new_callable=AsyncMock),
    ):
        mock_eg.return_value = failing_advisory
        res = await merge.step(
            ctx,
            cfg=PipelineConfig(),
            task_results=_results(),
            integration_wt="/wt",
            idea=_idea(),
        )

    # the returned string is UNCHANGED
    assert res == "rejected:merge:advisory"
    # exactly ONE merge record, before the return, naming kind and checks
    recs = _merge_records(ctx)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.quality.score == 0.0
    assert rec.outcome is BenchmarkOutcome.FAIL
    assert rec.error is not None and "advisory" in rec.error
    assert "review_severity" in rec.error
    # GATE_DECIDED belongs to the override path, not this one
    assert all(str(kind) != "GATE_DECIDED" for kind, _kw in ctx.emitted)


# --- (3) the soft-verdict rejection writes one record before the return ------


@pytest.mark.asyncio
async def test_soft_verdict_rejection_writes_one_record_naming_the_kind():
    passing_gate = GateReport(passed=True, checks=[], blocking=[], overridden=[])
    ctx = _FullRecordCtx(
        gate_decision=GateDecision(gate="merge", outcome=GateOutcome.REJECT, decided_by="human"),
        verdict=MergeVerdict(approve=False, confidence=0.3, rationale="risk detected"),
    )
    cfg = PipelineConfig(gates={"merge": GateConfig(policy=GatePolicy.SOFT)})
    with (
        patch("sdlc.stages.merge.step.evaluate_gate", new_callable=AsyncMock) as mock_eg,
        patch("sdlc.stages.merge.step.run_integration_checks", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.measure_coverage", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.scoped_security_scan", new_callable=AsyncMock),
        patch("sdlc.stages.merge.step.prepare_base_worktree", new_callable=AsyncMock),
        patch(
            "sdlc.stages.merge.step.calibration_verdict",
            new_callable=AsyncMock,
            side_effect=RuntimeError("no calibration store"),
        ),
    ):
        mock_eg.return_value = passing_gate
        res = await merge.step(
            ctx,
            cfg=cfg,
            task_results=_results(),
            integration_wt="/wt",
            idea=_idea(),
            merge_agent=object(),
        )

    # the returned string is UNCHANGED
    assert res == "rejected:merge:soft-verdict"
    recs = _merge_records(ctx)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.quality.score == 0.0
    assert rec.outcome is BenchmarkOutcome.FAIL
    assert rec.error is not None and "soft-verdict" in rec.error


# --- (4) an ordinary run rides the same record path --------------------------


@pytest.mark.asyncio
async def test_ordinary_run_rejection_records_are_ordinary_records():
    """With cfg.benchmark.case_id None the new records go through the same
    ctx.record path as any base record: exactly one merge record per
    rejection path, carrying no benchmark identity (case_id '_unknown')."""
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

    async def _advisory_case():
        ctx = _gate_ctx()
        with (
            patch("sdlc.stages.merge.step.evaluate_gate", new_callable=AsyncMock) as mock_eg,
            patch("sdlc.stages.merge.step.run_integration_checks", new_callable=AsyncMock),
            patch("sdlc.stages.merge.step.measure_coverage", new_callable=AsyncMock),
            patch("sdlc.stages.merge.step.scoped_security_scan", new_callable=AsyncMock),
            patch("sdlc.stages.merge.step.prepare_base_worktree", new_callable=AsyncMock),
        ):
            mock_eg.return_value = failing_advisory
            res = await merge.step(
                ctx,
                cfg=PipelineConfig(),  # benchmark.case_id is None
                task_results=_results(),
                integration_wt="/wt",
                idea=_idea(),
            )
        assert res == "rejected:merge:advisory"
        recs = _merge_records(ctx)
        assert len(recs) == 1
        return recs[0]

    advisory_rec = await _advisory_case()
    assert advisory_rec.case_id == "_unknown", (
        "an ordinary run's rejection record carries no benchmark identity"
    )
