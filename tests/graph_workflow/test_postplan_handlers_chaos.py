"""Chaos + edge-case characterization for E-74 Task 18 (post-plan handlers).

RED until ``sdlc.workflows.graph_nodes.postplan`` exists: every test fetches
the module through ``_postplan()``, so each test fails on its own with
``ImportError: cannot import name 'postplan'`` -- the plan's expected RED
reason -- while the file still collects.

Pins the edge behaviour the task specifies:
- seed_spec_node / seed_plan_node raise RuntimeError ("<node> activated on a
  run without SeededWork") when facts.seeded is None; with a SeededWork they
  emit the seeded artifacts by identity and seed_plan mirrors the single
  ("coding", "code") stage event
- analyze_node / merge_node assert facts.integration is not None ("intake
  sets RunFacts.integration before any post-plan node") BEFORE doing any work
- plan_check_node halts with "failed:plan-validation:<error>" for unknown
  dependency ids, two-task cycles and self-cycles (validate_task_graph's
  verbatim strings), and never syncs an invalid graph; a valid plan syncs
  (version, task ids) and passes through as "ok"
- code_node: an exception from run_tasks propagates unchanged; a returned
  failure string becomes the halt result
- merge_node: ANY result starting with "rejected:" rides the reject port
  verbatim; everything else -- an https url or a benchmark-skip string --
  becomes a PullRequest on the pr port; step kwargs thread base_sha,
  worktree and untraced criteria
- deploy_node: whatever the deploy step returns rides the done sink
  verbatim, with pr_url, repo_path and the run id threaded through
"""

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
from sdlc.workflows.graph_catalog import SHIPPED
from sdlc.workflows.graph_nodes.base import NodeContext, RunFacts, StoredPayload
from sdlc.workflows.models import AnalyzeResult, BuildResult, PullRequest, SeededWork
from tests.fakes.canned import ARCH, PLAN, greenfield_idea


def _postplan():
    from sdlc.workflows.graph_nodes import postplan

    return postplan


class Host:
    def __init__(self):
        self._plan_version = 3
        self.synced = None
        self.stages: list[tuple[str, str]] = []

    async def _board_sync_tasks(self, cfg, version, tasks):
        self.synced = (version, [t.id for t in tasks])

    def _stage(self, status, trace=None):
        self.stages.append((status, trace))


class _FakeDeploy:
    """deploy module stand-in recording every threaded argument."""

    def __init__(self):
        self.seen: dict[str, object] = {}

    async def step(self, ctx, **kw):
        self.seen["pr_url"] = kw["pr_url"]
        self.seen["repo_path"] = kw["repo_path"]
        return f"deployed:{kw['pr_url']}"

    def _deploy_plan(self, cfg, run_id):
        self.seen["run_id"] = run_id
        return "PLAN"


def _nc(node_id, *, graph="default", payloads=None, host=None, seeded=None, with_integration=True):
    g = SHIPPED[graph]
    node = next(n for n in g.nodes if n.id == node_id)
    facts = RunFacts(
        idea=greenfield_idea(), repo_path="/r", run_id="wf", seeded=seeded, memory_watermark=None
    )
    if with_integration:
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


def _t(tid, deps=()):
    return DevTask(
        id=tid, title=tid, description=tid, acceptance_criteria=["x"], depends_on=list(deps)
    )


def _analysis(untraced=()):
    return AnalyzeResult(
        report=AnalysisReport(traceability=[], summary="s", confidence=0.5),
        untraced=list(untraced),
        integration_diff={"files": []},
    )


_MERGE_PAYLOADS = lambda: {  # noqa: E731 -- fresh dicts per test
    "code#1.results": StoredPayload(model=BuildResult(task_results=[]), producer="code#1"),
    "plan_check#1.ok": StoredPayload(model=PLAN, producer="plan_check#1"),
    "architecture#1.approve": StoredPayload(model=ARCH, producer="architecture#1"),
    "analyze#1.analysis": StoredPayload(model=_analysis(untraced=["c"]), producer="analyze#1"),
}
_MERGE_INPUTS = {
    "results": "code#1.results",
    "plan": "plan_check#1.ok",
    "spec": "architecture#1.approve",
    "analysis": "analyze#1.analysis",
}


# ---- seed nodes: facts.seeded must exist ---------------------------------------


@pytest.mark.parametrize("node", ["seed_spec", "seed_plan"], ids=["seed.spec", "seed.plan"])
def test_seed_nodes_raise_without_seeded_work(node):
    pp = _postplan()
    handler = getattr(pp, f"{node}_node")

    with pytest.raises(RuntimeError, match=f"{node} activated on a run without SeededWork"):
        asyncio.run(handler(_nc(node, graph="seeded", seeded=None), _act(node), PipelineConfig()))


def test_seed_nodes_emit_the_seeded_work_by_identity():
    pp = _postplan()
    seeded = SeededWork(arch=ARCH, plan=PLAN)
    host = Host()
    spec_nc = _nc("seed_spec", graph="seeded", seeded=seeded)
    plan_nc = _nc("seed_plan", graph="seeded", seeded=seeded, host=host)

    spec_out = asyncio.run(pp.seed_spec_node(spec_nc, _act("seed_spec"), PipelineConfig()))
    plan_out = asyncio.run(pp.seed_plan_node(plan_nc, _act("seed_plan"), PipelineConfig()))

    assert (spec_out.port, spec_out.payload) == ("spec", ARCH)
    assert (plan_out.port, plan_out.payload) == ("plan", PLAN)
    assert host.stages == [("coding", "code")]  # the seeded path's only stage event


# ---- analyze / merge: integration is a precondition ------------------------------


@pytest.mark.parametrize("node", ["analyze", "merge"], ids=["analyze", "merge"])
def test_postplan_nodes_require_integration_before_any_work(node):
    pp = _postplan()
    if node == "analyze":
        payloads = {
            "code#1.results": StoredPayload(model=BuildResult(task_results=[]), producer="code#1"),
            "plan_check#1.ok": StoredPayload(model=PLAN, producer="plan_check#1"),
        }
        inputs = {"results": "code#1.results", "plan": "plan_check#1.ok"}
    else:
        payloads = _MERGE_PAYLOADS()
        inputs = dict(_MERGE_INPUTS)

    with pytest.raises(AssertionError, match="intake sets RunFacts.integration"):
        asyncio.run(
            getattr(pp, f"{node}_node")(
                _nc(node, payloads=payloads, with_integration=False),
                _act(node, inputs),
                PipelineConfig(),
            )
        )


# ---- plan_check: invalid task graphs halt before the sync ------------------------


@pytest.mark.parametrize(
    ("tasks", "error"),
    [
        ([_t("a", ["z"])], "task 'a' depends on unknown task id(s) ['z']"),
        ([_t("a", ["b"]), _t("b", ["a"])], "dependency cycle: a -> b -> a"),
        ([_t("a", ["a"])], "dependency cycle: a -> a"),
        ([_t("a", ["b"]), _t("b", ["c"]), _t("c", ["a"])], "dependency cycle: a -> b -> c -> a"),
    ],
    ids=["unknown-dep", "two-cycle", "self-cycle", "three-cycle"],
)
def test_plan_check_halts_on_invalid_graphs_without_syncing(tasks, error):
    pp = _postplan()
    bad = ImplementationPlan(tasks=list(tasks))
    host = Host()
    nc = _nc(
        "plan_check",
        payloads={"plan#1.approve": StoredPayload(model=bad, producer="plan#1")},
        host=host,
    )

    out = asyncio.run(
        pp.plan_check_node(nc, _act("plan_check", {"plan": "plan#1.approve"}), PipelineConfig())
    )

    assert (out.port, out.result) == ("halt", f"failed:plan-validation:{error}")
    assert host.synced is None  # an invalid graph is never synced


def test_plan_check_syncs_a_valid_graph_and_passes_it_through():
    pp = _postplan()
    host = Host()
    nc = _nc(
        "plan_check",
        payloads={"plan#1.approve": StoredPayload(model=PLAN, producer="plan#1")},
        host=host,
    )

    out = asyncio.run(
        pp.plan_check_node(nc, _act("plan_check", {"plan": "plan#1.approve"}), PipelineConfig())
    )

    assert (out.port, out.payload) == ("ok", PLAN)
    assert host.synced == (3, ["t1"])


# ---- code_node: run_tasks exceptions and failure strings --------------------------


_CODE_PAYLOADS = lambda: {"plan_check#1.ok": StoredPayload(model=PLAN, producer="plan_check#1")}  # noqa: E731
_CODE_INPUTS = {"plan": "plan_check#1.ok"}


def test_code_node_propagates_a_run_tasks_exception(monkeypatch):
    pp = _postplan()
    boom = RuntimeError("worker exploded")

    async def raising(host, *, cfg, plan, repo_path):
        raise boom

    monkeypatch.setattr(pp, "run_tasks", raising)

    with pytest.raises(RuntimeError) as err:
        asyncio.run(
            pp.code_node(
                _nc("code", payloads=_CODE_PAYLOADS()), _act("code", _CODE_INPUTS), PipelineConfig()
            )
        )

    assert err.value is boom


def test_code_node_maps_a_failure_string_to_the_halt_port(monkeypatch):
    pp = _postplan()

    async def conflict(host, *, cfg, plan, repo_path):
        return {}, "failed:integration-conflict:t1"

    monkeypatch.setattr(pp, "run_tasks", conflict)

    out = asyncio.run(
        pp.code_node(
            _nc("code", payloads=_CODE_PAYLOADS()), _act("code", _CODE_INPUTS), PipelineConfig()
        )
    )

    assert (out.port, out.result) == ("halt", "failed:integration-conflict:t1")


# ---- merge_node: rejected prefixes vs pr results ----------------------------------


@pytest.mark.parametrize(
    ("step_result", "expected_port"),
    [
        ("rejected:merge:advisory", "reject"),
        ("rejected:merge:hard", "reject"),
        ("rejected:merge (nothing to merge)", "reject"),
        ("https://example.test/pr/1", "pr"),
        ("skipped: nothing to merge", "pr"),  # benchmark-skip strings ride pr too
    ],
    ids=["advisory", "hard", "paren", "url", "skip"],
)
def test_merge_prefixes_split_reject_from_pr(monkeypatch, step_result, expected_port):
    pp = _postplan()

    async def fake_merge(ctx, **kw):
        return step_result

    monkeypatch.setattr(pp, "merge", SimpleNamespace(step=fake_merge))

    out = asyncio.run(
        pp.merge_node(
            _nc("merge", payloads=_MERGE_PAYLOADS()),
            _act("merge", dict(_MERGE_INPUTS)),
            PipelineConfig(),
        )
    )

    assert out.port == expected_port
    if expected_port == "reject":
        assert out.result == step_result
        assert out.payload is None
    else:
        assert out.result is None
        assert out.payload == PullRequest(url=step_result)


def test_merge_node_threads_the_integration_facts_into_the_step(monkeypatch):
    pp = _postplan()
    seen = {}

    async def fake_merge(ctx, **kw):
        seen.update(kw)
        return "rejected:merge:advisory"

    monkeypatch.setattr(pp, "merge", SimpleNamespace(step=fake_merge))

    asyncio.run(
        pp.merge_node(
            _nc("merge", payloads=_MERGE_PAYLOADS()),
            _act("merge", dict(_MERGE_INPUTS)),
            PipelineConfig(),
        )
    )

    assert seen["base_sha"] == "base"  # from facts.integration
    assert seen["integration_wt"] == "/wt"
    assert seen["untraced"] == ["c"]  # from the analysis payload
    assert seen["arch"] is ARCH
    assert seen["plan"] is PLAN


# ---- deploy_node: any pr url, result on the done sink ------------------------------


@pytest.mark.parametrize(
    "url",
    ["https://example.test/pr/1", "skipped: nothing to merge", ""],
    ids=["url", "skip-string", "empty"],
)
def test_deploy_node_threads_any_pr_url_and_rides_the_done_sink(monkeypatch, url):
    pp = _postplan()
    fake = _FakeDeploy()
    monkeypatch.setattr(pp, "deploy", fake)
    payloads = {"merge#1.pr": StoredPayload(model=PullRequest(url=url), producer="merge#1")}

    out = asyncio.run(
        pp.deploy_node(
            _nc("deploy", payloads=payloads), _act("deploy", {"pr": "merge#1.pr"}), PipelineConfig()
        )
    )

    assert (out.port, out.result) == ("done", f"deployed:{url}")
    assert fake.seen["pr_url"] == url
    assert fake.seen["repo_path"] == "/r"
    assert fake.seen["run_id"] == "wf"
