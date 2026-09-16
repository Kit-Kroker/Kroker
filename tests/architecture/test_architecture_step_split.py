"""E-74 §4.3: architecture.step == prepare + revisable(produce) + finish, with the
same service-call sequence; once-per-stage work happens once across rounds."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sdlc.core.models import GateDecision, GateOutcome, PipelineConfig

# Import names from the SUBMODULE: the package's `step` attribute is the
# shadow-proofed step FUNCTION (_StageModule), never the module.
from sdlc.stages.architecture.step import finish, prepare, produce, step
from tests.fakes.canned import ARCH, CLARIFIED, greenfield_idea


class Ctx:
    def __init__(self, rounds: int = 2):
        self.calls: list[str] = []
        self.rounds = rounds

    def stage(self, status, trace=None):
        self.calls.append(f"stage:{trace}")

    def emit(self, *a, **k):
        self.calls.append("emit")

    async def recall(self, cfg, bank, query, filters):
        self.calls.append("recall")
        return SimpleNamespace(items=[])

    async def run_role(self, cfg, role, model, agent, prompt, **kw):
        self.calls.append(f"run_role:{'guided' if 'Revision guidance' in prompt else 'plain'}")
        return SimpleNamespace(output=ARCH)

    async def cached_stage(self, cfg, stage, input_json, output_type, run_fn, *, prompt_digest=""):
        self.calls.append(f"cached:{stage}")
        return await run_fn(), False

    async def revisable_stage(self, name, cfg, run_fn, *, author_model=""):
        guidance = None
        for _ in range(self.rounds):
            artifact = await run_fn(guidance)
            guidance = "again"
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
    "stage:architecture",
    "recall",
    "cached:architect",
    "run_role:plain",
    "cached:architect",
    "run_role:guided",
    "gate:architecture",
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
            requirements=CLARIFIED,
            idea=greenfield_idea(),
            architect_agent=object(),
            architect_model="m-arch",
        )
    )
    assert ctx.calls == EXPECTED


def test_prepare_produce_finish_compose_to_the_same_sequence():
    ctx = Ctx()
    cfg = PipelineConfig()

    async def go():
        prep = await prepare(ctx, cfg=cfg, idea=greenfield_idea(), architect_model="m-arch")
        a1 = await produce(
            ctx, prep, cfg=cfg, requirements=CLARIFIED, architect_agent=object(), guidance=None
        )
        a2 = await produce(
            ctx, prep, cfg=cfg, requirements=CLARIFIED, architect_agent=object(), guidance="again"
        )
        ctx.calls.append("gate:architecture")
        await finish(
            ctx,
            prep,
            cfg=cfg,
            artifact=a2,
            gate=GateDecision(gate="architecture", outcome=GateOutcome.APPROVE, decided_by="human"),
        )
        return prep, a1

    prep, _ = asyncio.run(go())
    assert ctx.calls == EXPECTED
    assert prep.resolved_model == "m-arch"
    assert prep.spend.role == "architect"
