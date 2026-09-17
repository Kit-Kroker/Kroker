# tests/test_dashboard_run_graph_routes.py
"""E-75 spec §6.2, §7.1-§7.3: run graph, run state and validate routes."""

from __future__ import annotations

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
from sdlc.graph import NODE_TYPES, GraphRouter, GraphRunView, validate
from sdlc.graph.store import GraphStore
from sdlc.workflows.graph_catalog import build_run_input
from tests.fakes.canned import greenfield_idea

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
        "save": False,
        "load": False,
        "run_graph": False,
    }
