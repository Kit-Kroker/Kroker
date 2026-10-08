"""012 T018 (RED): the review record carries its own tokens (contract §5.7)
and brackets the review work (§5.3); no record for a lens that did not run
(§5.8).

New sibling file rather than an extension of test_review_slice_contract.py:
that file's _StubCtx builds MagicMock records, which cannot carry a real
CostBag — these tests capture records built by the REAL
``record_builder.stage_record`` so the spend assertions read actual fields.
The fake run_role mirrors the real RoleHost._run_role merge: when the step
hands it an ``into=`` bag, it fills the bag with canned token counts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from sdlc.benchmarks.record_builder import stage_record as real_stage_record
from sdlc.core.models import PipelineConfig
from sdlc.stages import review
from sdlc.stages.qa.models import QAReport
from sdlc.stages.review.models import ReviewReport

_T0 = datetime(2026, 7, 4, 10, tzinfo=UTC)


class _RecordingCtx:
    def __init__(self) -> None:
        self.records: list = []
        self.into_seen = "not-called"

    async def run_role(self, cfg, role, model, agent, prompt, into=None):
        self.into_seen = into
        if into is not None:
            # mirror RoleHost._run_role: usage merges into the caller's bag
            into.input_tokens = 1234
            into.output_tokens = 567
        res = MagicMock()
        res.output = ReviewReport(approve=True, findings=[])
        return res

    def stage_record(self, cfg, **kwargs):
        return real_stage_record(cfg, **kwargs)

    async def record(self, cfg, record):
        self.records.append(record)


def _drive(ctx):
    cfg = PipelineConfig(review_enabled=True)
    task = MagicMock()
    task.id = "t1"
    task.acceptance_criteria = ["assertion-1"]
    contract = MagicMock()
    contract.assertions = ["assertion-1"]
    return review.step(
        ctx,
        cfg=cfg,
        task=task,
        contract=contract,
        diff={"patch": "--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new"},
        reviewer_agent=MagicMock(),
        qa_raw=QAReport(tests_passed=True, issues=[]),
        reviewer_model="test-model",
        started=_T0,
    )


@pytest.mark.asyncio
async def test_review_record_carries_the_review_tokens():
    """contract §5.7: the record's cost bag carries the tokens the review
    consumed — the step must hand run_role an ``into=`` bag and pass the
    same bag to the record builder as ``spend=`` (run_adversary's pattern)."""
    ctx = _RecordingCtx()
    await _drive(ctx)
    assert len(ctx.records) == 1
    # the seam: the step passed a bag for the host to fill
    assert ctx.into_seen is not None, (
        "review.step must pass into= to ctx.run_role so the role's usage "
        "lands in a bag (run_adversary's pattern)"
    )
    rec = ctx.records[0]
    assert rec.cost.input_tokens == 1234
    assert rec.cost.output_tokens == 567


@pytest.mark.asyncio
async def test_review_record_brackets_the_review_work():
    """contract §5.3 (local pin): the record's started_at is exactly the
    ``started`` argument (the code step's qa end) and ended_at is taken at
    the write, so the span brackets the review work. The code-step-side
    ``started=_qa_ended`` wiring is pinned by
    tests/code/test_attempt_records.py — not duplicated here."""
    ctx = _RecordingCtx()
    await _drive(ctx)
    rec = ctx.records[0]
    assert rec.speed.started_at == _T0
    assert rec.speed.ended_at >= rec.speed.started_at


@pytest.mark.asyncio
async def test_no_record_when_review_disabled_or_reviewer_absent():
    """contract §5.8 (pin): no record claims a timing or verdict for a
    review that did not run — neither with the lens disabled (agent
    present) nor with the reviewer absent (lens enabled)."""
    ctx_off = _RecordingCtx()
    cfg_off = PipelineConfig(review_enabled=False)
    task = MagicMock()
    task.id = "t1"
    task.acceptance_criteria = ["assertion-1"]
    contract = MagicMock()
    contract.assertions = ["assertion-1"]
    result = await review.step(
        ctx_off,
        cfg=cfg_off,
        task=task,
        contract=contract,
        diff={"patch": "p"},
        reviewer_agent=MagicMock(),
        qa_raw=QAReport(tests_passed=True, issues=[]),
        started=_T0,
    )
    assert result is None
    assert ctx_off.records == []

    ctx_absent = _RecordingCtx()
    cfg_on = PipelineConfig(review_enabled=True)
    result = await review.step(
        ctx_absent,
        cfg=cfg_on,
        task=task,
        contract=contract,
        diff={"patch": "p"},
        reviewer_agent=None,
        qa_raw=QAReport(tests_passed=True, issues=[]),
        started=_T0,
    )
    assert result is None
    assert ctx_absent.records == []
