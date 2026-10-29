# tests/test_dashboard_fleet_summary.py
"""GET /fleet/summary (018 T045 RED; R-6, read-routes.md, data-model §2.1).

The route does not exist yet: the import target below is the RED. The fakes
reuse tests/test_dashboard_run_graph_routes.py's handles/client/store; the
poller seam is faked inline.

Seam assumptions T046 must honour (named per the qa brief):
- ``register_read_routes(poller, run_graphs=...)`` returns an APIRouter that
  the test mounts fresh, the same way ``create_router`` is mounted; the
  summary path is ``/fleet/summary`` -- create_router registers
  un-prefixed (the sibling tests hit ``/runs/...``) and production mounts
  ``/api`` around both.
- The poller seam stays ``await poller.snapshot()`` returning a real
  ``FleetSnapshot`` (dashboard/fleet.py); the fake fills only the fields the
  summary consumes (the id lists).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from temporalio.client import WorkflowExecutionStatus
from temporalio.contrib.pydantic import pydantic_data_converter

from sdlc.core.models import GateConfig, PipelineConfig, RunState, RunSummary, TimeoutAction
from sdlc.dashboard.fleet import FleetSnapshot
from sdlc.dashboard.read_routes import register_read_routes
from sdlc.dashboard.run_graph import RunGraphs
from sdlc.graph import NODE_TYPES, GraphRouter, GraphRunView, validate
from sdlc.graph.store import GraphStore
from sdlc.workflows.graph_catalog import SHIPPED, build_run_input
from tests.fakes.canned import greenfield_idea
from tests.test_dashboard_run_graph_routes import (
    RUN_INPUT,
    _Client,
    _Handle,
)

SUMMARY = "/fleet/summary"

_SHIPPED_DEFAULT_SHA = SHIPPED["default"].content_sha()

_GATES_CFG = PipelineConfig(gates={"architecture": GateConfig()})
_GATED_INPUT = build_run_input(greenfield_idea(), _GATES_CFG)


class _InputHandle(_Handle):
    """A run whose pinned start input differs from the module default."""

    def __init__(self, run_input, **kw):
        super().__init__(**kw)
        self._run_input = run_input

    async def fetch_history_events(self):
        self.history_reads += 1
        [payload] = await pydantic_data_converter.encode([self._run_input])
        attrs = SimpleNamespace(input=SimpleNamespace(payloads=[payload]))
        yield SimpleNamespace(workflow_execution_started_event_attributes=attrs)


class _BrokenDescribeHandle(_Handle):
    """A run whose source read raises: the unreadable case."""

    async def describe(self):
        raise RuntimeError("no worker")


class _Poller:
    """Minimal poller seam: a real FleetSnapshot with just the id lists."""

    def __init__(self, open_ids: list[str], closed_ids: list[str]):
        self._open, self._closed = open_ids, closed_ids

    async def snapshot(self) -> FleetSnapshot:
        now = datetime.now(UTC)
        return FleetSnapshot(
            at=now,
            total_open_runs=len(self._open),
            runs=[
                RunState(run_id=i, title=i, mode="greenfield", status="running", started_at=now)
                for i in self._open
            ],
            closed=[
                RunSummary(
                    run_id=i,
                    mode="greenfield",
                    outcome="deployed:x",
                    terminal_stage="code",
                    started_at=now,
                    ended_at=now,
                    duration_s=1.0,
                )
                for i in self._closed
            ],
        )


@pytest.fixture
def setup(tmp_path, monkeypatch):
    # 018 T083: the graph imports live at MODULE scope on purpose. The
    # Temporal replay tests (tests/replay/*, collected earlier) rebind
    # sdlc.graph.validate from the function to the SUBMODULE through the
    # workflow sandbox importer; a runtime `from sdlc.graph import
    # validate` then picks up the module and is not callable. A
    # collection-time import binds the function and keeps it.
    from tests.graph.fixtures.registries import graph as ggraph
    from tests.graph.fixtures.registries import node as gnode

    custom_input = RUN_INPUT.model_copy(
        update={"graph": ggraph([gnode("custom_a", "intake"), gnode("custom_b", "code")], [])}
    )
    gated_input = build_run_input(greenfield_idea(), _GATES_CFG)

    def _view_for(run_input):
        topology = validate(run_input.graph, NODE_TYPES, roles=run_input.roles).topology
        if topology is None:
            return None
        state = GraphRouter(topology).start().state
        return GraphRunView(graph_sha=run_input.graph.content_sha(), state=state)

    handles = {
        "graph-run": _Handle(view=_view_for(RUN_INPUT)),
        "gated-run": _InputHandle(gated_input, view=_view_for(gated_input)),
        "custom-run": _InputHandle(custom_input, view=None),
        "closed-run": _InputHandle(
            RUN_INPUT, status=WorkflowExecutionStatus.COMPLETED, view=_view_for(RUN_INPUT)
        ),
        "legacy-run": _Handle(wf_type="FeatureWorkflow"),
        "unreadable-run": _BrokenDescribeHandle(),
    }
    client = _Client(handles)

    async def get_client():
        return client

    store = GraphStore(tmp_path)
    puts: list[object] = []

    def _spy_put(graph):
        puts.append(graph)
        raise AssertionError("read route wrote to the store")

    monkeypatch.setattr(store, "put", _spy_put)
    poller = _Poller(
        open_ids=["graph-run", "gated-run", "custom-run", "legacy-run", "unreadable-run"],
        closed_ids=["closed-run"],
    )
    app = FastAPI()
    app.include_router(register_read_routes(poller, run_graphs=RunGraphs(get_client, store=store)))
    return TestClient(app), handles, puts


def test_a_shipped_sha_matches_its_name(setup):
    client, _, _ = setup
    body = client.get(SUMMARY).json()
    row = next(r for r in body["runs"] if r["run_id"] == "graph-run")
    assert row["graph_sha"] == _SHIPPED_DEFAULT_SHA
    assert row["graph_name"] == "default"


def test_a_custom_sha_keeps_its_sha_and_loses_the_name(setup):
    client, _, _ = setup
    body = client.get(SUMMARY).json()
    row = next(r for r in body["runs"] if r["run_id"] == "custom-run")
    assert row["graph_sha"] not in {g.content_sha() for g in SHIPPED.values()}
    assert row["graph_sha"] is not None
    assert row["graph_name"] is None


def test_a_legacy_run_is_the_null_arm(setup):
    client, _, _ = setup
    body = client.get(SUMMARY).json()
    row = next(r for r in body["runs"] if r["run_id"] == "legacy-run")
    assert row["graph_sha"] is None
    assert row["arm"] is None
    assert row["traversals"] == []
    assert row["outcome"] is None


def test_an_unreadable_source_is_listed_and_not_served(setup):
    client, _, _ = setup
    body = client.get(SUMMARY).json()
    assert "unreadable-run" in body["unreadable"]
    assert "unreadable-run" not in {r["run_id"] for r in body["runs"]}


def test_traversals_carry_the_back_edges_with_used_and_max(setup):
    client, _, _ = setup
    body = client.get(SUMMARY).json()
    row = next(r for r in body["runs"] if r["run_id"] == "graph-run")
    bounded = [e for e in RUN_INPUT.graph.edges if e.max_traversals is not None]
    assert len(row["traversals"]) == len(bounded)
    for t, e in zip(row["traversals"], bounded, strict=True):
        assert t["used"] == 0  # the start state has traversed nothing
        assert t["max"] == e.max_traversals
        assert t["edge"]["source"] == e.source
        assert t["edge"]["target"] == e.target


def test_the_arm_is_the_dev_entry_of_the_resolved_roles(setup):
    from sdlc.workflows.graph_catalog import resolved_roles

    client, _, _ = setup
    body = client.get(SUMMARY).json()
    row = next(r for r in body["runs"] if r["run_id"] == "graph-run")
    dev = resolved_roles(RUN_INPUT.cfg)["dev"]
    assert row["arm"]["harness"] == (dev.harness.value if dev.harness else None)
    assert row["arm"]["model"] == dev.model


def test_gate_timeouts_come_from_the_run_config(setup):
    client, _, _ = setup
    body = client.get(SUMMARY).json()
    row = next(r for r in body["runs"] if r["run_id"] == "gated-run")
    expected = {"gate": "architecture", "on_timeout": TimeoutAction.REJECT.value}
    assert expected in row["gate_timeouts"]
    # A run without explicit gates still serves the config's own timeouts.
    plain = next(r for r in body["runs"] if r["run_id"] == "graph-run")
    assert plain["gate_timeouts"] == [
        {"gate": name, "on_timeout": cfg.on_timeout.value}
        for name, cfg in PipelineConfig().gates.items()
    ]


def test_the_route_is_get_only_and_writes_nothing(setup):
    client, _, puts = setup
    assert client.post(SUMMARY).status_code == 405
    assert client.put(SUMMARY).status_code == 405
    client.get(SUMMARY)
    assert puts == []  # read-routes rule 1


def test_open_and_closed_runs_both_appear(setup):
    client, _, _ = setup
    ids = {r["run_id"] for r in client.get(SUMMARY).json()["runs"]}
    assert {"graph-run", "closed-run"} <= ids
