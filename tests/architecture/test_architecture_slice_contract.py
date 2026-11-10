"""Contract tests for the architecture stage vertical slice (spec A §3).

020 T028: rewritten against prepare/produce/finish — the FeatureWorkflow-era
`step` composite is deleted (T027); the graph's architect_node is the
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
from sdlc.stages import architecture
from sdlc.stages.architecture.models import ArchitectureDecision, ArchitectureSpec
from sdlc.stages.architecture.step import finish, prepare, produce
from sdlc.stages.clarify.models import ClarifiedRequirements


def test_slice_exports_a_narrow_surface():
    # 020 T027: `step` is gone from the package surface — the submodule
    # exists, the composite function does not.
    assert "step" not in architecture.__all__
    assert isinstance(architecture.ACTIVITIES, list)
    assert len(architecture.ACTIVITIES) == 0


def test_agents_arrive_in_the_signature_not_from_the_registry():
    params = inspect.signature(produce).parameters
    assert "architect_agent" in params
    assert params["architect_agent"].kind is inspect.Parameter.KEYWORD_ONLY

    src = pathlib.Path("src/sdlc/stages/architecture/step.py").read_text(encoding="utf-8")
    assert "agents.roles" not in src


@pytest.mark.clause("ARCH-1.1")
def test_the_slice_takes_a_stage_context_and_never_the_workflow():
    for fn in (prepare, produce, finish):
        first = list(inspect.signature(fn).parameters)[0]
        assert first == "ctx", fn.__name__
    assert StageServices


@pytest.mark.clause("ARCH-1.2")
def test_produce_returns_an_architecture_spec():
    ret = inspect.signature(produce).return_annotation
    assert "ArchitectureSpec" in str(ret)


@pytest.mark.clause("ARCH-1.3")
@pytest.mark.asyncio
async def test_the_composition_executes_the_architect_and_finishes():
    """prepare → produce → finish runs the architect through the cached
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

    prep = await prepare(ctx, cfg=cfg, idea=idea, architect_model="m-arch")
    spec = await produce(ctx, prep, cfg=cfg, requirements=reqs, architect_agent=object())
    await finish(
        ctx,
        prep,
        cfg=cfg,
        artifact=spec,
        gate=GateDecision(
            gate="architecture", approved=True, outcome=GateOutcome.APPROVE, decided_by="human"
        ),
    )

    assert isinstance(spec, ArchitectureSpec)
    assert spec.overview == "Test arch overview"
    assert ctx.recorded is True
    assert ctx.retained is True
