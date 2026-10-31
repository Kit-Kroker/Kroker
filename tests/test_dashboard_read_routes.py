# tests/test_dashboard_read_routes.py
"""GET /graphs/shipped (018 T056 RED; read-routes.md §shipped, data-model §2.2).

The fleet-summary half of the read routes landed with T046; the shipped
route has not -- every request here 404s today, which is the RED. The
fakes follow tests/test_dashboard_fleet_summary.py (itself from the
run-graph routes suite).

Seam assumptions T057 must honour (named for reconciliation):
- the route is registered by the same ``register_read_routes`` router
  (mounted un-prefixed; production adds ``/api``);
- the validate_run_roles check reads the LIVE registry
  (``sdlc.agents.roles.REGISTRY``) resolved to ``{name: model}`` and runs
  ``sdlc.agents.loader.validate_run_roles`` over it -- the monkeypatch
  below drives pass/fail/V8 through that map;
- the limits rows cover PipelineConfig's scalar limits; default-None
  schedule fields (remind/escalate_after_hours) render ``null``.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sdlc.agents import roles
from sdlc.dashboard.read_routes import register_read_routes
from sdlc.graph import NODE_TYPES
from sdlc.graph.store import GraphStore
from sdlc.workflows.graph_catalog import SHIPPED, SHIPPED_NAMES
from tests.test_dashboard_run_graph_routes import _Client


class _NoPoller:
    def __getattr__(self, name):
        raise AssertionError(f"shipped route touched the poller: {name}")


def _gate_count(graph) -> int:
    return sum(
        1
        for n in graph.nodes
        if NODE_TYPES.get(n.type) is not None and NODE_TYPES[n.type].kind == "gate"
    )


@pytest.fixture
def setup(tmp_path, monkeypatch):
    async def get_client():
        return _Client({})

    store = GraphStore(tmp_path)
    puts: list[object] = []

    def _spy_put(graph):
        puts.append(graph)
        raise AssertionError("read route wrote to the store")

    monkeypatch.setattr(store, "put", _spy_put)
    from sdlc.dashboard.run_graph import RunGraphs

    app = FastAPI()
    app.include_router(
        register_read_routes(_NoPoller(), run_graphs=RunGraphs(get_client, store=store))
    )
    return TestClient(app), monkeypatch, puts


def _body(client) -> dict:
    r = client.get("/graphs/shipped")
    assert r.status_code == 200, r.text  # RED: 404 today
    return r.json()


def test_graph_counts_equal_the_shipped_yaml_and_seeded_has_no_gates(setup):
    client, _, _ = setup
    graphs = {g["name"]: g for g in _body(client)["graphs"]}
    assert set(graphs) == set(SHIPPED_NAMES)
    for name, source in SHIPPED.items():
        row = graphs[name]
        assert row["sha"] == source.content_sha()
        assert row["nodes"] == len(source.nodes)
        assert row["edges"] == len(source.edges)
        assert row["gates"] == _gate_count(source)
    assert graphs["seeded"]["gates"] == 0


def test_validate_run_roles_passes_on_the_live_registry(setup):
    client, _, _ = setup
    check = next(c for c in _body(client)["checks"] if c["name"] == "validate_run_roles")
    assert check["state"] == "pass"


def test_validate_run_roles_fails_when_dev_and_reviewer_share_a_family(setup, monkeypatch):
    client, _, _ = setup
    registry = dict(roles.REGISTRY)
    same = "zai-coding-plan/glm-5.3"
    registry["dev"] = registry["dev"].model_copy(update={"model": same})
    registry["reviewer"] = registry["reviewer"].model_copy(update={"model": same})
    monkeypatch.setattr(roles, "REGISTRY", registry)
    check = next(c for c in _body(client)["checks"] if c["name"] == "validate_run_roles")
    assert check["state"] == "fail"
    assert "family" in check["text"]


def test_the_same_weights_note_when_model_ids_are_equal_v8(setup, monkeypatch):
    client, _, _ = setup
    registry = dict(roles.REGISTRY)
    dev_model = registry["dev"].model
    if "adversary" not in registry:
        pytest.skip("registry has no adversary role to collide with")
    registry["adversary"] = registry["adversary"].model_copy(update={"model": dev_model})
    monkeypatch.setattr(roles, "REGISTRY", registry)
    check = next(c for c in _body(client)["checks"] if c["name"] == "validate_run_roles")
    assert check["state"] == "fail"
    assert "same weights" in check["text"]  # V8: a second opinion from the same weights


def test_every_limits_row_present_or_none(setup):
    from sdlc.core.models import PipelineConfig

    client, _, _ = setup
    sections = _body(client)["sections"]
    limits = next(s for s in sections if "limit" in s["title"].lower())
    rows = {row["k"]: row["v"] for row in limits["rows"]}
    cfg = PipelineConfig()
    for key in (
        "max_gate_rounds",
        "gate_timeout_hours",
        "clarify_question_cap",
        "coverage_threshold",
        "run_budget_usd",
    ):
        assert key in rows, f"limits row {key} missing"
        if getattr(cfg, key, None) is not None:
            assert rows[key] == str(getattr(cfg, key))
    # Default-None schedule fields render null, never a fabricated number.
    assert rows.get("remind_after_hours", None) is None
    assert all(row["v"] is None or isinstance(row["v"], str) for row in limits["rows"])


def test_the_route_writes_no_graph_to_the_store(setup):
    client, _, puts = setup
    _body(client)
    assert puts == []  # read-routes rule 1


def test_shipped_wins_over_the_sha_route_in_the_composed_app(tmp_path):
    """Regression (2026-10-31 live report): FastAPI matches in registration
    order, and create_router declared /graphs/{sha} before it included the
    read routes -- so GET /api/graphs/shipped answered 422 "sha must be 64
    lowercase hex chars" and the v5 Graphs screen lived at loading forever.
    The isolated mount above cannot catch this; only the composed router
    (the shape main.py serves) can."""
    from sdlc.dashboard.api import create_router
    from sdlc.dashboard.run_graph import RunGraphs

    async def get_client():
        return _Client({})

    app = FastAPI()
    app.include_router(
        create_router(_NoPoller(), run_graphs=RunGraphs(get_client, store=GraphStore(tmp_path)))
    )
    client = TestClient(app)

    r = client.get("/graphs/shipped")
    assert r.status_code == 200, r.text
    assert r.json()["graphs"], "the shipped catalog came back, not the sha error"

    # A real 64-hex sha still reaches the load route (200, missing store).
    sha = "a" * 64
    r = client.get(f"/graphs/{sha}")
    assert r.status_code == 200, r.text
    assert r.json()["reason"] == "not_found"
