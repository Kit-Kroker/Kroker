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
