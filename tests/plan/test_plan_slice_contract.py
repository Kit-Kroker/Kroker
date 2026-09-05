"""Contract tests for the plan stage vertical slice (spec A §3)."""

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


def test_slice_exports_a_narrow_surface():
    assert callable(plan.step)
    assert isinstance(plan.ACTIVITIES, list)
    assert len(plan.ACTIVITIES) == 0


def test_agents_arrive_in_the_signature_not_from_the_registry():
    params = inspect.signature(plan.step).parameters
    assert "planner_agent" in params
    assert params["planner_agent"].kind is inspect.Parameter.KEYWORD_ONLY

    src = pathlib.Path("src/sdlc/stages/plan/step.py").read_text(encoding="utf-8")
    assert "agents.roles" not in src


@pytest.mark.clause("PLAN-1.1")
def test_step_takes_a_stage_context_and_never_the_workflow():
    first = list(inspect.signature(plan.step).parameters)[0]
    assert first == "ctx"
    assert StageServices


@pytest.mark.clause("PLAN-1.2")
def test_step_returns_implementation_plan_and_gate_decision():
    ret = inspect.signature(plan.step).return_annotation
    assert "tuple" in str(ret).lower() or ret == tuple[ImplementationPlan, GateDecision]


@pytest.mark.clause("PLAN-1.3")
@pytest.mark.asyncio
async def test_step_executes_planner_and_revisable_stage():
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

        async def revisable_stage(
            self, name: str, cfg: Any, run_fn: Any
        ) -> tuple[ImplementationPlan, GateDecision]:
            plan_obj = await run_fn(None)
            decision = GateDecision(
                gate="plan",
                approved=True,
                outcome=GateOutcome.APPROVE,
                decided_by="human",
            )
            return plan_obj, decision

        async def cached_stage(
            self,
            cfg: Any,
            stage: str,
            input_json: str,
            output_type: type,
            run_fn: Any,
            *,
            prompt_digest: str = "",
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

    plan_res, gate = await plan.step(
        ctx,
        cfg=cfg,
        architecture=arch,
        requirements=reqs,
        idea=idea,
    )

    assert isinstance(plan_res, ImplementationPlan)
    assert isinstance(gate, GateDecision)
    assert len(plan_res.tasks) == 1
    assert gate.approved is True
    assert ctx.recorded is True
    assert ctx.retained is True
