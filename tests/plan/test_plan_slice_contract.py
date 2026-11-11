"""Contract tests for the plan stage vertical slice (spec A §3).

020 T028: rewritten against prepare/produce/finish — the FeatureWorkflow-era
`step` composite is deleted (T027); the graph's planner node is the
composition point, so the slice's contract is the three functions' shapes."""

from __future__ import annotations

import inspect
import pathlib
from typing import Any

import pytest

from sdlc.core.context import StageServices
from sdlc.core.models import (
    GateDecision,
    GateOutcome,
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
    RoleConfig,
)
from sdlc.stages import plan
from sdlc.stages.architecture.models import ArchitectureDecision, ArchitectureSpec
from sdlc.stages.clarify.models import ClarifiedRequirements
from sdlc.stages.plan.models import DevTask, ImplementationPlan
from sdlc.stages.plan.step import finish, prepare, produce


def test_slice_exports_a_narrow_surface():
    # 020 T027: `step` is gone from the package surface — the submodule
    # exists, the composite function does not.
    assert "step" not in plan.__all__
    assert isinstance(plan.ACTIVITIES, list)
    assert len(plan.ACTIVITIES) == 0


def test_agents_arrive_in_the_signature_not_from_the_registry():
    params = inspect.signature(produce).parameters
    assert "planner_agent" in params
    assert params["planner_agent"].kind is inspect.Parameter.KEYWORD_ONLY

    src = pathlib.Path("src/sdlc/stages/plan/step.py").read_text(encoding="utf-8")
    assert "agents.roles" not in src


@pytest.mark.clause("PLAN-1.1")
def test_the_slice_takes_a_stage_context_and_never_the_workflow():
    for fn in (prepare, produce, finish):
        first = list(inspect.signature(fn).parameters)[0]
        assert first == "ctx", fn.__name__
    assert StageServices


@pytest.mark.clause("PLAN-1.2")
def test_produce_returns_an_implementation_plan():
    ret = inspect.signature(produce).return_annotation
    assert "ImplementationPlan" in str(ret)


@pytest.mark.clause("PLAN-1.3")
@pytest.mark.asyncio
async def test_the_composition_executes_the_planner_and_finishes():
    """prepare → produce → finish runs the planner through the cached
    stage and lands the judge/record/retain triple — the composite's old
    sequence, pinned slice-wise (the revisable loop itself is the graph
    node's gate wiring)."""
    from sdlc.benchmarks.models import QualityScore

    class _StubCtx:
        def __init__(self) -> None:
            self.stages_called: list[str] = []
            self.recorded = False
            self.retained = False

        def stage(self, status: str, trace: str | None = None) -> None:
            self.stages_called.append(status)

        def emit(self, *a: Any, **k: Any) -> None:
            pass

        async def recall(self, *a: Any, **k: Any) -> Any:
            from sdlc.memory.models import RecallSnapshot

            return RecallSnapshot(query_hash="q", bank="b", watermark="w", items=[])

        async def cached_stage(
            self,
            cfg: Any,
            stage: str,
            input_json: str,
            output_type: type,
            run_fn: Any,
            *,
            prompt_digest: str = "",
            recall_ref: str = "",
        ) -> tuple[Any, bool]:
            out = await run_fn()
            return out, False

        async def run_role(self, *a: Any, **k: Any) -> Any:
            class _RoleResult:
                output = ImplementationPlan(
                    tasks=[
                        DevTask(
                            id="T1",
                            title="Task 1",
                            description="Desc 1",
                            acceptance_criteria=["Tests pass"],
                        )
                    ]
                )

            return _RoleResult()

        async def judge(self, *a: Any, **k: Any) -> QualityScore:
            return QualityScore(score=1.0, judge="contract", rationale="Good")

        async def record(self, *a: Any, **k: Any) -> None:
            self.recorded = True

        async def retain(self, *a: Any, **k: Any) -> None:
            self.retained = True

    ctx = _StubCtx()
    cfg = PipelineConfig(roles={"plan": RoleConfig(model="claude-3-5-sonnet")})
    idea = IdeaBrief(title="Test Idea", description="Test desc", mode=ProjectMode.GREENFIELD)
    reqs = ClarifiedRequirements(
        summary="Test reqs",
        functional_requirements=[],
        non_functional_requirements=[],
        out_of_scope=[],
        open_questions=[],
    )
    arch = ArchitectureSpec(
        overview="Arch overview",
        decisions=[
            ArchitectureDecision(
                id="ADR-1",
                decision="Use slices",
                rationale="Decoupling",
            )
        ],
    )

    prep = await prepare(ctx, cfg=cfg, idea=idea, planner_model="m-plan")
    plan_res = await produce(
        ctx, prep, cfg=cfg, architecture=arch, requirements=reqs, planner_agent=object()
    )
    await finish(
        ctx,
        prep,
        cfg=cfg,
        artifact=plan_res,
        gate=GateDecision(
            gate="plan", approved=True, outcome=GateOutcome.APPROVE, decided_by="human"
        ),
    )

    assert isinstance(plan_res, ImplementationPlan)
    assert len(plan_res.tasks) == 1
    assert ctx.recorded is True
    assert ctx.retained is True
