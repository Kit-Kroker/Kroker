"""009 D4: the research step retains the brief that was verified (FR-001,
FR-002, FR-003, FR-008).

Stage-level pairing tests: the step runs against a stub context and a
scripted activity mock, with the REAL verified_findings_to_retain unless a
case says otherwise. RED cases 1-4 fail on unmodified source (the retain
path re-runs the verifier itself, reading page files); PIN cases 5-7 pin the
failure paths that FR-008 keeps unchanged. Cases 3 and 4 pin the pairing
under a refine round that fails after the first brief was verified (EC5,
EC2/A1).
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest
import temporalio.workflow

from sdlc.core.models import (
    GateDecision,
    GateOutcome,
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
    RoleUsage,
)
from sdlc.grounding import Violation
from sdlc.stages.research.models import (
    GroundedFinding,
    ResearchBrief,
    ResearchPlan,
    SubQuestion,
    SubQuestionFinding,
)

# The package __init__ re-exports the step FUNCTION as `research.step`, so a
# from-import binds that; bind the modules themselves (the slice-contract test
# reaches them via sys.modules for the same reason).
step_module = importlib.import_module("sdlc.stages.research.step")
verify_module = importlib.import_module("sdlc.stages.research.verify")

SQ = SubQuestion(id="sq-0", question="Sub-question 0")
PLAN = ResearchPlan(sub_questions=[SQ])
FINDING = SubQuestionFinding(sub_question=SQ, brief=ResearchBrief(summary="Sub-brief"))

F1 = GroundedFinding(source_url="https://example.com/1", quote="quote one", claim="claim one")
F2 = GroundedFinding(source_url="https://example.com/2", quote="quote two", claim="claim two")
BRIEF1 = ResearchBrief(summary="first brief", grounded_findings=[F1, F2])
BRIEF2 = ResearchBrief(
    summary="second brief",
    grounded_findings=[
        GroundedFinding(
            source_url="https://example.com/3", quote="quote three", claim="claim three"
        )
    ],
)
VIOLATION = Violation(kind="quote_not_found", source=F1.source_url, quote=F1.quote)

IDEA = IdeaBrief(title="Feature", description="Test description", mode=ProjectMode.GREENFIELD)


def _texts(brief: ResearchBrief) -> list[str]:
    """The retain items' texts for a brief, in retain.py's own format."""
    return [f"{f.claim} — {f.source_url}" for f in brief.grounded_findings]


def _retained_texts(ctx: _StubCtx) -> list[str]:
    return [text for _, _, text, _ in ctx.retained]


class _StubCtx:
    """Stage/record/retain/gate/judge stub; gates answer from a script."""

    def __init__(self, gates: list[tuple[GateOutcome, str | None]]) -> None:
        self.stages: list[str] = []
        self.records: list = []
        self.retained: list[tuple] = []
        self._gates = iter(gates)

    def stage(self, status: str, trace: str | None = None) -> None:
        self.stages.append(status)

    async def gate(self, name: str, settings: object, **kwargs: object) -> GateDecision:
        outcome, guidance = next(self._gates)
        return GateDecision(
            gate=name,
            outcome=outcome,
            decided_by="human",
            round=kwargs.get("round", 1),  # type: ignore[arg-type]
            guidance=guidance,
        )

    async def record(self, cfg: object, record: object) -> None:
        self.records.append(record)

    async def retain(self, cfg: object, kind: object, bank: str, text: str, metadata: dict) -> None:
        self.retained.append((kind, bank, text, metadata))

    async def judge(self, cfg: object, artifact_json: str, stage: str, author_model: str) -> object:
        res = MagicMock()
        res.score = 1.0
        res.judge = "contract"
        return res


def _script_activities(monkeypatch, *, synth: list, verify: list) -> None:
    """Mock temporalio.workflow.execute_activity, dispatched by activity name.

    plan_research always plans SQ; research_subquestion always returns FINDING.
    `synth` and `verify` are consumed left-to-right, one item per call; a
    BaseException item is raised instead of returned.
    """
    synth_iter, verify_iter = iter(synth), iter(verify)

    async def _execute(activity_fn, *args, **kwargs):
        name = getattr(activity_fn, "__temporal_activity_definition", MagicMock()).name
        if name == "plan_research":
            return PLAN
        if name == "research_subquestion":
            return FINDING
        if name == "synthesize_brief":
            item = next(synth_iter)
            if isinstance(item, BaseException):
                raise item
            return item
        if name == "verify_brief_activity":
            return next(verify_iter)
        if name == "price_usage":
            return 0.0
        return MagicMock()

    monkeypatch.setattr(temporalio.workflow, "execute_activity", _execute)


def _usage(model: str = "m") -> RoleUsage:
    return RoleUsage(role="research", model=model)


async def _run_step(ctx: _StubCtx, monkeypatch, tmp_path) -> object:
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return await step_module.step(
        ctx, cfg=PipelineConfig(research_enabled=True), idea=IDEA, run_id="pair-run"
    )


@pytest.mark.asyncio
async def test_retain_path_never_touches_the_page_store(monkeypatch, tmp_path):
    """RED 1 / FR-002: retention decides from the verification result, not disk."""
    ctx = _StubCtx([(GateOutcome.APPROVE, None)])
    _script_activities(monkeypatch, synth=[(BRIEF1, _usage())], verify=[[]])

    def _no_pages(run_id: str):
        raise AssertionError("the retain path must not look at the page store")

    monkeypatch.setattr(verify_module, "pages_dir", _no_pages)

    await _run_step(ctx, monkeypatch, tmp_path)

    assert _retained_texts(ctx) == _texts(BRIEF1)


@pytest.mark.asyncio
async def test_retain_receives_the_brief_and_the_activity_s_own_result(monkeypatch, tmp_path):
    """RED 2 / FR-001, FR-003: the result handed over is the verifier's own list."""
    ctx = _StubCtx([(GateOutcome.APPROVE, None)])
    violations: list = []  # the specific object the verify activity returned
    spy_calls: list = []

    def _spy(brief, violations, bank):
        spy_calls.append((brief, violations, bank))
        return []

    monkeypatch.setattr(step_module, "verified_findings_to_retain", _spy)
    _script_activities(monkeypatch, synth=[(BRIEF1, _usage())], verify=[violations])

    await _run_step(ctx, monkeypatch, tmp_path)

    assert len(spy_calls) == 1
    assert spy_calls[0][0] is BRIEF1
    assert spy_calls[0][1] is violations


@pytest.mark.asyncio
async def test_failed_refine_keeps_the_first_verified_brief_s_findings(monkeypatch, tmp_path):
    """RED 3 / EC5: a refine round that dies mid-synthesis retains brief one."""
    ctx = _StubCtx([(GateOutcome.REVISE, "add a source")])
    _script_activities(
        monkeypatch,
        synth=[(BRIEF1, _usage()), RuntimeError("synthesis exploded")],
        verify=[[]],
    )

    await _run_step(ctx, monkeypatch, tmp_path)

    assert _retained_texts(ctx) == _texts(BRIEF1)


@pytest.mark.asyncio
async def test_failure_after_reassignment_retains_the_verified_brief_s_findings(
    monkeypatch, tmp_path
):
    """RED 4 / EC2, A1: a crash after the new brief is assigned cannot swap the
    retained brief — the verified pair stays bound."""
    ctx = _StubCtx([(GateOutcome.REVISE, "add a source")])
    refine_usage = _usage("refine-model")  # the exact object the fold receives
    real_fold = step_module._fold_research_usage

    async def _fold_exploding_on_refine_usage(cfg, usage, into):
        if usage is refine_usage:
            raise RuntimeError("fold exploded after the refine synthesis")
        return await real_fold(cfg, usage, into)

    monkeypatch.setattr(step_module, "_fold_research_usage", _fold_exploding_on_refine_usage)
    _script_activities(
        monkeypatch,
        synth=[(BRIEF1, _usage()), (BRIEF2, refine_usage)],
        verify=[[]],
    )

    await _run_step(ctx, monkeypatch, tmp_path)

    retained = _retained_texts(ctx)
    assert retained == _texts(BRIEF1)
    assert _texts(BRIEF2)[0] not in retained


@pytest.mark.asyncio
async def test_first_round_violation_retains_nothing_and_fails_closed(monkeypatch, tmp_path):
    """PIN 5 / US3-1: a violated first verification is a stage failure."""
    ctx = _StubCtx([])
    _script_activities(monkeypatch, synth=[(BRIEF1, _usage())], verify=[[VIOLATION]])

    res = await _run_step(ctx, monkeypatch, tmp_path)

    assert ctx.retained == []
    assert len(ctx.records) == 1
    assert ctx.records[0].outcome.name == "FAIL"
    assert ctx.records[0].error.startswith("rejected:research.grounding:")
    assert res.digest == ""


@pytest.mark.asyncio
async def test_refine_round_violation_retains_nothing_and_fails_closed(monkeypatch, tmp_path):
    """PIN 6 / US3-2: a violated refine verification fails with its own label."""
    ctx = _StubCtx([(GateOutcome.REVISE, "add a source")])
    _script_activities(
        monkeypatch, synth=[(BRIEF1, _usage()), (BRIEF2, _usage())], verify=[[], [VIOLATION]]
    )

    await _run_step(ctx, monkeypatch, tmp_path)

    assert ctx.retained == []
    assert len(ctx.records) == 1
    assert ctx.records[0].outcome.name == "FAIL"
    assert ctx.records[0].error == "rejected:research.grounding (refine)"


@pytest.mark.asyncio
async def test_verified_brief_without_findings_retains_nothing_and_passes(monkeypatch, tmp_path):
    """PIN 7 / EC4: nothing grounded is not a failure — there is nothing to retain."""
    ctx = _StubCtx([(GateOutcome.APPROVE, None)])
    empty_brief = ResearchBrief(summary="nothing grounded")
    _script_activities(monkeypatch, synth=[(empty_brief, _usage())], verify=[[]])

    res = await _run_step(ctx, monkeypatch, tmp_path)

    assert ctx.retained == []
    assert len(ctx.records) == 1
    assert ctx.records[0].outcome.name == "PASS"
    assert res.digest != ""
