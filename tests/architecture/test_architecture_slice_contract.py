"""Contract tests for the architecture stage vertical slice (spec A §3)."""

from __future__ import annotations

import inspect
import pathlib
from typing import Any

import pytest

from sdlc.core.context import StageServices
from sdlc.core.models import GateDecision, IdeaBrief, PipelineConfig, ProjectMode, RoleConfig
from sdlc.stages import architecture
from sdlc.stages.architecture.models import ArchitectureDecision, ArchitectureSpec
from sdlc.stages.clarify.models import ClarifiedRequirements


def test_slice_exports_a_narrow_surface():
    assert callable(architecture.step)
    assert isinstance(architecture.ACTIVITIES, list)
    assert len(architecture.ACTIVITIES) == 0


def test_agents_arrive_in_the_signature_not_from_the_registry():
    params = inspect.signature(architecture.step).parameters
    assert "architect_agent" in params
    assert params["architect_agent"].kind is inspect.Parameter.KEYWORD_ONLY

    src = pathlib.Path("src/sdlc/stages/architecture/step.py").read_text(encoding="utf-8")
    assert "agents.roles" not in src


@pytest.mark.clause("ARCH-1.1")
def test_step_takes_a_stage_context_and_never_the_workflow():
    first = list(inspect.signature(architecture.step).parameters)[0]
    assert first == "ctx"
    assert StageServices


@pytest.mark.clause("ARCH-1.2")
def test_step_returns_architecture_spec_and_gate_decision():
    ret = inspect.signature(architecture.step).return_annotation
    assert "tuple" in str(ret).lower() or ret == tuple[ArchitectureSpec, GateDecision]


@pytest.mark.clause("ARCH-1.3")
@pytest.mark.asyncio
async def test_step_executes_architect_and_revisable_stage():
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
        ) -> tuple[ArchitectureSpec, GateDecision]:
            spec = await run_fn(None)
            from sdlc.core.models import GateOutcome

            decision = GateDecision(
                gate="architecture",
                approved=True,
                outcome=GateOutcome.APPROVE,
                decided_by="human",
            )
            return spec, decision

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
                output = ArchitectureSpec(
                    overview="Test arch overview",
                    decisions=[
                        ArchitectureDecision(
                            id="ADR-1",
                            decision="Use vertical slices",
                            rationale="Decoupling",
                        )
                    ],
                )

            return _RoleResult()

        async def judge(self, *a: Any, **k: Any) -> QualityScore:
            return QualityScore(score=1.0, judge="contract", rationale="Good")

        async def record(self, *a: Any, **k: Any) -> None:
            self.recorded = True

        async def retain(self, *a: Any, **k: Any) -> None:
            self.retained = True

    ctx = _StubCtx()
    cfg = PipelineConfig(roles={"architect": RoleConfig(model="claude-3-5-sonnet")})
    idea = IdeaBrief(title="Test Idea", description="Test desc", mode=ProjectMode.GREENFIELD)
    reqs = ClarifiedRequirements(
        summary="Test reqs",
        functional_requirements=[],
        non_functional_requirements=[],
        out_of_scope=[],
        open_questions=[],
    )

    spec, gate = await architecture.step(
        ctx,
        cfg=cfg,
        idea=idea,
        requirements=reqs,
        codebase_map=None,
        memory_watermark=None,
    )

    assert isinstance(spec, ArchitectureSpec)
    assert isinstance(gate, GateDecision)
    assert spec.overview == "Test arch overview"
    assert gate.approved is True
    assert ctx.recorded is True
    assert ctx.retained is True
