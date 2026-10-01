"""Which model answered: the FR-006 forwarding suite (004 T025, US1).

Every scenario drives the pipeline through the replay harness
(FeatureWorkflow on a real time-skipping worker) with T006's recording
fakes: each fake resolver records ``(agent name, model id)`` into
``tests.fakes.fake_agents.MODEL_RESOLUTIONS`` (autouse-cleared per test) —
the id that actually SERVED the request, not the resolver's return value.

Expected on this branch (forwarding not yet implemented):
(a) RED — architect under an override is served by the registry id, the
    memo key carries the raw string, not the ``fwd1:`` salt;
(b) RED — the clarify fan-out pair both resolve the registry id;
(c) GREEN — a role not overridden keeps its registry id (pin, E-scope);
(d) GREEN — an override equal to the registry model behaves exactly like
    no override (pin, E1);
(e) RED — a benchmark arm default that differs from the registry never
    reaches the agents (the equal-to-registry half is asserted too, as a
    pin, because with default == registry the two are E1-equivalent);
(f) RED — the research sub-question fan-out passes no ``model=`` (its
    usage label already names inp.model — that half is a pin);
(g) RED — the architect's research tool resolves the registry id because
    ResearchDeps cannot yet carry the override.

(f) observes the fan-out through the impl's ``_agent`` seam with a spy
(the fan-out runs the agent in-process inside its activity — the e2e
scenarios fake plan_research into the degraded empty decomposition for
exactly this reason, so no scenario exercises the fan-out under fakes);
its HTTP-layer bound is T015's stub test. (g) calls the toolset function
from workflow code so the nested t_research.run crosses to the fake
research agent's model_request activity and lands in MODEL_RESOLUTIONS.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.agents.loader import PROPOSER_ROLES
from sdlc.agents.roles import STAGE_MODELS, resolve_role_model
from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.benchmarks.models import Arm, BenchmarkCell, CaseSpec
from sdlc.benchmarks.workflow import _cell_config
from sdlc.core.models import HarnessKind, PipelineConfig, RoleConfig
from sdlc.memoization.activities import cache_get, cache_put
from sdlc.pricing import PriceUsageInput
from sdlc.stages.research.deps import ResearchDeps
from sdlc.stages.research.models import ResearchBrief, SubQuestion
from sdlc.stages.research.stage import SubQuestionInput, _research_subquestion_impl
from sdlc.workflows import role_host
from tests.fakes.canned import greenfield_idea
from tests.fakes.fake_agents import MODEL_RESOLUTIONS, fake_agent_activities
from tests.replay.harness import FEATURE_STARTER, capture
from tests.replay.scenarios import SCENARIOS

with workflow.unsafe.imports_passed_through():
    from sdlc.stages.research.toolset import research_subquery

pytestmark = [pytest.mark.temporal]

_OVERRIDE = "openai:gpt-5.2"
_OPUS = "anthropic:claude-opus-4-8"
_HARNESS_PIN = {
    "dev": "zai-coding-plan/glm-5.2",
    "test": "zai-coding-plan/glm-5.2",
    "devops": "zai-coding-plan/glm-5.2",
}


def _scenario(name: str):
    return next(s for s in SCENARIOS if s.name == name)


def _ids() -> list[tuple[str, str | None]]:
    return list(MODEL_RESOLUTIONS)


def _price_models(history) -> list[str]:
    """Every scheduled price_usage input's model, in order (the priced-model
    label — decode pattern per tests/durability/test_priced_usage_parity.py)."""
    converter = pydantic_data_converter.payload_converter
    models: list[str] = []
    for ev in history.events:
        if not ev.HasField("activity_task_scheduled_event_attributes"):
            continue
        attrs = ev.activity_task_scheduled_event_attributes
        if attrs.activity_type.name != "price_usage":
            continue
        (value,) = converter.from_payloads(list(attrs.input.payloads), [PriceUsageInput])
        models.append(value.model)
    return models


def _spy_content_key(monkeypatch) -> list[tuple[str, str]]:
    """Record (stage, model slot) of every memo key _cached_stage computes —
    the workflow runs in-process under UnsandboxedWorkflowRunner, so the
    patched module attribute is exactly what workflow code calls."""
    real = role_host.content_key
    calls: list[tuple[str, str]] = []

    def spy(stage, input_json, prompt_sha, model_id, upstream_recall_ref):
        calls.append((stage, model_id))
        return real(stage, input_json, prompt_sha, model_id, upstream_recall_ref)

    monkeypatch.setattr(role_host, "content_key", spy)
    return calls


async def _capture_with_override(
    scenario_name: str,
    monkeypatch,
    tmp_path,
    *,
    role: str,
    model: str,
    memo: bool,
    content_key_calls: list | None = None,
    cache_subdir: str = "memo",
):
    """One capture of the named scenario with `role` overridden to `model`.
    `memo` additionally enables memoization (the e2e config keeps it off, so
    the memo activities are registered here only when they will fire).
    `cache_subdir` isolates each run's memo root — two runs sharing a root
    would make the second eat the first's cache hits and skip its stages."""
    base = _scenario(scenario_name)

    def cfg() -> PipelineConfig:
        c = base.cfg()
        if memo:
            c.memoization_enabled = True
        if role is not None:
            c.roles[role] = RoleConfig(kind="proposer", model=model)
        return c

    sc = base
    if memo:
        monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path / cache_subdir))
        sc = dataclasses.replace(
            base, activities=lambda: [*base.activities(), cache_get, cache_put]
        )
    sc = dataclasses.replace(sc, cfg=cfg)
    return await capture(sc, FEATURE_STARTER, monkeypatch, tmp_path)


@pytest.mark.asyncio
async def test_a_serial_role_override_is_served_and_named_by_the_override(monkeypatch, tmp_path):
    """(a) FR-006/SC-001: architect under `openai:gpt-5.2` — the recording
    fake serves it, the priced model names it, and the memo key salts it."""
    key_calls = _spy_content_key(monkeypatch)
    cap = await _capture_with_override(
        "greenfield_happy",
        monkeypatch,
        tmp_path,
        role="architect",
        model=_OVERRIDE,
        memo=True,
    )
    assert ("architect_agent", _OVERRIDE) in _ids(), (
        f"the architect was not served by the override; recorded: {_ids()!r}"
    )
    assert _OVERRIDE in _price_models(cap.history), "the priced model does not name the override"
    assert ("architect", f"fwd1:{_OVERRIDE}") in key_calls, (
        f"the architect memo key does not carry the fwd1 salt; slots: "
        f"{[m for s, m in key_calls if s == 'architect']!r}"
    )


@pytest.mark.asyncio
async def test_b_clarify_override_reaches_both_fanout_agents(monkeypatch, tmp_path):
    """(b) E2: an override for `clarify` must reach clarify_route_agent AND
    clarify_probe_agent — they share the role's model without being registry
    roles, so the label/model divergence would reappear here."""
    await _capture_with_override(
        "clarify_fanout", monkeypatch, tmp_path, role="clarify", model=_OVERRIDE, memo=False
    )
    assert ("clarify_route_agent", _OVERRIDE) in _ids(), (
        f"clarify_route_agent was not served by the override; recorded: {_ids()!r}"
    )
    assert ("clarify_probe_agent", _OVERRIDE) in _ids(), (
        f"clarify_probe_agent was not served by the override; recorded: {_ids()!r}"
    )


@pytest.mark.asyncio
async def test_c_a_role_not_overridden_keeps_its_registry_model(monkeypatch, tmp_path):
    """(c) pin (green now and after): planner, not overridden in a run whose
    architect is, still resolves its registry id."""
    await _capture_with_override(
        "greenfield_happy", monkeypatch, tmp_path, role="architect", model=_OVERRIDE, memo=False
    )
    assert ("planner_agent", STAGE_MODELS["plan"]) in _ids(), (
        f"planner was not served by its registry model; recorded: {_ids()!r}"
    )


@pytest.mark.asyncio
async def test_d_override_equal_to_registry_behaves_as_no_override(monkeypatch, tmp_path):
    """(d) pin, E1: an override naming the registry model must be
    indistinguishable from no override — same resolution ids (compared across
    two full runs) and no fwd1 salt in any memo key."""
    key_calls = _spy_content_key(monkeypatch)
    await _capture_with_override(
        "greenfield_happy",
        monkeypatch,
        tmp_path,
        role="architect",
        model=STAGE_MODELS["architect"],
        memo=True,
        cache_subdir="memo-equal",
    )
    equal_ids = _ids()
    MODEL_RESOLUTIONS.clear()
    await _capture_with_override(
        "greenfield_happy",
        monkeypatch,
        tmp_path,
        role=None,
        model="",
        memo=True,
        cache_subdir="memo-plain",
    )
    plain_ids = _ids()
    assert equal_ids == plain_ids, (
        f"an override equal to the registry model changed the serving ids: "
        f"{equal_ids!r} != {plain_ids!r}"
    )
    assert not any(model.startswith("fwd1:") for _, model in key_calls), (
        f"an equal override salted a memo key: {key_calls!r}"
    )


@pytest.mark.asyncio
async def test_e_benchmark_arm_default_serves_every_overridable_proposer_role(
    monkeypatch, tmp_path
):
    """(e) US1 scenario 3: an arm `default` fans out to the proposer roles.
    The equal-to-registry half is a pin (with default == registry the two are
    E1-equivalent, so it can only assert cfg coverage); the discriminating
    half uses a default that DIFFERS from the registry and asserts the
    serving ids — RED until forwarding lands."""
    base = _scenario("greenfield_happy")
    spec = CaseSpec(
        case_id="t025e",
        idea_summary="x",
        harnesses=["opencode"],
        models=[],
        judge_model="google:gemini-3.5-flash",
    )

    arm = Arm(
        name="t025e-registry-equal", default=STAGE_MODELS["architect"], role_models=_HARNESS_PIN
    )
    cell = BenchmarkCell(
        case_id=spec.case_id,
        harness=HarnessKind.OPENCODE,
        arm_name=arm.name,
        role_models=arm.resolve(),
    )
    cfg_equal = _cell_config(base.cfg(), greenfield_idea(), spec, cell, bench_run_id="t025e-a")
    for role in PROPOSER_ROLES:
        assert cfg_equal.roles[role].model == STAGE_MODELS["architect"], (
            f"the arm default did not fan out to proposer role {role!r}"
        )

    arm_b = Arm(name="t025e-opus", default=_OPUS, role_models=_HARNESS_PIN)
    cell_b = BenchmarkCell(
        case_id=spec.case_id,
        harness=HarnessKind.OPENCODE,
        arm_name=arm_b.name,
        role_models=arm_b.resolve(),
    )
    cfg_opus = _cell_config(base.cfg(), greenfield_idea(), spec, cell_b, bench_run_id="t025e-b")
    # _cell_config retargets every gate at the unattended policy; the capture
    # is driven by the scenario's own HARD-gate driver, so restore it.
    reference = base.cfg()
    cfg_opus.gates = reference.gates
    cfg_opus.deploy.enabled = reference.deploy.enabled

    sc = dataclasses.replace(base, cfg=lambda: cfg_opus)
    await capture(sc, FEATURE_STARTER, monkeypatch, tmp_path)
    for agent in ("architect_agent", "planner_agent", "reviewer_agent"):
        assert (agent, _OPUS) in _ids(), (
            f"{agent} was not served by the arm default; recorded: {_ids()!r}"
        )


@pytest.mark.asyncio
async def test_f_research_subquestion_fanout_forwards_and_labels_the_override():
    """(f) D7a: the sub-question fan-out passes the run's research model as
    `model=` when it differs from the registry (RED), and its usage label
    already names inp.model (pin). Driven through the impl's `_agent` seam
    with a spy — see the module docstring for why no scenario covers this
    path under fakes."""
    cfg = PipelineConfig()
    cfg.roles["research"] = RoleConfig(kind="proposer", model=_OVERRIDE)
    inp = SubQuestionInput(
        sub_question=SubQuestion(id="sq-0", question="q"),
        deps=ResearchDeps(
            run_id="t025f", provider="fake", max_searches=1, max_fetches=1, max_cost_usd=1.0
        ),
        model=resolve_role_model(cfg, "research"),
        max_requests=3,
        max_run_cost_usd=1.0,
    )
    spy_kwargs: dict = {}

    class _SpyAgent:
        async def run(self, *args, **kwargs):
            spy_kwargs.update(kwargs)
            return SimpleNamespace(
                output=ResearchBrief(summary="ok"),
                usage=SimpleNamespace(
                    requests=1,
                    input_tokens=1,
                    output_tokens=1,
                    cache_read_tokens=0,
                    cache_write_tokens=0,
                ),
            )

    finding = await _research_subquestion_impl(inp, _agent=_SpyAgent())
    assert spy_kwargs.get("model") == _OVERRIDE, (
        f"the sub-question fan-out did not forward the override (kwargs: {spy_kwargs!r})"
    )
    assert finding.usage.model == _OVERRIDE, (
        "the sub-question usage label does not name the override"
    )


@workflow.defn
class _ResearchToolWorkflow:
    @workflow.run
    async def run(self, deps: ResearchDeps) -> str:
        brief = await research_subquery(deps, "Which pattern applies?")
        return brief.summary


@pytest.mark.asyncio
async def test_g_architect_research_tool_resolves_the_research_override():
    """(g) D7: the architect's research tool's nested t_research call
    resolves the run's research override. research_model is carried on
    ResearchDeps (absent today — pydantic drops the extra key silently, which
    is exactly the RED: the tool call falls back to the registry id)."""
    deps = ResearchDeps(
        run_id="t025g",
        provider="fake",
        max_searches=1,
        max_fetches=1,
        max_cost_usd=1.0,
        research_model=_OVERRIDE,
    )
    brief = ResearchBrief(summary="tool brief")
    activities = fake_agent_activities([("research_agent", ResearchBrief, brief)])
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue="s004-t025g",
            workflows=[_ResearchToolWorkflow],
            activities=activities,
            plugins=[SdlcPydanticAIPlugin()],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                _ResearchToolWorkflow.run,
                deps,
                id="s004-t025g",
                task_queue="s004-t025g",
            )
            summary = await handle.result()
    assert summary == "tool brief"
    assert ("research_agent", _OVERRIDE) in _ids(), (
        f"the architect research tool did not resolve the override; recorded: {_ids()!r}"
    )
