"""E-72 YAML storage shape (spec §7.2)."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest
from pydantic import ValidationError

from sdlc.graph import GraphSchemaError, PipelineGraph, from_yaml, to_yaml

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


def _fixture_text() -> str:
    # read_text uses universal newlines, so a CRLF checkout still reads as LF.
    return FIXTURE.read_text(encoding="utf-8")


def test_fixture_is_in_canonical_yaml_form():
    """The committed fixture is byte-identical to to_yaml of itself."""
    text = _fixture_text()
    assert to_yaml(from_yaml(text)) == text


def test_round_trip_equality():
    graph = from_yaml(_fixture_text())
    assert from_yaml(to_yaml(graph)) == graph


def test_to_yaml_is_a_fixpoint():
    once = to_yaml(from_yaml(_fixture_text()))
    assert to_yaml(from_yaml(once)) == once


def test_yaml_keeps_cosmetics():
    text = _fixture_text()
    assert "position:" in text and "label: Plan gate" in text
    graph = from_yaml(text)
    assert any(n.label == "Plan gate" for n in graph.nodes)


def test_to_yaml_is_order_independent():
    """NFR-10, per-module pattern: byte-identical across input order."""
    data = from_yaml(_fixture_text()).model_dump(mode="json", exclude_defaults=True)
    nodes, edges = data["nodes"][:4], data["edges"][:4]
    expected = to_yaml(PipelineGraph.model_validate({**data, "nodes": nodes, "edges": edges}))
    for ns in itertools.permutations(nodes):
        for es in itertools.permutations(edges):
            graph = PipelineGraph.model_validate({**data, "nodes": list(ns), "edges": list(es)})
            assert to_yaml(graph) == expected


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("schema_version: 1\nnodes: [\n", "not valid YAML"),
        ("- just\n- a list\n", "must be a mapping"),
        ("", "must be a mapping"),
        ("schema_version: 2\nnodes: []\nedges: []\n", "unsupported graph schema_version 2"),
        ("schema_version: true\nnodes: []\nedges: []\n", "unsupported graph schema_version True"),
        ("nodes: []\nedges: []\n", "unsupported graph schema_version None"),
    ],
)
def test_from_yaml_document_errors(text, match):
    with pytest.raises(GraphSchemaError, match=match):
        from_yaml(text)


@pytest.mark.parametrize(
    "text",
    [
        "schema_version: 1\nnodes:\n- id: Bad#Id\n  type: architect\nedges: []\n",
        "schema_version: 1\nnodes:\n- id: a\n  type: architect\n  role:\n    modle: x\nedges: []\n",
    ],
)
def test_from_yaml_shape_failure_is_one_exception_type(text):
    with pytest.raises(GraphSchemaError) as info:
        from_yaml(text)
    assert isinstance(info.value.__cause__, ValidationError)


def test_graph_schema_error_is_a_value_error():
    assert issubclass(GraphSchemaError, ValueError)
