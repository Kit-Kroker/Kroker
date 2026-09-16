"""Chaos + edge-case characterization for the E-74 plan step split (Task 6).

RED until ``src/sdlc/stages/plan/step.py`` exposes ``prepare`` / ``produce``
/ ``finish``: the import below fails with ``ImportError: cannot import name
'finish'`` -- the failure plan Task 6 Step 2 names for its own split test.

Pins the edge behaviour the split must preserve verbatim:
- prepare: the model resolution chain (explicit planner_model >
  roles["plan"].model > "claude-3-5-sonnet"), falsy values skipping a tier,
  idea=None -> the "plan:feature" recall query, an idea with an empty title
  keeping the empty query suffix, salt == prompt_digest(cfg)
- produce: guidance=None and guidance="" sharing one cache key and one
  prompt, real guidance threading into both, spend/model/agent passthrough,
  requirements accepted but unused
- finish: outcome mapping (APPROVE -> PASS; REVISE and REJECT -> REVISED),
  judge receiving author_model=prep.resolved_model, judge quality landing in
  the benchmark record, retention text f"plan: {n} tasks" (including n == 0)
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from sdlc.benchmarks.models import BenchmarkOutcome
from sdlc.core.models import (
    GateDecision,
    GateOutcome,
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
    RoleConfig,
    RoleUsage,
)
from sdlc.memory.models import MemoryKind
from sdlc.prompts import planner_prompt
from sdlc.stages.plan.models import ImplementationPlan
from sdlc.stages.plan.prompts import prompt_digest
from sdlc.stages.plan.step import finish, prepare, produce
from tests.fakes.canned import ARCH, CLARIFIED, PLAN, greenfield_idea

DEFAULT_MODEL = "claude-3-5-sonnet"


class RecordingCtx:
    """The split test's Ctx seams, instrumented to record arguments."""

    def __init__(self):
        self.calls: list[str] = []
        self.recalls: list[dict] = []
        self.run_roles: list[dict] = []
        self.cache_keys: list[str] = []
        self.judges: list[dict] = []
        self.records: list[object] = []
        self.retains: list[dict] = []

    async def recall(self, cfg, bank, query, filters):
        self.calls.append("recall")
        self.recalls.append({"bank": bank, "query": query, "filters": filters})
        return SimpleNamespace(items=[])

    async def run_role(self, cfg, role, model, agent, prompt, **kw):
        self.calls.append("run_role")
        self.run_roles.append(
            {"role": role, "model": model, "agent": agent, "prompt": prompt, **kw}
        )
        return SimpleNamespace(output=PLAN)

    async def cached_stage(self, cfg, stage, input_json, output_type, run_fn, *, prompt_digest=""):
        self.calls.append(f"cached:{stage}")
        self.cache_keys.append(input_json)
        return await run_fn(), False

    async def judge(self, cfg, artifact_json, stage, author_model):
        self.calls.append("judge")
        self.judges.append(
            {"artifact_json": artifact_json, "stage": stage, "author_model": author_model}
        )
        # score/judge land in a QualityScore, whose JudgeKind literal must
        # accept them -- "contract" is in the pinned set.
        return SimpleNamespace(score=0.9, judge="contract")

    async def record(self, cfg, record):
        self.calls.append("record")
        self.records.append(record)

    async def retain(self, cfg, kind, bank, text, metadata):
        self.calls.append("retain")
        self.retains.append({"kind": kind, "bank": bank, "text": text, "metadata": metadata})


# ---- prepare: model resolution + recall query edges ------------------------


def test_prepare_defaults_resolve_default_model_and_feature_query():
    ctx = RecordingCtx()
    cfg = PipelineConfig()  # no "plan" role in the default mirror
    prep = asyncio.run(prepare(ctx, cfg=cfg))

    assert prep.resolved_model == DEFAULT_MODEL
    assert prep.spend == RoleUsage(role="planner", model=DEFAULT_MODEL)
    assert ctx.recalls == [
        {"bank": cfg.memory.project_bank, "query": "plan:feature", "filters": {"stage": "plan"}}
    ]
    assert prep.salt == prompt_digest(cfg)
    assert prep.snapshot.items == []
    assert isinstance(prep.started, datetime)


def test_prepare_explicit_idea_and_planner_model_win_over_role_config():
    ctx = RecordingCtx()
    cfg = PipelineConfig(roles={"plan": RoleConfig(model="m-role")})
    idea = greenfield_idea()

    prep = asyncio.run(prepare(ctx, cfg=cfg, idea=idea, planner_model="m-plan"))

    assert prep.resolved_model == "m-plan"
    assert prep.spend.model == "m-plan"
    assert ctx.recalls[0]["query"] == "plan:Hello service"


def test_prepare_role_model_used_when_no_explicit_model():
    ctx = RecordingCtx()
    cfg = PipelineConfig(roles={"plan": RoleConfig(model="m-role")})

    prep = asyncio.run(prepare(ctx, cfg=cfg))

    assert prep.resolved_model == "m-role"
    assert ctx.recalls[0]["query"] == "plan:feature"
    # the salt digests the role model, so it differs from the default cfg's
    assert prep.salt == prompt_digest(cfg)
    assert prep.salt != prompt_digest(PipelineConfig())


def test_prepare_empty_planner_model_does_not_shadow_role_model():
    ctx = RecordingCtx()
    cfg = PipelineConfig(roles={"plan": RoleConfig(model="m-role")})

    prep = asyncio.run(prepare(ctx, cfg=cfg, planner_model=""))

    assert prep.resolved_model == "m-role"


def test_prepare_falsy_planner_and_role_models_fall_to_default():
    ctx = RecordingCtx()
    cfg = PipelineConfig(roles={"plan": RoleConfig(model="")})

    prep = asyncio.run(prepare(ctx, cfg=cfg, planner_model=""))

    assert prep.resolved_model == DEFAULT_MODEL
    assert prep.spend == RoleUsage(role="planner", model=DEFAULT_MODEL)


def test_prepare_idea_with_empty_title_keeps_empty_query_suffix():
    ctx = RecordingCtx()
    cfg = PipelineConfig()
    idea = IdeaBrief(title="", description="d", mode=ProjectMode.GREENFIELD)

    asyncio.run(prepare(ctx, cfg=cfg, idea=idea))

    # a present-but-empty title is not idea=None: no "feature" fallback
    assert ctx.recalls[0]["query"] == "plan:"


# ---- produce: guidance + passthrough edges ---------------------------------


def _produce_once(ctx, prep, cfg, *, guidance=None, agent=None, requirements=None):
    async def go():
        return await produce(
            ctx,
            prep,
            cfg=cfg,
            architecture=ARCH,
            requirements=requirements,
            planner_agent=agent,
            guidance=guidance,
        )

    return asyncio.run(go())


def test_produce_none_guidance_uses_plain_cache_key_and_unguided_prompt():
    ctx = RecordingCtx()
    cfg = PipelineConfig()
    prep = asyncio.run(prepare(ctx, cfg=cfg))

    out = _produce_once(ctx, prep, cfg, guidance=None)

    assert out is PLAN
    assert ctx.cache_keys == [ARCH.model_dump_json()]
    assert ctx.run_roles[0]["prompt"] == planner_prompt(ARCH.model_dump_json(), [], None)


def test_produce_guidance_threads_into_cache_key_and_prompt():
    ctx = RecordingCtx()
    cfg = PipelineConfig()
    prep = asyncio.run(prepare(ctx, cfg=cfg))

    _produce_once(ctx, prep, cfg, guidance="cover the error path")

    assert ctx.cache_keys == [ARCH.model_dump_json() + "cover the error path"]
    assert ctx.run_roles[0]["prompt"] == planner_prompt(
        ARCH.model_dump_json(), [], "cover the error path"
    )


def test_produce_empty_guidance_is_cache_and_prompt_equivalent_to_none():
    ctx = RecordingCtx()
    cfg = PipelineConfig()
    prep = asyncio.run(prepare(ctx, cfg=cfg))

    _produce_once(ctx, prep, cfg, guidance=None)
    _produce_once(ctx, prep, cfg, guidance="")

    assert ctx.cache_keys[0] == ctx.cache_keys[1]
    assert ctx.run_roles[0]["prompt"] == ctx.run_roles[1]["prompt"]


def test_produce_passes_prep_model_spend_and_agent_to_run_role():
    ctx = RecordingCtx()
    cfg = PipelineConfig()
    prep = asyncio.run(prepare(ctx, cfg=cfg, planner_model="m-plan"))
    agent = object()

    _produce_once(ctx, prep, cfg, agent=agent)

    call = ctx.run_roles[0]
    assert call["role"] == "planner"
    assert call["model"] == "m-plan"
    assert call["agent"] is agent
    assert call["into"] is prep.spend


def test_produce_accepts_none_agent_and_unused_requirements():
    ctx = RecordingCtx()
    cfg = PipelineConfig()
    prep = asyncio.run(prepare(ctx, cfg=cfg))

    out = _produce_once(ctx, prep, cfg, requirements=CLARIFIED, agent=None)

    assert out is PLAN
    assert ctx.run_roles[0]["agent"] is None


# ---- finish: outcome mapping, judge contract, retention edges --------------


def _finish_once(ctx, prep, cfg, artifact, outcome):
    async def go():
        await finish(
            ctx,
            prep,
            cfg=cfg,
            artifact=artifact,
            gate=GateDecision(gate="plan", outcome=outcome, decided_by="human"),
        )

    asyncio.run(go())


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (GateOutcome.APPROVE, BenchmarkOutcome.PASS),
        (GateOutcome.REVISE, BenchmarkOutcome.REVISED),
        (GateOutcome.REJECT, BenchmarkOutcome.REVISED),
    ],
)
def test_finish_maps_gate_outcome_to_benchmark_outcome(outcome, expected):
    ctx = RecordingCtx()
    cfg = PipelineConfig()
    prep = asyncio.run(prepare(ctx, cfg=cfg))

    _finish_once(ctx, prep, cfg, PLAN, outcome)

    assert ctx.records[0].outcome is expected


def test_finish_judge_gets_prep_model_and_quality_lands_in_record():
    ctx = RecordingCtx()
    cfg = PipelineConfig()
    prep = asyncio.run(prepare(ctx, cfg=cfg, planner_model="m-plan"))

    _finish_once(ctx, prep, cfg, PLAN, GateOutcome.APPROVE)

    assert ctx.judges == [
        {
            "artifact_json": PLAN.model_dump_json(),
            "stage": "planner",
            "author_model": "m-plan",
        }
    ]
    rec = ctx.records[0]
    assert rec.stage == "plan"
    assert rec.role == "planner"
    assert rec.model == "m-plan"
    assert rec.quality.score == 0.9
    assert rec.quality.judge == "contract"


def test_finish_retain_message_counts_tasks():
    ctx = RecordingCtx()
    cfg = PipelineConfig()
    prep = asyncio.run(prepare(ctx, cfg=cfg))

    _finish_once(ctx, prep, cfg, PLAN, GateOutcome.APPROVE)

    assert ctx.retains == [
        {
            "kind": MemoryKind.STAGE_SUMMARY,
            "bank": cfg.memory.project_bank,
            "text": f"plan: {len(PLAN.tasks)} tasks",
            "metadata": {"stage": "plan", "run_id": "direct-execution"},
        }
    ]


def test_finish_zero_task_plan_retains_zero_count():
    ctx = RecordingCtx()
    cfg = PipelineConfig()
    prep = asyncio.run(prepare(ctx, cfg=cfg))
    empty = ImplementationPlan(tasks=[], confidence=0.5)

    _finish_once(ctx, prep, cfg, empty, GateOutcome.APPROVE)

    assert ctx.retains[0]["text"] == "plan: 0 tasks"
