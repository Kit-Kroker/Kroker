from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sdlc.core.models import GateDecision, GateOutcome, PipelineConfig
from sdlc.stages.plan.step import PlanPrep, finish, prepare, produce, step
from tests.fakes.canned import ARCH, PLAN, greenfield_idea


class Ctx:
    def __init__(self):
        self.calls: list[str] = []

    def stage(self, status, trace=None):
        self.calls.append(f"stage:{trace}")

    async def recall(self, cfg, bank, query, filters):
        self.calls.append("recall")
        return SimpleNamespace(items=[])

    async def run_role(self, cfg, role, model, agent, prompt, **kw):
        self.calls.append("run_role")
        return SimpleNamespace(output=PLAN)

    async def cached_stage(self, cfg, stage, input_json, output_type, run_fn, *, prompt_digest=""):
        self.calls.append(f"cached:{stage}:{'guided' if input_json.endswith('again') else 'plain'}")
        return await run_fn(), False

    async def revisable_stage(self, name, cfg, run_fn, *, author_model=""):
        await run_fn(None)
        artifact = await run_fn("again")
        self.calls.append(f"gate:{name}")
        return artifact, GateDecision(gate=name, outcome=GateOutcome.APPROVE, decided_by="human")

    async def judge(self, cfg, artifact_json, stage, author_model):
        self.calls.append("judge")
        return SimpleNamespace(score=None, judge="contract")

    async def record(self, cfg, record):
        self.calls.append("record")

    async def retain(self, cfg, kind, bank, text, metadata):
        self.calls.append("retain")


EXPECTED = [
    "recall",
    "cached:plan:plain",
    "run_role",
    "cached:plan:guided",
    "run_role",
    "gate:plan",
    "judge",
    "record",
    "retain",
]


def test_step_call_sequence_is_unchanged():
    ctx = Ctx()
    asyncio.run(
        step(
            ctx,
            cfg=PipelineConfig(),
            architecture=ARCH,
            idea=greenfield_idea(),
            planner_agent=object(),
            planner_model="m-plan",
        )
    )
    assert ctx.calls == EXPECTED


def test_prepare_produce_finish_compose_to_the_same_sequence():
    ctx = Ctx()
    cfg = PipelineConfig()

    async def go():
        prep = await prepare(ctx, cfg=cfg, idea=greenfield_idea(), planner_model="m-plan")
        await produce(ctx, prep, cfg=cfg, architecture=ARCH, planner_agent=object(), guidance=None)
        p2 = await produce(
            ctx, prep, cfg=cfg, architecture=ARCH, planner_agent=object(), guidance="again"
        )
        ctx.calls.append("gate:plan")
        await finish(
            ctx,
            prep,
            cfg=cfg,
            artifact=p2,
            gate=GateDecision(gate="plan", outcome=GateOutcome.APPROVE, decided_by="human"),
        )
        return prep

    prep = asyncio.run(go())
    assert isinstance(prep, PlanPrep)
    assert ctx.calls == EXPECTED
    assert (prep.resolved_model, prep.spend.role) == ("m-plan", "planner")
