"""C7: retro appends the run's calibration samples -- best-effort, and never
at the cost of the run's outcome."""

from unittest.mock import AsyncMock, patch

import pytest

from sdlc.core.models import (
    GateOutcomeSummary,
    MemoryConfig,
    PipelineConfig,
    RunSummary,
    StageOutcome,
)
from sdlc.stages import retro

_T = "2026-09-10T12:00:00+00:00"


class _StubCtx:
    def __init__(self) -> None:
        self.emitted: list[tuple] = []

    def emit(self, kind, **kwargs) -> None:
        self.emitted.append((kind, kwargs))

    async def retain(self, *a, **k) -> None:
        return None


def _summary(gates=(), stages=()) -> RunSummary:
    return RunSummary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:x",
        terminal_stage="merge",
        started_at=_T,
        ended_at=_T,
        duration_s=1.0,
        stages=list(stages),
        gates=list(gates),
    )


def _auto_plan_gate() -> GateOutcomeSummary:
    return GateOutcomeSummary(
        gate="plan",
        round=1,
        policy="soft",
        decided_by="policy",
        approved=True,
        confidence=0.9,
        author_model="m/x",
    )


@pytest.mark.asyncio
async def test_retro_appends_one_sample_batch():
    """Side-effect budget: exactly ONE ledger activity call per run, carrying
    every sample -- not one call per gate. The other execute_activity calls in
    retro (export, retention) are counted too, so the assertion is on the
    ledger call specifically."""
    cfg = PipelineConfig(memory=MemoryConfig(enabled=False))
    summary = _summary(
        [_auto_plan_gate()],
        [StageOutcome(stage="code", role="dev", outcome="pass", duration_s=1.0, plan_drift=0.25)],
    )
    with patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as act:
        await retro.step(_StubCtx(), cfg=cfg, summary=summary, session_refs=[], trace=[])

    ledger_calls = [
        c
        for c in act.await_args_list
        if getattr(c.args[0], "__name__", "") == "record_calibration_samples"
    ]
    assert len(ledger_calls) == 1
    payload = ledger_calls[0].args[1]
    assert len(payload.samples) == 1
    assert payload.samples[0].outcome_label == 0.75


@pytest.mark.asyncio
async def test_retro_skips_the_ledger_when_there_is_nothing_to_record():
    """No auto-approves -> no activity call at all. An empty batch would be a
    pointless round-trip on every human-gated run, which is most of them."""
    cfg = PipelineConfig(memory=MemoryConfig(enabled=False))
    with patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as act:
        await retro.step(_StubCtx(), cfg=cfg, summary=_summary(), session_refs=[], trace=[])

    assert not [
        c
        for c in act.await_args_list
        if getattr(c.args[0], "__name__", "") == "record_calibration_samples"
    ]


@pytest.mark.asyncio
async def test_a_ledger_failure_does_not_change_the_run_outcome():
    """RETRO-1.4 still holds. A storage outage must not turn a deployed run
    into a failed one."""
    cfg = PipelineConfig(memory=MemoryConfig(enabled=False))
    summary = _summary(
        [_auto_plan_gate()],
        [StageOutcome(stage="code", role="dev", outcome="pass", duration_s=1.0, plan_drift=0.25)],
    )
    with patch(
        "temporalio.workflow.execute_activity",
        new_callable=AsyncMock,
        side_effect=RuntimeError("ledger down"),
    ):
        await retro.step(_StubCtx(), cfg=cfg, summary=summary, session_refs=[], trace=[])


def test_retro_owns_no_activities():
    """The ledger activities belong to sdlc/calibration/, which retro imports
    the way it already imports reflect. RETRO's slice list stays empty."""
    assert len(retro.ACTIVITIES) == 0
