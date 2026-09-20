# tests/test_dashboard_run_graph_routes.py
"""E-75 spec §6.2, §7.1-§7.3: run graph, run state and validate routes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from temporalio.client import WorkflowExecutionStatus
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.service import RPCError, RPCStatusCode

from sdlc.core.models import PipelineConfig
from sdlc.dashboard import graph_wire
from sdlc.dashboard.api import create_router
from sdlc.dashboard.run_graph import RunGraphs
from sdlc.graph import NODE_TYPES, UNKNOWN_STAGE, GraphRouter, GraphRunView, resolve_stage, validate
from sdlc.graph.store import GraphStore, RunGraphPointer
from sdlc.workflows.graph_catalog import build_run_input
from tests.fakes.canned import greenfield_idea
from tests.graph.fixtures.registries import edge, graph, node, port_out, registry, stage

FIXTURE = Path(__file__).parent / "graph" / "fixtures" / "pre_code.graph.yaml"
RUN_INPUT = build_run_input(greenfield_idea(), PipelineConfig())


class _NoPoller:
    def __getattr__(self, name):
        raise AssertionError(f"run-graph route touched the poller: {name}")


class _Handle:
    def __init__(
        self,
        *,
        wf_type="GraphWorkflow",
        status=WorkflowExecutionStatus.RUNNING,
        view=None,
        missing=False,
        history_gone=False,
        query_error=None,
    ):
        self.wf_type, self.status, self._view, self.missing = wf_type, status, view, missing
        self.history_gone, self.query_error = history_gone, query_error
        self.history_reads = 0
        self.queries = 0

    async def describe(self):
        if self.missing:
            raise RPCError("not found", RPCStatusCode.NOT_FOUND, b"")
        return SimpleNamespace(workflow_type=self.wf_type, status=self.status)

    async def fetch_history_events(self):
        self.history_reads += 1
        if self.history_gone:
            raise RPCError("history purged", RPCStatusCode.NOT_FOUND, b"")
        [payload] = await pydantic_data_converter.encode([RUN_INPUT])
        attrs = SimpleNamespace(input=SimpleNamespace(payloads=[payload]))
        yield SimpleNamespace(workflow_execution_started_event_attributes=attrs)

    async def query(self, name):
        assert name == "graph_view"
        self.queries += 1
        if self.query_error is not None:
            raise self.query_error
        return None if self._view is None else self._view.model_dump(mode="json")


class _Client:
    data_converter = pydantic_data_converter

    def __init__(self, handles):
        self.handles = handles

    def get_workflow_handle(self, run_id):
        return self.handles.get(run_id) or _Handle(missing=True)


def _live_view() -> GraphRunView:
    topology = validate(RUN_INPUT.graph, NODE_TYPES, roles=RUN_INPUT.roles).topology
    assert topology is not None
    return GraphRunView(
        graph_sha=RUN_INPUT.graph.content_sha(), state=GraphRouter(topology).start().state
    )


@pytest.fixture
def setup(tmp_path):
    handles = {
        "graph-run": _Handle(view=_live_view()),
        "closed-run": _Handle(status=WorkflowExecutionStatus.COMPLETED, view=_live_view()),
        "legacy-run": _Handle(wf_type="FeatureWorkflow"),
        "purged-run": _Handle(status=WorkflowExecutionStatus.COMPLETED, history_gone=True),
        "broken-run": _Handle(
            status=WorkflowExecutionStatus.FAILED,
            view=_live_view(),
            query_error=RuntimeError("no worker"),
        ),
    }
    client = _Client(handles)

    async def get_client():
        return client

    store = GraphStore(tmp_path)
    app = FastAPI()
    app.include_router(create_router(_NoPoller(), run_graphs=RunGraphs(get_client, store=store)))
    return TestClient(app), handles, store


def test_graph_route_decodes_the_start_input_and_backfills_the_store(setup):
    client, handles, store = setup
    r = client.get("/runs/graph-run/graph")
    assert r.status_code == 200
    assert r.json() == graph_wire.graph_response(RUN_INPUT.graph).model_dump(mode="json")
    assert store.get(RUN_INPUT.graph.content_sha()) == RUN_INPUT.graph
    client.get("/runs/graph-run/graph")
    assert handles["graph-run"].history_reads == 1  # start input cached per run


def test_legacy_and_unknown_runs(setup):
    client, _, _ = setup
    for path in ("/runs/legacy-run/graph", "/runs/legacy-run/graph_state"):
        r = client.get(path)
        assert r.status_code == 200 and r.json() == {"kind": "no_graph", "reason": "legacy_run"}
    assert client.get("/runs/nope/graph").status_code == 404
    assert client.get("/runs/nope/graph_state").status_code == 404


def test_purged_history_is_404_and_query_failure_is_502_uncached(setup):
    client, handles, _ = setup
    assert client.get("/runs/purged-run/graph").status_code == 404
    assert client.get("/runs/purged-run/graph_state").status_code == 404
    assert client.get("/runs/broken-run/graph_state").status_code == 502
    assert client.get("/runs/broken-run/graph_state").status_code == 502
    assert handles["broken-run"].queries == 2  # a failure is never cached


def test_graph_state_projects_the_view(setup):
    client, _, _ = setup
    body = client.get("/runs/graph-run/graph_state").json()
    assert body["kind"] == "state"
    assert body["graph_sha"] == RUN_INPUT.graph.content_sha()
    assert body["nodes"]["intake"]["status"] == "running"
    assert body["outcome"] == {"state": "running", "reason": None, "result": None}


def test_a_closed_run_is_queried_once(setup):
    client, handles, _ = setup
    first = client.get("/runs/closed-run/graph_state").json()
    second = client.get("/runs/closed-run/graph_state").json()
    assert first == second
    assert handles["closed-run"].queries == 1
    assert first["outcome"]["reason"] == "interrupted:completed"  # router still running
    assert first["pending"] == []


def test_validate_route_serves_validate_plus_executable(setup):
    client, _, _ = setup
    graph = graph_wire.parse_text(FIXTURE.read_text(encoding="utf-8")).graph
    r = client.post("/graphs/validate", json={"graph": graph})
    assert r.status_code == 200
    severities = {i["severity"] for i in r.json()["issues"]}
    assert "not_executable" in severities
    assert client.post("/graphs/validate", json={"yaml": "x"}).status_code == 422


def test_capabilities_stay_false():
    assert graph_wire.catalog().capabilities.model_dump(by_alias=True) == {
        "validate": False,
        # E-77 flips save/load live (R-11); validate and run_graph stay
        # false until the canvas follow-up (spec D7).
        "save": True,
        "load": True,
        "run_graph": False,
    }


def test_served_catalog_opens_the_run_graph_routes_to_the_http_provider(setup):
    """Happy path of the reported symptom (bug canvas-run-mode, E75-OQ-1 (a)):
    with the run-graph routes mounted, the catalog the http provider gates on
    must declare run_graph and validate true -- today it serves the pre-flip
    caps, so runGraph.ts's can('run_graph') keeps refusing the live routes
    and canvas run mode only works on the mock provider."""
    client, _, _ = setup
    caps = client.get("/graphs/catalog").json()["capabilities"]
    assert caps == {"validate": True, "save": True, "load": True, "run_graph": True}


# ---------------------------------------------------------------------------
# E-77 T036 (RED): registry drift, per-run pointers and retention (FR-021..FR-023).
# A run pinned a graph containing 'ghost', a type the current registry no
# longer has. Today run_graph.py:111-112 raises on that drift (a 500 on both
# routes); the store's pointer + registry snapshot APIs (T011) are the inputs
# the T037 fallback reads.
# ---------------------------------------------------------------------------

_GHOST = stage("ghost", port_out("out", "ImplementationPlan"))  # canonical_stage=None
_SNAP_REG = registry(_GHOST, *list(NODE_TYPES.values()))  # the registry the run started under
_DRIFT_GRAPH = graph(
    [node("ghost", "ghost"), node("code", "code")],
    [edge("ghost.out", "code.plan")],
)
_DRIFT_INPUT = RUN_INPUT.model_copy(update={"graph": _DRIFT_GRAPH})


class _DriftHandle(_Handle):
    """A run whose pinned start input contains the drifted type."""

    def __init__(self, run_input, **kw):
        super().__init__(**kw)
        self._run_input = run_input

    async def fetch_history_events(self):
        self.history_reads += 1
        if self.history_gone:
            raise RPCError("history purged", RPCStatusCode.NOT_FOUND, b"")
        [payload] = await pydantic_data_converter.encode([self._run_input])
        attrs = SimpleNamespace(input=SimpleNamespace(payloads=[payload]))
        yield SimpleNamespace(workflow_execution_started_event_attributes=attrs)


@pytest.fixture
def drift_setup(tmp_path):
    handles = {
        "drift-run": _DriftHandle(_DRIFT_INPUT, status=WorkflowExecutionStatus.COMPLETED),
        "drift-snap-run": _DriftHandle(_DRIFT_INPUT, status=WorkflowExecutionStatus.COMPLETED),
        "gone-run": _Handle(missing=True),  # retention expired; pointer survives
        "gone-bare": _Handle(missing=True),  # retention expired; no pointer
        "legacy-run": _Handle(wf_type="FeatureWorkflow"),
    }
    client = _Client(handles)

    async def get_client():
        return client

    store = GraphStore(tmp_path)
    sha = store.put(_DRIFT_GRAPH)  # identity file + the run's layout
    snap = store.put_registry(_SNAP_REG)
    for run_id in ("drift-snap-run", "gone-run"):
        store.put_pointer(
            RunGraphPointer(
                run_id=run_id,
                graph_sha=sha,
                layout_sha=_DRIFT_GRAPH.document_sha(),
                registry_sha=snap,
                roles=RUN_INPUT.roles,
                started_at=datetime.now(UTC),
            )
        )
    app = FastAPI()
    app.include_router(create_router(_NoPoller(), run_graphs=RunGraphs(get_client, store=store)))
    # server errors surface as 500 responses so the RED assertions compare
    # today's drift raise against the 200s the contract promises
    return TestClient(app, raise_server_exceptions=False), handles, store


def test_registry_drift_serves_the_graph_and_reports_unavailable_state(drift_setup):
    """(a) FR-021: a history-present run whose pinned graph no longer validates
    gets the graph served (200) and an explicit unavailable/registry_drift
    state -- never a server error."""
    client, _, _ = drift_setup
    r = client.get("/runs/drift-run/graph")
    assert r.status_code == 200, r.text  # RED: 500 today (run_graph.py:111-112)
    body = r.json()
    assert body["kind"] == "graph" and body["sha"] == _DRIFT_GRAPH.content_sha()
    s = client.get("/runs/drift-run/graph_state")
    assert s.status_code == 200, s.text  # RED: 500 today
    state = s.json()
    assert state["kind"] == "unavailable"
    assert state["reason"] == "registry_drift"
    assert state["problems"], "drift problems must be carried"


def test_a_pointer_registry_snapshot_restores_normal_projection(drift_setup):
    """(b)+(f) FR-022: the pointer names the registry snapshot the run started
    under; against it the graph validates and graph_state projects normally,
    with each node's canonical_stage == resolve_stage of its type under that
    registry -- 'unknown' for the drifted type's unmapped entry."""
    client, _, _ = drift_setup
    s = client.get("/runs/drift-snap-run/graph_state")
    assert s.status_code == 200, s.text  # RED: 500 today (the pointer is ignored)
    body = s.json()
    assert body["kind"] == "state"
    assert body["graph_sha"] == _DRIFT_GRAPH.content_sha()
    for n in _DRIFT_GRAPH.nodes:
        expected = resolve_stage(n.type, _SNAP_REG)
        assert body["nodes"][n.id]["canonical_stage"] == expected  # RED: field absent today
    assert body["nodes"]["ghost"]["canonical_stage"] == UNKNOWN_STAGE


def test_describe_not_found_with_a_pointer_serves_the_layout_graph(drift_setup):
    """(c) FR-012/FR-013: after retention, the pointer still names the stored
    graph and layout; /graph serves it and /graph_state answers
    unavailable/retention_expired instead of 404."""
    client, _, _ = drift_setup
    r = client.get("/runs/gone-run/graph")
    assert r.status_code == 200, r.text  # RED: 404 today
    assert r.json()["kind"] == "graph"
    assert r.json()["sha"] == _DRIFT_GRAPH.content_sha()
    s = client.get("/runs/gone-run/graph_state")
    assert s.status_code == 200, s.text  # RED: 404 today
    state = s.json()
    assert state["kind"] == "unavailable"
    assert state["reason"] == "retention_expired"
    assert state["problems"] == []


def test_describe_not_found_without_a_pointer_and_legacy_runs_stay_as_today(drift_setup):
    """(d)+(e) pins: no pointer and no history is 404 on both routes; a
    FeatureWorkflow run keeps NoGraph on both."""
    client, _, _ = drift_setup
    assert client.get("/runs/gone-bare/graph").status_code == 404
    assert client.get("/runs/gone-bare/graph_state").status_code == 404
    for path in ("/runs/legacy-run/graph", "/runs/legacy-run/graph_state"):
        r = client.get(path)
        assert r.status_code == 200 and r.json() == {"kind": "no_graph", "reason": "legacy_run"}
