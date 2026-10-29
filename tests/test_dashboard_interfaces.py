# tests/test_dashboard_interfaces.py
"""GET /interfaces (018 T074 RED; read-routes.md §interfaces, data-model §2.3).

The wire module and route are absent -- every route request 404s and the
guarded import raises, which is the RED. Ground truth the route must serve:
harness containment declarations (claude_code native+hook at
harness/claude_code.py:77, opencode native at harness/opencode.py:83), the
registry dev harness (opencode at test time, via sdlc.agents.roles.REGISTRY)
and the adapters' own rules_unenforceable under the shipped policy.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sdlc.dashboard.read_routes import register_read_routes
from sdlc.graph.store import GraphStore
from tests.test_dashboard_run_graph_routes import _Client

COLUMNS = ["layers", "strict", "family", "installed", "checkpoint", "session"]
LAYERS_CELLS = {
    "claude_code": "native + hook",
    "opencode": "native",
    "cursor": "none",
    "crew": "per role harness",
}


class _NoPoller:
    def __getattr__(self, name):
        raise AssertionError(f"interfaces route touched the poller: {name}")


@pytest.fixture
def client(tmp_path):
    async def get_client():
        return _Client({})

    from sdlc.dashboard.run_graph import RunGraphs

    app = FastAPI()
    graphs = RunGraphs(get_client, store=GraphStore(tmp_path))
    app.include_router(register_read_routes(_NoPoller(), run_graphs=graphs))
    return TestClient(app)


def _body(client) -> dict:
    r = client.get("/interfaces")
    assert r.status_code == 200, r.text  # RED: 404 today
    return r.json()


def _cell(body: dict, harness: str, key: str) -> dict:
    """One row's cell by column key; the body's own column order is the index."""
    row = next(r for r in body["rows"] if r["harness"] == harness)
    index = [c["key"] for c in body["columns"]].index(key)
    return row["cells"][index]


def test_columns_in_key_order(client):
    body = _body(client)
    assert [c["key"] for c in body["columns"]] == COLUMNS


def test_layers_cells_match_the_adapter_declarations(client):
    body = _body(client)
    for harness, expected in LAYERS_CELLS.items():
        assert _cell(body, harness, "layers")["text"] == expected


def test_installed_checkpoint_and_session_are_not_measured_on_every_row(client):
    body = _body(client)
    for row in body["rows"]:
        if row["planned"]:
            continue  # a planned row measures nothing; planned dominates
        for key in ("installed", "checkpoint", "session"):
            assert _cell(body, row["harness"], key)["state"] == "not_measured", (
                row["harness"],
                key,
            )


def test_pyai_is_all_planned(client):
    body = _body(client)
    pyai = next(r for r in body["rows"] if r["harness"] == "pyai")
    assert pyai["planned"] is True
    for cell in pyai["cells"]:
        assert cell["state"] == "planned"


def test_family_fills_only_the_registry_dev_harness_row(client):
    from sdlc.agents.roles import REGISTRY

    body = _body(client)
    dev_harness = REGISTRY["dev"].harness
    for row in body["rows"]:
        if row["planned"]:
            continue  # a planned row measures nothing, family included
        cell = _cell(body, row["harness"], "family")
        if row["harness"] == dev_harness:
            assert cell["state"] != "not_measured", row["harness"]
        else:
            assert cell["state"] == "not_measured", row["harness"]


def test_strict_parity_against_rules_unenforceable(client, tmp_path, monkeypatch):
    """R-8 note: apply_containment runs ONLY here, inside a temp dir -- never
    in the route. For claude_code and opencode the route's strict cell must
    carry exactly what each adapter's rules_unenforceable computes."""
    from sdlc.harness.base import HarnessRequest
    from sdlc.harness.claude_code import ClaudeCodeHarness
    from sdlc.harness.containment import load_policy
    from sdlc.harness.opencode import OpenCodeHarness

    policy = load_policy()
    body = _body(client)
    adapters = {"claude_code": ClaudeCodeHarness(), "opencode": OpenCodeHarness()}
    for harness, adapter in adapters.items():
        workdir = tmp_path / harness
        workdir.mkdir()
        monkeypatch.chdir(workdir)
        request = HarnessRequest(prompt="parity", cwd=str(workdir))
        report = adapter.apply_containment(policy, request)
        strict = _cell(body, harness, "strict")
        if not report.rules_unenforceable:
            assert strict["state"] == "yes", (harness, strict)
        else:
            assert strict["state"] in ("partial", "no"), (harness, strict)
            for rule in report.rules_unenforceable:
                assert rule in strict["text"], (harness, rule, strict["text"])
        for rule in report.rules_enforced:
            if rule not in report.rules_unenforceable:
                assert rule not in strict["text"], (harness, rule, strict["text"])


def test_importing_the_wire_module_writes_nothing(tmp_path, monkeypatch):
    # The module-scope rule: importing sdlc.dashboard.interfaces_wire creates
    # no files. RED: the module is absent, so the import raises. Once landed,
    # a chdir'd temp dir must stay empty across the import.
    monkeypatch.chdir(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    importlib.import_module("sdlc.dashboard.interfaces_wire")
    assert sorted(p.name for p in tmp_path.iterdir()) == before
