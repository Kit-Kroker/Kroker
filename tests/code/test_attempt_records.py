"""012 T017 (RED): the three attempt records partition the attempt.

Drives the REAL ``code.step`` with a fake workflow namespace (controllable
clock + activity dispatch) and a fake ctx whose record() captures REAL
BenchmarkRecords built by the real ``record_builder.stage_record``.

CLOCK SCHEME (documented per the brief so ordering assertions are
decidable): every ``workflow.now()`` call advances a counter by +100 s, so
each timestamp the code step takes is strictly greater than the previous
one. The relations the code step controls (code/qa starts and ends, and
the review record's ``started`` argument) are therefore strictly ordered
and comparable. The review record's ``ended_at`` is taken by
review/step.py's OWN ``_now()`` (its module's workflow reference is not
patched here), which outside a workflow falls back to the real wall
clock — so R.ended is only asserted ``>= R.started``, never placed on the
fake clock's scale.

RED today (contract §5.1-5.4 violated at base): the code and qa records
both start at the attempt start and end at their write time — after the
review record was written — so the partition
C.ended == Q.started == Q.ended... cannot hold.
"""

from __future__ import annotations

import importlib
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from temporalio import workflow as real_workflow

# `sdlc.stages.code.__init__` re-exports the step FUNCTION, shadowing the
# module attribute — import the module explicitly to patch its `workflow`.
code_step = importlib.import_module("sdlc.stages.code.step")
from sdlc.benchmarks.models import BenchmarkOutcome, QualityScore
from sdlc.core.models import GateOutcome, HarnessKind, PipelineConfig, RoleConfig
from sdlc.harness.models import HarnessRunResult
from sdlc.stages.plan.models import DevTask
from sdlc.stages.qa.models import QAReport
from sdlc.stages.review.models import ReviewFinding, ReviewReport

_BASE = datetime(2026, 7, 4, 10, tzinfo=UTC)


class _FakeWorkflow:
    """The slice of temporalio.workflow the code step touches. now() is a
    controllable clock (+100 s per call); execute_activity dispatches by
    the activity function's name."""

    def __init__(self) -> None:
        self._t = 0
        self.activity_calls: list = []

    # delegate the sandbox marker and config class to the real module
    unsafe = real_workflow.unsafe
    ActivityConfig = staticmethod(real_workflow.ActivityConfig)
    logger = logging.getLogger("t017-fake-workflow")

    def now(self):
        self._t += 100
        return _BASE + timedelta(seconds=self._t)

    def info(self):
        return SimpleNamespace(workflow_id="wf-t017")

    async def execute_activity(self, fn, arg=None, **kw):
        self.activity_calls.append((fn.__name__, arg))
        if fn.__name__ == "run_coding_task":
            return HarnessRunResult(
                harness=HarnessKind.CLAUDE_CODE,
                exit_code=0,
                summary="ok",
                commit_sha="c" * 40,
                cost_usd=0.01,
            )
        if fn.__name__ == "run_test_suite":
            return QAReport(tests_passed=True, failing_tests=[], issues=[])
        if fn.__name__ == "get_task_diff":
            return {"files": ["app.py"], "stat": "app.py | 1 +", "patch": "diff --git ..."}
        raise AssertionError(f"unexpected activity {fn.__name__}")


class _FakeCtx:
    """Captures real BenchmarkRecords via ctx.record; run_role answers by
    role with canned reports."""

    def __init__(self, review_approve=True) -> None:
        self.records = []
        self.events = []
        self.review_approve = review_approve

    def emit(self, kind, **kw):
        # step.py calls ctx.emit WITHOUT await (code/step.py:563, usage.py:42)
        self.events.append((kind, kw))

    async def record(self, cfg, rec):
        self.records.append(rec)

    async def judge(self, cfg, artifact, stage, **kw):
        return QualityScore(score=None, judge="llm_judge")

    async def run_role(self, cfg, role, model, agent, prompt, into=None):
        if role == "qa":
            return SimpleNamespace(output=QAReport(tests_passed=True, failing_tests=[], issues=[]))
        if role == "reviewer":
            if self.review_approve:
                return SimpleNamespace(output=ReviewReport(approve=True))
            return SimpleNamespace(
                output=ReviewReport(
                    approve=False,
                    findings=[
                        ReviewFinding(assertion="ac1", severity="high", detail="not done right")
                    ],
                )
            )
        raise AssertionError(f"unexpected role {role}")

    async def gate(self, name, settings, **kw):
        # terminal reject: the step must return quarantined, not loop
        return SimpleNamespace(
            approved=False,
            outcome=GateOutcome.REJECT,
            comments="gate says no",
            guidance="",
            decided_by="human",
            thaw_tests=False,
        )

    async def retain(self, *a, **k):
        pass


def _cfg(**kw) -> PipelineConfig:
    base = dict(
        roles={"dev": RoleConfig(harness=HarnessKind.CLAUDE_CODE, model="test-model")},
        max_fix_attempts=0,  # one attempt, then the gate decides
    )
    base.update(kw)
    return PipelineConfig(**base)


def _task() -> DevTask:
    return DevTask(id="t1", title="T", description="D", acceptance_criteria=["ac1"])


def _run_step(monkeypatch, *, review_approve=True, cfg=None):
    fake_wf = _FakeWorkflow()
    monkeypatch.setattr(code_step, "workflow", fake_wf)
    ctx = _FakeCtx(review_approve=review_approve)

    import asyncio

    result = asyncio.run(
        code_step.step(
            ctx,
            cfg=cfg or _cfg(),
            task=_task(),
            worktree="/tmp/wt",
            branch="b",
            branch_point="bp",
            qa_agent=SimpleNamespace(),
            reviewer_agent=SimpleNamespace(),
            adversary_agent=None,
            deep_review_agent=None,
            handoff_agent=None,
        )
    )
    return result, ctx, fake_wf


def _by_stage(ctx):
    return {r.stage: r for r in ctx.records}


# --- (1) ordering: the three records partition the attempt (§5.1-5.4) --------


def test_attempt_records_partition_the_attempt_clock(monkeypatch):
    """One attempt, tests pass, qa clean, reviewer approves: C (code) ends
    where Q (qa) begins, Q ends where R (review) begins — with the +100 s
    clock every endpoint is distinct, so the partition relations are strict
    wherever the code step controls both sides."""
    result, ctx, fake_wf = _run_step(monkeypatch)
    assert result.status == "done"
    recs = _by_stage(ctx)
    assert set(recs) == {"code", "qa", "review"}
    C, Q, R = recs["code"], recs["qa"], recs["review"]

    def start(r):
        return r.speed.started_at

    def end(r):
        return r.speed.ended_at

    # C.started is the FIX_ATTEMPT emission time (attempt start)
    assert start(C) < end(C)
    assert end(C) == start(Q)
    assert start(Q) < end(Q)
    assert end(Q) == start(R)
    assert end(R) >= start(R)
    # strict chain across the three records, no shared endpoint pair
    # (executor fix: §5.3 makes R.start == Q.end BY DESIGN — equality, not
    # strict <; the strictness the step guarantees is end(C) < end(Q))
    assert end(C) < end(Q)
    assert end(Q) == start(R)
    spans = {(start(C), end(C)), (start(Q), end(Q)), (start(R), end(R))}
    assert len(spans) == 3


# --- (2) each record carries its own role's verdict (§5.5/§5.6) --------------


def test_qa_record_passes_when_the_reviewer_rejects(monkeypatch):
    """§5.5/§5.6: tests pass and qa is clean, so the QA record's outcome is
    the QA role's own PASS — while the task does not pass (the step returns
    a non-done TaskResult through the gate) and the review record says FAIL
    (the reviewer's own verdict). The code record stays the deterministic
    tests/qa verdict (PASS here); the task verdict is the TaskResult."""
    result, ctx, _ = _run_step(monkeypatch, review_approve=False)
    recs = _by_stage(ctx)
    assert recs["qa"].outcome is BenchmarkOutcome.PASS
    assert recs["review"].outcome is BenchmarkOutcome.FAIL
    assert result.status != "done"


# --- (3) the vacuous-lens boundary (§5.8) ------------------------------------


def test_no_review_record_when_review_is_disabled(monkeypatch):
    """§5.8, review half: with cfg.review_enabled False (reviewer agent
    present) no review record claims a timing or verdict for work that did
    not run."""
    result, ctx, _ = _run_step(monkeypatch, cfg=_cfg(review_enabled=False))
    assert result.status == "done"
    assert "review" not in _by_stage(ctx)
    assert {"code", "qa"} == set(_by_stage(ctx))


@pytest.mark.skip(
    "§5.8, qa half, unreachable by configuration at base (T001(e)): qa_step is "
    "called unconditionally on every attempt (code/step.py:749); only "
    "review_enabled / deep_review_enabled / adversarial_review_enabled exist. "
    "There is no qa off-switch, so 'no qa record when the lens did not run' "
    "has no configuration to test. This case becomes writable only if a qa "
    "switch is ever introduced."
)
def test_no_qa_record_when_the_qa_lens_did_not_run():
    """Documentation-only: see the skip reason — a pin placeholder for a
    configuration that does not exist."""
    raise AssertionError("unreachable")


# --- (4) containment drift found (§5.5/§5.9) ----------------------------------

from sdlc.stages.code.activities import DriftGlobs
from sdlc.vcs import DriftReport


class _DriftWorkflow(_FakeWorkflow):
    """The base fake plus the two containment activities: globs resolve
    empty, the backstop FINDS a fenced test changed (repair attempt 2)."""

    async def execute_activity(self, fn, arg=None, **kw):
        if fn.__name__ == "load_drift_globs":
            self.activity_calls.append((fn.__name__, arg))
            return DriftGlobs(fence=[], report=[])
        if fn.__name__ == "check_test_drift":
            self.activity_calls.append((fn.__name__, arg))
            return DriftReport(fence_paths=["tests/test_core.py"])
        return await super().execute_activity(fn, arg, **kw)


def _run_drift_step(monkeypatch):
    """Attempt 1: qa clean, reviewer rejects -> fix loop. Attempt 2 (a
    repair attempt, containment on, anchor captured from attempt 1's
    checkpoint): the drift backstop runs and FINDS drift. The terminal-REJECT
    gate then decides, so the step returns without a third attempt."""
    fake_wf = _DriftWorkflow()
    monkeypatch.setattr(code_step, "workflow", fake_wf)
    ctx = _FakeCtx(review_approve=False)

    gate_calls: list = []
    original_gate = ctx.gate

    async def capturing_gate(name, settings, **kw):
        gate_calls.append((name, getattr(kw.get("context"), "analysis", None)))
        return await original_gate(name, settings, **kw)

    ctx.gate = capturing_gate

    import asyncio

    result = asyncio.run(
        code_step.step(
            ctx,
            cfg=_cfg(max_fix_attempts=1, containment_enabled=True),
            task=_task(),
            worktree="/tmp/wt",
            branch="b",
            branch_point="bp",
            qa_agent=SimpleNamespace(),
            reviewer_agent=SimpleNamespace(),
            adversary_agent=None,
            deep_review_agent=None,
            handoff_agent=None,
        )
    )
    return result, ctx, fake_wf, gate_calls


def test_drift_found_leaves_the_qa_record_pass_and_the_verdict_quarantined(monkeypatch):
    """§5.5: containment drift does not change the QA role's verdict — with
    tests passing and qa clean, the LAST attempt's qa record is PASS even
    though the drift forces the task to the human gate. §5.9: the returned
    TaskResult is what the base step returns for the same inputs — PINNED
    at red as status 'quarantined' (the drift-found path goes straight to
    the gate, whose terminal REJECT yields 'quarantined'); this assertion
    must keep holding after the record-verdict change."""
    result, ctx, fake_wf, gate_calls = _run_drift_step(monkeypatch)

    # the drift path really ran, on the repair attempt
    drift_acts = [
        name
        for name, _ in fake_wf.activity_calls
        if name in ("load_drift_globs", "check_test_drift")
    ]
    assert "load_drift_globs" in drift_acts and "check_test_drift" in drift_acts
    assert result.attempts == 2
    # the drift note reached the gate analysis (ground truth for the human)
    assert gate_calls, "the drift-found task must reach the gate"
    assert "FROZEN TESTS CHANGED" in (gate_calls[0][1] or "")

    # (a) RED today: the base step computes the qa record's outcome from
    # task_passed, which drift.found forces False — so at base this is FAIL.
    recs = _by_stage(ctx)
    assert recs["qa"].outcome is BenchmarkOutcome.PASS

    # (b) PINNED base behaviour (observed at red): status 'quarantined'
    assert result.status == "quarantined"


def test_reviewer_rejection_task_result_matches_the_base_verdict(monkeypatch):
    """§5.9, reviewer-rejection scenario: the returned TaskResult equals
    what the base step returns for the same inputs — one attempt, qa pass,
    reviewer reject, terminal-REJECT gate. PINNED at red: status
    'quarantined', attempts 1; the record-span change must not move it."""
    result, ctx, _ = _run_step(monkeypatch, review_approve=False)
    # PINNED base behaviour (observed at red)
    assert result.status == "quarantined"
    assert result.attempts == 1
    assert result.qa.tests_passed is True
