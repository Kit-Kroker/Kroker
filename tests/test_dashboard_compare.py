# tests/test_dashboard_compare.py
"""GET /compare (018 T067 RED; read-routes.md §compare, data-model §2.4).

The route does not exist yet -- every request 404s, which is the RED. The
fixture tree under tests/fixtures/compare/ was validated against the real
loader chain (build_runs -> 4 graded runs, build_grid -> 2 groups) before
being committed; it carries two arms x two graphs, one unpriced arm and one
truncated JSONL line. The route's runs root is driven through SDLC_RUNS_ROOT
(read-routes.md: $SDLC_RUNS_ROOT or ./runs), matching the recorder's own
root convention.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sdlc.benchmarks.models import CELL_STAGE_ORDER
from sdlc.dashboard.read_routes import register_read_routes
from sdlc.graph.store import GraphStore
from tests.test_dashboard_run_graph_routes import _Client

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "compare"
DEFAULT_SHA = "a021c25b8f7e012faaf9f4de9664d8cc5b11a977c1b878e20d50cfec78b23c38"
SEEDED_SHA = "c1bbef2d33379ca4252d8971ed4b65934dd54e7d4c306a887698df0f0520c5ab"


class _NoPoller:
    def __getattr__(self, name):
        raise AssertionError(f"compare route touched the poller: {name}")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(FIXTURE_ROOT))

    async def get_client():
        return _Client({})

    from sdlc.dashboard.run_graph import RunGraphs

    app = FastAPI()
    app.include_router(
        register_read_routes(
            _NoPoller(), run_graphs=RunGraphs(get_client, store=GraphStore(tmp_path))
        )
    )
    return TestClient(app)


def _body(client) -> dict:
    r = client.get("/compare")
    assert r.status_code == 200, r.text  # RED: 404 today
    return r.json()


def test_an_empty_root_answers_unavailable_with_the_root_path(monkeypatch, tmp_path):
    empty = tmp_path / "no-records"
    empty.mkdir()
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(empty))

    async def get_client():
        return _Client({})

    from sdlc.dashboard.run_graph import RunGraphs

    app = FastAPI()
    app.include_router(
        register_read_routes(
            _NoPoller(), run_graphs=RunGraphs(get_client, store=GraphStore(tmp_path))
        )
    )
    body = _body(TestClient(app))
    assert body["available"] is False
    assert body["root"] == str(empty)


def test_two_arms_times_two_graphs(client):
    body = _body(client)
    assert body["available"] is True
    arms = {a["name"] for a in body["arms"]}
    assert arms == {"glm-5.2", "glm-5.3"}
    assert set(body["graphs"]) == {DEFAULT_SHA, SEEDED_SHA}
    models = {a["name"]: a["model"] for a in body["arms"]}
    assert models["glm-5.3"] == "zai-coding-plan/glm-5.3"
    assert models["glm-5.2"] == "zai-coding-plan/glm-5.2"
    for arm in body["arms"]:
        assert arm["harness"] == "opencode"
        assert {c["graph"] for c in arm["cells"]} == {DEFAULT_SHA, SEEDED_SHA}


def test_a_truncated_jsonl_line_is_skipped_with_no_500(client):
    # run-a1's records.jsonl ends with a half-written line; its run still
    # serves (the priced cell is present) and the route answers 200.
    body = _body(client)
    arm = next(a for a in body["arms"] if a["name"] == "glm-5.3")
    cell = next(c for c in arm["cells"] if c["graph"] == DEFAULT_SHA)
    assert cell["sc"] is not None


def test_an_unpriced_arm_answers_cost_per_case_none(client):
    body = _body(client)
    arm = next(a for a in body["arms"] if a["name"] == "glm-5.2")
    for cell in arm["cells"]:
        if cell["graph"] == DEFAULT_SHA:  # run-b1 carries cost usd null
            assert cell["cost_per_case"] is None


def test_heat_columns_follow_cell_stage_order(client):
    body = _body(client)
    assert body["heat_columns"] == [s for s in CELL_STAGE_ORDER if s in body["heat_columns"]]
    assert body["heat_columns"]  # the fixture carries at least 'code'


def test_importing_the_wire_module_never_imports_benchmarks_report():
    # The data-model rule: report.py must not ride module scope (its import
    # pulls the report table machinery). RED: the module does not exist yet,
    # so the import raises. Once landed, importing it must leave
    # sdlc.benchmarks.report unimported.
    import importlib
    import sys

    sys.modules.pop("sdlc.benchmarks.report", None)
    importlib.import_module("sdlc.dashboard.compare_wire")
    assert "sdlc.benchmarks.report" not in sys.modules
