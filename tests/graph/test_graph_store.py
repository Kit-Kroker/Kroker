# tests/graph/test_graph_store.py
"""E-75 spec §6.1: graphs/<sha>.yaml, put-if-absent, verify-then-trust."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sdlc.graph import from_yaml
from sdlc.graph.store import GraphStore, GraphStoreCorrupt, default_root

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


@pytest.fixture
def graph():
    return from_yaml(FIXTURE.read_text(encoding="utf-8"))


def test_put_writes_sha_named_yaml_and_get_round_trips(tmp_path, graph):
    store = GraphStore(tmp_path)
    sha = store.put(graph)
    assert sha == graph.content_sha()
    assert (tmp_path / f"{sha}.yaml").is_file()
    assert store.get(sha) == graph
    assert list(tmp_path.glob("*.tmp")) == []


def test_put_is_idempotent_and_keeps_a_valid_file(tmp_path, graph):
    store = GraphStore(tmp_path)
    sha = store.put(graph)
    before = (tmp_path / f"{sha}.yaml").stat().st_mtime_ns
    assert store.put(graph) == sha
    assert (tmp_path / f"{sha}.yaml").stat().st_mtime_ns == before


@pytest.mark.parametrize(
    "content",
    ["", "schema_version: 1\nnodes: [\n", "schema_version: 1\nnodes: []\nedges: []\n"],
)
def test_put_replaces_a_truncated_or_corrupt_existing_file(tmp_path, graph, content):
    store = GraphStore(tmp_path)
    target = tmp_path / f"{graph.content_sha()}.yaml"
    target.write_text(content, encoding="utf-8")
    store.put(graph)
    assert store.get(graph.content_sha()) == graph


def test_replace_refused_succeeds_only_if_the_target_then_verifies(tmp_path, graph, monkeypatch):
    store = GraphStore(tmp_path)
    sha = graph.content_sha()

    def racing_replace(src, dst):
        Path(dst).write_text(Path(src).read_text(encoding="utf-8"), encoding="utf-8")
        raise PermissionError("held by a concurrent reader")

    monkeypatch.setattr(os, "replace", racing_replace)
    assert store.put(graph) == sha
    assert list(tmp_path.glob("*.tmp")) == []

    def failing_replace(src, dst):
        raise PermissionError("held")

    other = tmp_path / "other"
    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(PermissionError):
        GraphStore(other).put(graph)


def test_get_missing_is_none_and_corruption_is_loud(tmp_path, graph):
    store = GraphStore(tmp_path)
    assert store.get(graph.content_sha()) is None
    (tmp_path / f"{graph.content_sha()}.yaml").write_text(
        "schema_version: 1\nnodes: []\nedges: []\n", encoding="utf-8"
    )
    with pytest.raises(GraphStoreCorrupt):
        store.get(graph.content_sha())


@pytest.mark.parametrize("bad", ["../x", "ABC", "a" * 63, "g" * 64])
def test_sha_must_be_lowercase_hex_64(tmp_path, bad):
    with pytest.raises(ValueError):
        GraphStore(tmp_path).get(bad)


def test_default_root_resolution(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_GRAPH_STORE", str(tmp_path / "g"))
    assert default_root() == (tmp_path / "g").resolve()
    monkeypatch.delenv("SDLC_GRAPH_STORE")
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path / "runs"))
    assert default_root() == (tmp_path / "graphs").resolve()
    assert GraphStore().root.is_absolute()
