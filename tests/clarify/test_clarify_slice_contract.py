import inspect
import pathlib
from typing import Any

import pytest

from sdlc.core.context import StageServices
from sdlc.stages import clarify


def test_slice_exports_a_narrow_surface():
    assert callable(clarify.step)
    assert isinstance(clarify.ACTIVITIES, list)


def test_agents_arrive_in_the_signature_not_from_the_registry():
    # The boot cycle: agents/roles.py imports the clarify slice, so a step
    # importing the registry back deadlocks the worker.
    params = inspect.signature(clarify.step).parameters
    for name in ("clarify_agent", "route_agent", "probe_agent"):
        assert name in params, name
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY

    src = pathlib.Path("src/sdlc/stages/clarify/step.py").read_text(encoding="utf-8")
    assert "agents.roles" not in src


@pytest.mark.clause("CLARIFY-1.1")
def test_step_takes_a_stage_context_and_never_the_workflow():
    first = list(inspect.signature(clarify.step).parameters)[0]
    assert first == "ctx"
    # A step is testable with stubs alone -- no workflow, no Temporal env.
    assert StageServices


@pytest.mark.clause("CLARIFY-1.2")
def test_step_returns_clarified_requirements():
    from sdlc.models import ClarifiedRequirements

    ret = inspect.signature(clarify.step).return_annotation
    assert ret is ClarifiedRequirements or ret == "ClarifiedRequirements"


@pytest.mark.clause("CLARIFY-1.3")
@pytest.mark.asyncio
async def test_step_resolves_questions_via_ask_and_wait_or_suggested():
    from sdlc.benchmarks.models import QualityScore
    from sdlc.core.models import GateConfig, GatePolicy, IdeaBrief, PipelineConfig, ProjectMode
    from sdlc.models import ClarifiedRequirements, OpenQuestion

    class _StubCtx:
        def __init__(self) -> None:
            self.asked = False

        def stage(self, *a: Any, **k: Any) -> None:
            pass

        def emit(self, *a: Any, **k: Any) -> None:
            pass

        async def recall(self, *a: Any, **k: Any) -> Any:
            from sdlc.models import RecallSnapshot

            return RecallSnapshot(query_hash="q", bank="b", watermark="w", items=[])

        async def cached_stage(self, *a: Any, **k: Any) -> tuple[ClarifiedRequirements, bool]:
            q = OpenQuestion(
                id="q1", question="What?", why_it_matters="Because", suggested_answer="Default"
            )
            return (
                ClarifiedRequirements(
                    summary="s",
                    functional_requirements=[],
                    non_functional_requirements=[],
                    out_of_scope=[],
                    open_questions=[q],
                ),
                False,
            )

        async def ask_and_wait(
            self, questions: Any, *, stage: str, timeout_hours: int
        ) -> dict[str, str]:
            self.asked = True
            return {"q1": "Human Answer"}

        async def judge(self, *a: Any, **k: Any) -> QualityScore:
            return QualityScore(score=1.0, judge="contract", rationale="")

        async def record(self, *a: Any, **k: Any) -> None:
            pass

    # Active gate calls ask_and_wait
    ctx = _StubCtx()
    cfg = PipelineConfig(gates={"clarify": GateConfig(policy=GatePolicy.HARD)})
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    res = await clarify.step(
        ctx, cfg=cfg, idea=idea, clarify_agent=None, route_agent=None, probe_agent=None
    )
    assert ctx.asked is True
    assert res.open_questions[0].answer == "Human Answer"

    # OFF gate uses suggested_answer without ask_and_wait
    ctx_off = _StubCtx()
    cfg_off = PipelineConfig(gates={"clarify": GateConfig(policy=GatePolicy.OFF)})
    res_off = await clarify.step(
        ctx_off, cfg=cfg_off, idea=idea, clarify_agent=None, route_agent=None, probe_agent=None
    )
    assert ctx_off.asked is False
    assert res_off.open_questions[0].answer == "Default"
