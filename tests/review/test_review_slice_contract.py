"""Review stage slice contract test (spec A §3.3)."""

from __future__ import annotations

import inspect
import pathlib
from unittest.mock import MagicMock

import pytest
import temporalio.workflow

from sdlc.benchmarks.models import BenchmarkOutcome
from sdlc.core.models import ArtifactRef, PipelineConfig
from sdlc.harness.models import SessionEvent
from sdlc.memory.models import MemoryKind
from sdlc.stages import review
from sdlc.stages.code.models import IntegrityFlag
from sdlc.stages.qa.models import QAReport
from sdlc.stages.review.models import DeepReviewReport, ReviewFinding, ReviewReport


@pytest.mark.clause("REVIEW-1.5")
def test_slice_exports_step_and_activities():
    assert callable(review.step)
    assert callable(review.run_adversary)
    assert callable(review.run_deep_review)
    assert isinstance(review.ACTIVITIES, list)
    assert review.ACTIVITIES == []


@pytest.mark.clause("REVIEW-1.1")
def test_review_step_signature_and_no_gate():
    params = inspect.signature(review.step).parameters
    param_names = list(params)
    assert param_names[0] == "ctx"
    assert "cfg" in param_names
    assert "task" in param_names
    assert "contract" in param_names
    assert "diff" in param_names
    assert "reviewer_agent" in param_names
    assert "adversary_agent" in param_names
    assert "deep_review_agent" in param_names

    src = pathlib.Path("src/sdlc/stages/review/step.py").read_text(encoding="utf-8")
    assert "ctx.gate" not in src


@pytest.mark.clause("REVIEW-1.2")
@pytest.mark.asyncio
async def test_review_step_clean_context_execution():
    class _StubCtx:
        def __init__(self) -> None:
            self.role_called = False
            self.records: list = []

        async def run_role(self, cfg, role, model, agent, prompt, into=None):
            self.role_called = True
            assert role == "reviewer"
            assert "Frozen contract assertions:" in prompt
            assert "assertion-1" in prompt
            assert "Test results:" in prompt
            assert "Diff:" in prompt
            res = MagicMock()
            res.output = ReviewReport(approve=True, findings=[])
            return res

        def stage_record(self, cfg, **kwargs):
            rec = MagicMock()
            rec.stage = kwargs.get("stage", "review")
            rec.outcome = kwargs.get("outcome", BenchmarkOutcome.PASS)
            return rec

        async def record(self, cfg, record):
            self.records.append(record)

    ctx = _StubCtx()
    cfg = PipelineConfig(review_enabled=True)
    task = MagicMock()
    task.id = "t1"
    task.acceptance_criteria = ["assertion-1"]
    contract = MagicMock()
    contract.assertions = ["assertion-1"]
    diff = {"patch": "--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new"}
    qa_raw = QAReport(tests_passed=True, issues=[])

    result = await review.step(
        ctx,
        cfg=cfg,
        task=task,
        contract=contract,
        diff=diff,
        reviewer_agent=MagicMock(),
        qa_raw=qa_raw,
    )
    assert ctx.role_called is True
    assert isinstance(result, ReviewReport)
    assert result.approve is True
    assert len(ctx.records) == 1
    assert ctx.records[0].stage == "review"
    assert ctx.records[0].outcome == BenchmarkOutcome.PASS


@pytest.mark.clause("REVIEW-1.3")
@pytest.mark.asyncio
async def test_adversary_fail_open_and_retention():
    class _StubCtx:
        def __init__(self) -> None:
            self.records: list = []
            self.retained: list[tuple] = []

        async def run_role(self, cfg, role, model, agent, prompt, into=None):
            assert role == "adversary"
            res = MagicMock()
            res.output = ReviewReport(
                approve=False,
                findings=[
                    ReviewFinding(
                        assertion="A1",
                        severity="high",
                        detail="adversary finding",
                    )
                ],
            )
            return res

        def stage_record(self, cfg, **kwargs):
            rec = MagicMock()
            rec.stage = kwargs.get("stage", "adversary")
            rec.outcome = kwargs.get("outcome", BenchmarkOutcome.FAIL)
            return rec

        async def record(self, cfg, record):
            self.records.append(record)

        async def retain(self, cfg, kind, bank, text, metadata):
            self.retained.append((kind, bank, text, metadata))

    ctx = _StubCtx()
    cfg = PipelineConfig(adversarial_review_enabled=True)
    task = MagicMock()
    task.id = "t1"
    contract = MagicMock()
    diff = {"patch": "diff patch"}
    qa_raw = QAReport(tests_passed=True, issues=[])

    report = await review.run_adversary(
        ctx,
        cfg=cfg,
        contract=contract,
        assertions=["A1"],
        diff=diff,
        qa_raw=qa_raw,
        task=task,
        adversary_agent=MagicMock(),
    )
    assert report is not None
    assert report.approve is False
    assert len(ctx.records) == 1
    assert ctx.records[0].stage == "adversary"
    assert len(ctx.retained) == 1
    assert ctx.retained[0][0] == MemoryKind.GOTCHA

    # Fail-open: exception returns None
    class _FailingCtx(_StubCtx):
        async def run_role(self, *args, **kwargs):
            raise RuntimeError("adversary model exploded")

    fail_report = await review.run_adversary(
        _FailingCtx(),
        cfg=cfg,
        contract=contract,
        assertions=["A1"],
        diff=diff,
        qa_raw=qa_raw,
        task=task,
        adversary_agent=MagicMock(),
    )
    assert fail_report is None


@pytest.mark.clause("REVIEW-1.4")
@pytest.mark.asyncio
async def test_deep_review_fail_open_and_integrity_verification(monkeypatch):
    class _StubCtx:
        def __init__(self) -> None:
            self.records: list = []
            self.retained: list[tuple] = []

        async def run_role(self, cfg, role, model, agent, prompt, into=None):
            assert role == "deep_review"
            res = MagicMock()
            res.output = DeepReviewReport(
                findings=[],
                integrity_flags=[
                    IntegrityFlag(
                        kind="test_gaming",
                        detail="deleted a test",
                        evidence="pytest deleted line",
                    )
                ],
                summary="summary",
                approve=False,
            )
            return res

        def stage_record(self, cfg, **kwargs):
            rec = MagicMock()
            rec.stage = kwargs.get("stage", "deep_review")
            rec.outcome = kwargs.get("outcome", BenchmarkOutcome.FAIL)
            return rec

        async def record(self, cfg, record):
            self.records.append(record)

        async def retain(self, cfg, kind, bank, text, metadata):
            self.retained.append((kind, bank, text, metadata))

    async def _fake_execute_act(act, inp, **kwargs):
        res = MagicMock()
        ev = SessionEvent(kind="command", text="pytest deleted line")
        res.text = '{"header": "meta"}\n' + ev.model_dump_json()
        res.truncated = False
        return res

    monkeypatch.setattr(temporalio.workflow, "execute_activity", _fake_execute_act)

    ctx = _StubCtx()
    cfg = PipelineConfig(deep_review_enabled=True)
    run = MagicMock()
    run.session_ref = ArtifactRef(kind="harness_session", id="session-123", uri="session-123.jsonl")
    run.session_digest = None
    task = MagicMock()
    task.id = "t1"
    contract = MagicMock()
    diff = {"patch": "diff patch"}

    report = await review.run_deep_review(
        ctx,
        cfg=cfg,
        run=run,
        contract=contract,
        assertions=["A1"],
        diff=diff,
        task=task,
        deep_review_agent=MagicMock(),
    )
    assert report is not None
    assert report.cheat_detected is True
    assert len(ctx.records) == 1
    assert ctx.records[0].stage == "deep_review"
    assert len(ctx.retained) == 1
    assert ctx.retained[0][0] == MemoryKind.GOTCHA

    # Fail-open: exception returns None
    class _FailingCtx(_StubCtx):
        async def run_role(self, *args, **kwargs):
            raise RuntimeError("deep review model exploded")

    fail_report = await review.run_deep_review(
        _FailingCtx(),
        cfg=cfg,
        run=run,
        contract=contract,
        assertions=["A1"],
        diff=diff,
        task=task,
        deep_review_agent=MagicMock(),
    )
    assert fail_report is None
