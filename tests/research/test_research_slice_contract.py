import inspect
import pathlib
import sys
from unittest.mock import MagicMock

import pytest
import temporalio.workflow

from sdlc.core.models import (
    GateDecision,
    GateOutcome,
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
)
from sdlc.grounding import Violation
from sdlc.memory.models import MemoryKind, RetainItem
from sdlc.stages import research
from sdlc.stages.research.models import (
    ConsultedSource,
    GroundedFinding,
    ResearchBrief,
    ResearchPlan,
    SubQuestion,
    SubQuestionFinding,
)


@pytest.mark.clause("RESEARCH-1.5")
def test_slice_exports_step_and_activities():
    assert callable(research.step)
    assert isinstance(research.ACTIVITIES, list)
    assert len(research.ACTIVITIES) == 4
    act_names = {
        getattr(a, "__temporal_activity_definition", MagicMock()).name for a in research.ACTIVITIES
    }
    assert {
        "plan_research",
        "research_subquestion",
        "synthesize_brief",
        "verify_brief_activity",
    }.issubset(act_names)


@pytest.mark.clause("RESEARCH-1.1")
def test_research_step_signature_and_no_workflow_dependencies():
    params = inspect.signature(research.step).parameters
    param_names = list(params)
    assert param_names[0] == "ctx"
    assert "cfg" in param_names
    assert "idea" in param_names
    assert "research_agent" in param_names

    src = pathlib.Path("src/sdlc/stages/research/step.py").read_text(encoding="utf-8")
    assert "agents.roles" not in src
    assert "@workflow.signal" not in src
    assert "@workflow.query" not in src
    assert "@workflow.defn" not in src


@pytest.mark.clause("RESEARCH-1.2")
@pytest.mark.clause("RESEARCH-1.4")
@pytest.mark.asyncio
async def test_research_step_grounded_execution_and_retention(monkeypatch):
    class _StubCtx:
        def __init__(self) -> None:
            self.stages: list[str] = []
            self.records: list = []
            self.retained: list[tuple] = []

        def stage(self, status: str, trace: str | None = None) -> None:
            self.stages.append(status)

        async def gate(self, name: str, settings: object, **kwargs: object) -> GateDecision:
            return GateDecision(
                gate=name,
                outcome=GateOutcome.APPROVE,
                decided_by="human",
                round=kwargs.get("round", 1),
            )

        async def record(self, cfg: object, record: object) -> None:
            self.records.append(record)

        async def retain(
            self, cfg: object, kind: object, bank: str, text: str, metadata: dict
        ) -> None:
            self.retained.append((kind, bank, text, metadata))

        async def judge(
            self, cfg: object, artifact_json: str, stage: str, author_model: str
        ) -> object:
            res = MagicMock()
            res.score = 1.0
            res.judge = "contract"
            return res

    ctx = _StubCtx()
    cfg = PipelineConfig(research_enabled=True)
    idea = IdeaBrief(title="Feature", description="Test description", mode=ProjectMode.GREENFIELD)

    sq = SubQuestion(id="sq-0", question="Sub-question 0")
    plan = ResearchPlan(sub_questions=[sq])
    source = ConsultedSource(
        url="https://example.com", title="Ex", assessment="good", relevance="high"
    )
    finding_grounded = GroundedFinding(
        source_url="https://example.com", quote="exact quote", claim="claim 1"
    )
    finding = SubQuestionFinding(
        sub_question=sq,
        brief=ResearchBrief(
            summary="Sub-brief",
            sources_consulted=[source],
            grounded_findings=[finding_grounded],
        ),
    )
    synth_brief = ResearchBrief(
        summary="Synthesized research brief",
        sources_consulted=[source],
        grounded_findings=[finding_grounded],
        confidence=0.9,
    )

    async def _mock_execute_activity(activity_fn, *args, **kwargs):
        name = getattr(activity_fn, "__temporal_activity_definition", MagicMock()).name
        if name == "plan_research":
            return plan
        elif name == "research_subquestion":
            return finding
        elif name == "synthesize_brief":
            return synth_brief, MagicMock(input_tokens=0, output_tokens=0)
        elif name == "verify_brief_activity":
            return []  # No violations -> verified
        elif name == "price_usage":
            return 0.01
        return MagicMock()

    monkeypatch.setattr(
        sys.modules["sdlc.stages.research.step"],
        "verified_findings_to_retain",
        lambda brief, run_id, bank: [
            RetainItem(
                kind=MemoryKind.RESEARCH_FINDING,
                bank=bank,
                text="test finding",
                metadata={},
            )
        ],
    )
    monkeypatch.setattr(temporalio.workflow, "execute_activity", _mock_execute_activity)

    res = await research.step(
        ctx,
        cfg=cfg,
        idea=idea,
        research_agent=MagicMock(),
    )

    assert isinstance(res, ResearchBrief)
    assert res.summary == "Synthesized research brief"
    assert len(ctx.records) == 1
    assert ctx.records[0].outcome.name == "PASS"
    assert len(ctx.retained) > 0


@pytest.mark.clause("RESEARCH-1.3")
@pytest.mark.asyncio
async def test_research_step_handles_grounding_violation_as_stage_failure(monkeypatch):
    class _StubCtx:
        def __init__(self) -> None:
            self.stages: list[str] = []
            self.records: list = []

        def stage(self, status: str, trace: str | None = None) -> None:
            self.stages.append(status)

        async def record(self, cfg: object, record: object) -> None:
            self.records.append(record)

    ctx = _StubCtx()
    cfg = PipelineConfig(research_enabled=True)
    idea = IdeaBrief(title="Feature", description="Test description", mode=ProjectMode.GREENFIELD)

    sq = SubQuestion(id="sq-0", question="Sub-question 0")
    plan = ResearchPlan(sub_questions=[sq])
    finding = SubQuestionFinding(sub_question=sq, brief=ResearchBrief(summary="Sub-brief"))
    synth_brief = ResearchBrief(
        summary="Synthesized research brief",
        grounded_findings=[
            GroundedFinding(
                source_url="https://unfetched.com",
                quote="hallucinated",
                claim="claim",
            )
        ],
    )

    async def _mock_execute_activity(activity_fn, *args, **kwargs):
        name = getattr(activity_fn, "__temporal_activity_definition", MagicMock()).name
        if name == "plan_research":
            return plan
        elif name == "research_subquestion":
            return finding
        elif name == "synthesize_brief":
            return synth_brief, MagicMock(input_tokens=0, output_tokens=0)
        elif name == "verify_brief_activity":
            return [
                Violation(
                    kind="source_unavailable",
                    source="https://unfetched.com",
                    quote="hallucinated",
                )
            ]
        return MagicMock()

    monkeypatch.setattr(temporalio.workflow, "execute_activity", _mock_execute_activity)

    res = await research.step(
        ctx,
        cfg=cfg,
        idea=idea,
        research_agent=MagicMock(),
    )

    assert "research_failed" in ctx.stages
    assert len(ctx.records) == 1
    assert ctx.records[0].outcome.name == "FAIL"
    assert "rejected:research.grounding" in ctx.records[0].error
    # Digest must be empty on grounding failure
    assert getattr(res, "digest", "") == ""
