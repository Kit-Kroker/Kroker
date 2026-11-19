"""E-74 §6: post-plan handlers and handler coverage."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sdlc.core.models import GateOutcome, PipelineConfig, RoleConfig
from sdlc.graph import NODE_TYPES, validate
from sdlc.graph.router import Activation
from sdlc.stages.analyze.models import AnalysisReport
from sdlc.stages.plan.models import DevTask, ImplementationPlan
from sdlc.vcs import IntegrationHandle
from sdlc.vcs.models import CodeArtifact
from sdlc.workflows.graph_catalog import NOT_EXECUTABLE, SHIPPED
from sdlc.workflows.graph_nodes import HANDLERS, postplan
from sdlc.workflows.graph_nodes.base import NodeContext, RunFacts, StoredPayload
from sdlc.workflows.models import AnalyzeResult, BuildResult, PullRequest, SeededWork, TaskResult
from tests.fakes.canned import ARCH, PLAN, greenfield_idea
from tests.graph.fixtures.pre_reorder import pre_reorder_default
from tests.graph.fixtures.registries import roles


def test_handlers_cover_every_executable_type():
    assert sorted(HANDLERS) == sorted(t for t in NODE_TYPES if t not in NOT_EXECUTABLE)


class Host:
    def __init__(self):
        self._plan_version = 3
        self.synced = None
        self.stages: list[tuple[str, str]] = []

    async def _board_sync_tasks(self, cfg, version, tasks):
        self.synced = (version, [t.id for t in tasks])

    def _stage(self, status, trace=None):
        self.stages.append((status, trace))


def _nc(node_id: str, graph="default", payloads=None, host=None, seeded=None, topology=None):
    g = SHIPPED[graph]
    node = next(n for n in g.nodes if n.id == node_id)
    facts = RunFacts(
        idea=greenfield_idea(), repo_path="/r", run_id="wf", seeded=seeded, memory_watermark=None
    )
    facts.set_integration(IntegrationHandle(head_sha="base", worktree_path="/wt"))
    return NodeContext(
        ctx=SimpleNamespace(),
        host=host or Host(),
        facts=facts,
        node=node,
        spec=NODE_TYPES[node.type],
        topology=topology,
        payloads=payloads or {},
        carries={},
    )


def _act(node_id, inputs=None, unavailable=None):
    return Activation(
        activation_id=f"{node_id}#1",
        node_id=node_id,
        round=1,
        inputs=inputs or {},
        unavailable_ports=unavailable or {},
    )


def _topology_of(graph):
    """A real Topology for handlers that branch on connectivity (FR-301:
    plan_check's revise branch). The pre-reorder literal carries no revise
    edge, so connected('revise') is False there -- the in-flight shape.

    `validate` is bound at collection time: the replay tests rebind
    sdlc.graph.validate to the SUBMODULE (test_dashboard_fleet_summary's
    documented trap), and a runtime import would pick up the module."""
    extra = {"product": RoleConfig(kind="proposer", model="anthropic:glm-5.2")}
    report = validate(graph, NODE_TYPES, roles=roles(**extra))
    assert report.topology is not None, [p.message for p in report.problems]
    return report.topology


def _bad_plan():
    return ImplementationPlan(
        tasks=[
            DevTask(id="a", title="a", description="a", acceptance_criteria=["x"], depends_on=["z"])
        ]
    )


def test_plan_check_halts_on_an_invalid_graph_and_syncs_a_valid_one():
    """The pre-reorder (in-flight) topology: the gate already approved, so
    a published version exists and the ok path syncs under it; a bad plan
    keeps today's exact halt string."""
    bad = _bad_plan()
    nc = _nc(
        "plan_check",
        payloads={"plan#1.approve": StoredPayload(model=bad, producer="plan#1")},
        topology=_topology_of(pre_reorder_default()),
    )
    out = asyncio.run(
        postplan.plan_check_node(
            nc, _act("plan_check", {"plan": "plan#1.approve"}), PipelineConfig()
        )
    )
    assert (out.port, out.result) == (
        "halt",
        "failed:plan-validation:task 'a' depends on unknown task id(s) ['z']",
    )
    nc = _nc(
        "plan_check", payloads={"plan#1.approve": StoredPayload(model=PLAN, producer="plan#1")}
    )
    out = asyncio.run(
        postplan.plan_check_node(
            nc, _act("plan_check", {"plan": "plan#1.approve"}), PipelineConfig()
        )
    )
    assert (out.port, out.payload, nc.host.synced) == ("ok", PLAN, (3, ["t1"]))


def test_plan_check_revise_returns_the_validator_text_as_planner_guidance():
    """FR-301 D3: on the reordered graph a validator failure rides the
    revise port as a synthesized REVISE GateDecision whose guidance is the
    validator text verbatim -- no human gate opens."""
    nc = _nc(
        "plan_check",
        payloads={"planner#1.plan": StoredPayload(model=_bad_plan(), producer="planner#1")},
        topology=_topology_of(SHIPPED["default"]),
    )
    out = asyncio.run(
        postplan.plan_check_node(
            nc, _act("plan_check", {"plan": "planner#1.plan"}), PipelineConfig()
        )
    )
    assert out.port == "revise"
    decision = out.payload
    assert decision.outcome is GateOutcome.REVISE
    assert decision.decided_by == "policy"
    assert decision.gate == "plan_check"
    assert decision.guidance == "task 'a' depends on unknown task id(s) ['z']"
    assert nc.host.synced is None


def test_plan_check_halt_when_the_revise_loop_is_exhausted():
    """Round 3 on a max_traversals: 2 loop: revise is unavailable at issue
    time, so the failure keeps today's terminal halt with today's string."""
    nc = _nc(
        "plan_check",
        payloads={"planner#3.plan": StoredPayload(model=_bad_plan(), producer="planner#3")},
        topology=_topology_of(SHIPPED["default"]),
    )
    out = asyncio.run(
        postplan.plan_check_node(
            nc,
            _act("plan_check", {"plan": "planner#3.plan"}, unavailable={"revise": "exhausted"}),
            PipelineConfig(),
        )
    )
    assert (out.port, out.result) == (
        "halt",
        "failed:plan-validation:task 'a' depends on unknown task id(s) ['z']",
    )


def test_plan_check_ok_skips_the_sync_before_a_version_exists_and_stashes_for_the_gate():
    """FR-301: plan_check now runs BEFORE gate.plan mints a plan version,
    so the board sync waits for the gate's publish (which reads the
    producer stash); the requirements doc rides the stash so the gate's
    conjunct computes real coverage."""
    from sdlc.stages.requirements.models import (
        FunctionalRequirement,
        Requirements,
        Story,
        requirements_digest,
    )

    story = Story(
        id="US-1",
        narrative="As a user, I want a greeting, so that the service greets me.",
        functional=[FunctionalRequirement(id="FR-1", text="GET /hello returns 200")],
        success_criteria=[],
    )
    req_doc = Requirements(stories=[story], digest=requirements_digest([story]), drafted_by="agent")
    plan = ImplementationPlan(
        tasks=[
            DevTask(
                id="t1", title="t1", description="t1", acceptance_criteria=["x"], covers=["FR-1"]
            )
        ]
    )

    def payloads():
        return {
            "planner#1.plan": StoredPayload(model=plan, producer="planner#1"),
            "requirements#1.requirements": StoredPayload(model=req_doc, producer="requirements#1"),
        }

    inputs = {"plan": "planner#1.plan", "requirements_doc": "requirements#1.requirements"}
    host = Host()
    host._plan_version = None  # pre-gate on the reordered graph: no version minted yet
    nc = _nc(
        "plan_check",
        payloads=payloads(),
        host=host,
        topology=_topology_of(SHIPPED["default-requirements"]),
    )
    nc.carries.setdefault("planner", {})["prep"] = "PREP"
    out = asyncio.run(postplan.plan_check_node(nc, _act("plan_check", inputs), PipelineConfig()))
    assert (out.port, out.payload) == ("ok", plan)
    assert nc.host.synced is None  # no published version yet: the gate's publish syncs
    assert nc.carry("plan_check")["requirements_doc"] is req_doc
    assert nc.carry("plan_check")["validated"] is True
    # the plan stage's prep passes through: the gate reads it from the
    # artifact producer's carry, which is now plan_check
    assert nc.carry("plan_check")["prep"] == "PREP"


def test_seed_nodes_emit_the_seeded_work():
    seeded = SeededWork(arch=ARCH, plan=PLAN)
    spec_nc = _nc("seed_spec", graph="seeded", seeded=seeded)
    plan_nc = _nc("seed_plan", graph="seeded", seeded=seeded)
    assert (
        asyncio.run(postplan.seed_spec_node(spec_nc, _act("seed_spec"), PipelineConfig())).payload
        is ARCH
    )
    out = asyncio.run(postplan.seed_plan_node(plan_nc, _act("seed_plan"), PipelineConfig()))
    assert out.payload is PLAN and plan_nc.host.stages == [("coding", "code")]


def test_code_maps_run_tasks_outcomes(monkeypatch):
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b")

    async def ok(host, *, cfg, plan, repo_path):
        return {"t1": tr}, None

    async def conflict(host, *, cfg, plan, repo_path):
        return {}, "failed:integration-conflict:t1"

    payloads = {"plan_check#1.ok": StoredPayload(model=PLAN, producer="plan_check#1")}
    monkeypatch.setattr(postplan, "run_tasks", ok)
    out = asyncio.run(
        postplan.code_node(
            _nc("code", payloads=payloads),
            _act("code", {"plan": "plan_check#1.ok"}),
            PipelineConfig(),
        )
    )
    assert out.port == "results" and out.payload.task_results == [tr]
    monkeypatch.setattr(postplan, "run_tasks", conflict)
    out = asyncio.run(
        postplan.code_node(
            _nc("code", payloads=payloads),
            _act("code", {"plan": "plan_check#1.ok"}),
            PipelineConfig(),
        )
    )
    assert (out.port, out.result) == ("halt", "failed:integration-conflict:t1")


def test_merge_rejection_and_pr(monkeypatch):
    analysis = AnalyzeResult(
        report=AnalysisReport(traceability=[], summary="s", confidence=0.5),
        untraced=["c"],
        integration_diff=CodeArtifact(),
    )
    payloads = {
        "code#1.results": StoredPayload(model=BuildResult(task_results=[]), producer="code#1"),
        "plan_check#1.ok": StoredPayload(model=PLAN, producer="plan_check#1"),
        "architecture#1.approve": StoredPayload(model=ARCH, producer="architecture#1"),
        "analyze#1.analysis": StoredPayload(model=analysis, producer="analyze#1"),
    }
    inputs = {
        "results": "code#1.results",
        "plan": "plan_check#1.ok",
        "spec": "architecture#1.approve",
        "analysis": "analyze#1.analysis",
    }
    seen = {}

    async def fake_merge(ctx, **kw):
        seen.update(kw)
        return seen.get("next", "rejected:merge:advisory")

    monkeypatch.setattr(postplan, "merge", SimpleNamespace(step=fake_merge))
    out = asyncio.run(
        postplan.merge_node(
            _nc("merge", payloads=payloads), _act("merge", inputs), PipelineConfig()
        )
    )
    assert (out.port, out.result) == ("reject", "rejected:merge:advisory")
    assert seen["untraced"] == ["c"] and seen["base_sha"] == "base" and seen["arch"] is ARCH

    async def pr_merge(ctx, **kw):
        return "https://example.test/pr/1"

    monkeypatch.setattr(postplan, "merge", SimpleNamespace(step=pr_merge))
    out = asyncio.run(
        postplan.merge_node(
            _nc("merge", payloads=payloads), _act("merge", inputs), PipelineConfig()
        )
    )
    assert out.port == "pr" and out.payload == PullRequest(url="https://example.test/pr/1")


@pytest.mark.parametrize(
    "prefix", ["deployed", "merged-not-deployed", "deploy-broken", "deploy-rejected", "rolled-back"]
)
def test_every_deploy_result_rides_the_done_sink_unchanged(monkeypatch, prefix):
    async def fake_deploy(ctx, **kw):
        return f"{prefix}:{kw['pr_url']}"

    monkeypatch.setattr(
        postplan, "deploy", SimpleNamespace(step=fake_deploy, _deploy_plan=lambda cfg, wid: "PLAN")
    )
    payloads = {"merge#1.pr": StoredPayload(model=PullRequest(url="u"), producer="merge#1")}
    out = asyncio.run(
        postplan.deploy_node(
            _nc("deploy", payloads=payloads), _act("deploy", {"pr": "merge#1.pr"}), PipelineConfig()
        )
    )
    assert (out.port, out.result) == ("done", f"{prefix}:u")
