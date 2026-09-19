"""E-76 pure graph routes: catalog, parse, serialize (spec §5.2-§5.4, §6.3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sdlc.dashboard import graph_wire
from sdlc.dashboard.api import create_router

FIXTURE = Path(__file__).parent / "graph" / "fixtures" / "pre_code.graph.yaml"


class _NoPoller:
    """The graph routes must never touch the fleet poller."""

    def __getattr__(self, name):
        raise AssertionError(f"graph route touched the poller: {name}")


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(create_router(_NoPoller()))
    return TestClient(app)


def test_catalog_route_serves_the_projection(client):
    r = client.get("/graphs/catalog")
    assert r.status_code == 200
    assert r.json() == graph_wire.catalog().model_dump(mode="json")


def test_parse_route_accepts_yaml_text(client):
    text = FIXTURE.read_text(encoding="utf-8")
    r = client.post("/graphs/parse", json={"yaml": text})
    assert r.status_code == 200
    assert r.json() == graph_wire.parse_text(text).model_dump(mode="json")
    assert r.json()["ok"] is True


def test_parse_route_returns_shape_errors_as_200(client):
    r = client.post("/graphs/parse", json={"yaml": "schema_version: 1\nnodes: []\nnodes: []\n"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["shape_errors"][0]["line"] == 3


def test_parse_route_accepts_a_graph_object(client):
    graph = graph_wire.parse_text(FIXTURE.read_text(encoding="utf-8")).graph
    r = client.post("/graphs/parse", json={"graph": graph})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_serialize_route_is_to_yaml(client):
    text = FIXTURE.read_text(encoding="utf-8")
    graph = graph_wire.parse_text(text).graph
    r = client.post("/graphs/serialize", json={"graph": graph})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "yaml": text}


@pytest.mark.parametrize(
    "body",
    [{}, {"yaml": "x", "graph": {}}, {"yaml": 3}, {"text": "x"}, []],
    ids=["empty", "both", "yaml_not_string", "unknown_key", "not_object"],
)
def test_parse_route_rejects_a_malformed_body_with_422(client, body):
    assert client.post("/graphs/parse", json=body).status_code == 422


def test_parse_route_rejects_non_json_with_422(client):
    r = client.post("/graphs/parse", content=b"yaml: x", headers={"content-type": "text/plain"})
    assert r.status_code == 422


def _raw(body: dict) -> bytes:
    # What the browser sends: JSON.stringify does not \u-escape non-ASCII.
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def test_parse_route_caps_the_body_in_utf8_bytes(client):
    # 'é' is two UTF-8 bytes: under the cap in characters, over it in bytes.
    text = "é" * (graph_wire.MAX_GRAPH_BYTES // 2 + 1)
    assert len(_raw({"yaml": text}).decode("utf-8")) < graph_wire.MAX_GRAPH_BYTES
    r = client.post("/graphs/parse", content=_raw({"yaml": text}))
    assert r.status_code == 413


def test_parse_route_accepts_a_body_exactly_at_the_cap(client):
    overhead = len(_raw({"yaml": ""}))
    text = "a" * (graph_wire.MAX_GRAPH_BYTES - overhead)
    r = client.post("/graphs/parse", content=_raw({"yaml": text}))
    assert r.status_code == 200 and r.json()["ok"] is False


def test_serialize_route_rejects_a_yaml_body(client):
    assert client.post("/graphs/serialize", json={"yaml": "x"}).status_code == 422


# --- E-77 T038 (RED): POST /graphs (save) and GET /graphs/{sha} (load) --------
# contracts/http-graphs.md: save answers SaveOk{ok, sha, layout_sha,
# validation == /graphs/validate's}; load answers LoadOk{ok, sha, layout_sha,
# graph} or LoadMissing{ok: false, reason: not_found}. The store points at
# tmp_path through RunGraphs so saves are observable on disk; save/load must
# never touch the Temporal client.


@pytest.fixture
def store_client(tmp_path):
    from sdlc.dashboard.run_graph import RunGraphs
    from sdlc.graph.store import GraphStore

    async def _no_client():
        raise AssertionError("save/load routes must not touch the Temporal client")

    app = FastAPI()
    app.include_router(
        create_router(_NoPoller(), run_graphs=RunGraphs(_no_client, store=GraphStore(tmp_path)))
    )
    return TestClient(app), tmp_path


def _fixture_graph():
    return graph_wire.parse_text(FIXTURE.read_text(encoding="utf-8")).graph


def test_post_graphs_answers_save_ok_with_validate_equal_validation(store_client):
    import re

    client, _ = store_client
    graph = _fixture_graph()
    r = client.post("/graphs", json={"graph": graph})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert re.fullmatch(r"[0-9a-f]{64}", body["sha"])
    assert re.fullmatch(r"[0-9a-f]{64}", body["layout_sha"])
    v = client.post("/graphs/validate", json={"graph": graph})
    assert v.status_code == 200
    assert body["validation"] == v.json()  # identical to /graphs/validate's answer


def test_an_illegal_but_schema_valid_draft_is_still_saved(store_client):
    client, root = store_client
    draft = {
        "schema_version": 1,
        "nodes": [
            {"id": "architect", "type": "architect", "role": {"kind": "proposer", "model": "m1"}}
        ],
        "edges": [
            {"source": "architect", "source_port": "spec", "target": "ghost", "target_port": "spec"}
        ],
    }
    r = client.post("/graphs", json={"graph": draft})
    assert r.status_code == 200
    body = r.json()
    assert body["validation"]["issues"]  # legality problems are reported...
    assert (root / f"{body['sha']}.yaml").is_file()  # ...and the draft is saved anyway


def test_bad_save_bodies_are_rejected_and_write_nothing(store_client):
    client, root = store_client
    assert client.post("/graphs", json={"yaml": "x"}).status_code == 422  # not {graph}
    assert client.post("/graphs", json={"graph": {"schema_version": 2}}).status_code == 422
    over = {
        "graph": {
            "schema_version": 1,
            "nodes": [],
            "edges": [],
            "pad": "a" * graph_wire.MAX_GRAPH_BYTES,
        }
    }
    assert client.post("/graphs", json=over).status_code == 413  # cap beats parsing
    assert list(root.rglob("*")) == []  # nothing written, ever


def test_get_graphs_serves_the_latest_layout_and_layout_selects(store_client):
    client, _ = store_client
    graph = _fixture_graph()
    saved = client.post("/graphs", json={"graph": graph}).json()
    r = client.get(f"/graphs/{saved['sha']}")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["sha"] == saved["sha"]
    assert body["layout_sha"] == saved["layout_sha"]  # the latest layout
    assert body["graph"] == graph
    exact = client.get(f"/graphs/{saved['sha']}", params={"layout": saved["layout_sha"]})
    assert exact.status_code == 200
    assert exact.json()["layout_sha"] == saved["layout_sha"]


def test_unknown_or_malformed_graph_identifiers(store_client):
    client, _ = store_client
    graph = _fixture_graph()
    saved = client.post("/graphs", json={"graph": graph}).json()
    assert client.get(f"/graphs/{'a' * 64}").json() == {"ok": False, "reason": "not_found"}
    unknown_layout = client.get(f"/graphs/{saved['sha']}", params={"layout": "b" * 64})
    assert unknown_layout.json() == {"ok": False, "reason": "not_found"}
    assert client.get("/graphs/zzz").status_code == 422  # non-hex sha, no disk access
    assert client.get(f"/graphs/{saved['sha']}?layout=nothex").status_code == 422


def test_a_second_save_with_moved_nodes_reuses_sha_and_moves_latest(store_client):
    import copy

    client, root = store_client
    graph = _fixture_graph()
    first = client.post("/graphs", json={"graph": graph}).json()
    moved = copy.deepcopy(graph)
    moved["nodes"][0]["position"] = {"x": 999, "y": -1}
    second = client.post("/graphs", json={"graph": moved}).json()
    assert second["sha"] == first["sha"]  # cosmetics never change content identity
    assert second["layout_sha"] != first["layout_sha"]
    got = client.get(f"/graphs/{first['sha']}").json()
    assert got["layout_sha"] == second["layout_sha"]  # GET serves the new latest
    by_id = {n["id"]: n for n in got["graph"]["nodes"]}
    assert by_id[moved["nodes"][0]["id"]]["position"] == {"x": 999, "y": -1}


def test_catalog_reports_save_and_load_true_with_the_rest_as_today(store_client):
    client, _ = store_client
    today = graph_wire.catalog().capabilities.model_dump(mode="json", by_alias=True)
    caps = client.get("/graphs/catalog").json()["capabilities"]
    assert caps["save"] is True and caps["load"] is True
    assert caps["validate"] == today["validate"]  # unchanged
    assert caps["run_graph"] == today["run_graph"]  # unchanged
