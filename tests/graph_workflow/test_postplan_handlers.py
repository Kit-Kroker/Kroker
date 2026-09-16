"""E-74 §6: post-plan handlers and handler coverage."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sdlc.core.models import PipelineConfig
from sdlc.graph import NODE_TYPES
from sdlc.graph.router import Activation
from sdlc.stages.analyze.models import AnalysisReport
from sdlc.stages.plan.models import DevTask, ImplementationPlan
from sdlc.vcs import IntegrationHandle
from sdlc.workflows.graph_catalog import NOT_EXECUTABLE, SHIPPED
from sdlc.workflows.graph_nodes import HANDLERS, postplan
from sdlc.workflows.graph_nodes.base import NodeContext, RunFacts, StoredPayload
from sdlc.workflows.models import AnalyzeResult, BuildResult, PullRequest, SeededWork, TaskResult
from tests.fakes.canned import ARCH, PLAN, greenfield_idea


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


def _nc(node_id: str, graph="default", payloads=None, host=None, seeded=None):
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
        topology=None,
        payloads=payloads or {},
        carries={},
    )


def _act(node_id, inputs=None):
    return Activation(
        activation_id=f"{node_id}#1",
        node_id=node_id,
        round=1,
        inputs=inputs or {},
        unavailable_ports={},
    )


def test_plan_check_halts_on_an_invalid_graph_and_syncs_a_valid_one():
    bad = ImplementationPlan(
        tasks=[
            DevTask(id="a", title="a", description="a", acceptance_criteria=["x"], depends_on=["z"])
        ]
    )
    nc = _nc("plan_check", payloads={"plan#1.approve": StoredPayload(model=bad, producer="plan#1")})
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
        integration_diff={"files": []},
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
