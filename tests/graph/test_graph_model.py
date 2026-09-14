"""E-72 stored schema: parsing is shape-only (spec §5, D5)."""

from __future__ import annotations

import itertools

import pytest
from pydantic import ValidationError

from sdlc.graph import GraphEdge, GraphNode, NodePort, PipelineGraph


def _node(**kw):
    return {"id": "architect", "type": "architect", **kw}


def _edge(**kw):
    return {
        "source": "architect",
        "source_port": "spec",
        "target": "architecture",
        "target_port": "artifact",
        **kw,
    }


def _graph(nodes=None, edges=None, **kw):
    return {
        "schema_version": 1,
        "nodes": nodes if nodes is not None else [_node()],
        "edges": edges if edges is not None else [],
        **kw,
    }


@pytest.mark.parametrize("bad_id", ["", "Architect", "1st", "arch#1", "arch:x", "arch.x", "a-b"])
def test_node_id_shape(bad_id):
    with pytest.raises(ValidationError):
        GraphNode.model_validate(_node(id=bad_id))


@pytest.mark.parametrize("good_type", ["architect", "gate.plan", "gate.architecture"])
def test_node_type_accepts_one_dot(good_type):
    assert GraphNode.model_validate(_node(type=good_type)).type == good_type


@pytest.mark.parametrize("bad_type", ["Gate.plan", "gate..plan", "a.b.c", "gate.", ""])
def test_node_type_shape(bad_type):
    with pytest.raises(ValidationError):
        GraphNode.model_validate(_node(type=bad_type))


@pytest.mark.parametrize("field", ["source", "source_port", "target", "target_port"])
def test_edge_endpoint_shape(field):
    with pytest.raises(ValidationError):
        GraphEdge.model_validate(_edge(**{field: "Bad#Name"}))


def test_edge_max_traversals_is_positive():
    with pytest.raises(ValidationError):
        GraphEdge.model_validate(_edge(max_traversals=0))
    assert GraphEdge.model_validate(_edge(max_traversals=1)).max_traversals == 1


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (GraphNode, _node(params={"model": "x"})),
        (GraphEdge, _edge(weight=1)),
        (PipelineGraph, _graph(name="x")),
        (GraphNode, _node(position={"x": 1, "y": 2, "z": 3})),
    ],
)
def test_extra_keys_forbidden(model, data):
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_role_typo_is_rejected_not_dropped():
    with pytest.raises(ValidationError, match="unknown role key"):
        GraphNode.model_validate(_node(role={"modle": "anthropic:x"}))


def test_gate_typo_is_rejected_not_dropped():
    with pytest.raises(ValidationError, match="unknown gate key"):
        GraphNode.model_validate(_node(type="gate.plan", gate={"polcy": "soft"}))


def test_gate_bare_policy_shorthand_not_accepted():
    """Spec §5: PipelineConfig.gates' `plan: soft` coercion is NOT mirrored."""
    with pytest.raises(ValidationError):
        GraphNode.model_validate(_node(type="gate.plan", gate="soft"))


def test_role_and_gate_carry_core_models_verbatim():
    node = GraphNode.model_validate(
        _node(role={"kind": "proposer", "model": "m"}, gate={"policy": "soft"})
    )
    assert node.role is not None and node.role.model == "m"
    assert node.gate is not None and node.gate.policy.value == "soft"


@pytest.mark.parametrize("version", [None, 2, 0, True, 1.0, "1"])
def test_schema_version_must_be_int_one(version):
    data = _graph()
    if version is None:
        del data["schema_version"]
    else:
        data["schema_version"] = version
    with pytest.raises(ValidationError):
        PipelineGraph.model_validate(data)


def test_parse_is_shape_only():
    """Dangling edge, unknown type, duplicate ids and incompatible ports all
    PARSE -- rejecting them is validate.py's (E-73)."""
    graph = PipelineGraph.model_validate(
        _graph(
            nodes=[_node(), _node(), _node(id="x", type="no.such_type")],
            edges=[
                _edge(target="missing_node"),
                _edge(source_port="spec", target="x", target_port="guidance"),
            ],
        )
    )
    assert len(graph.nodes) == 3 and len(graph.edges) == 2


def test_models_are_frozen():
    node = GraphNode.model_validate(_node())
    with pytest.raises(ValidationError):
        node.id = "other"  # type: ignore[misc]


def test_order_normalization():
    nodes = [_node(id="c"), _node(id="a", label="A"), _node(id="b")]
    edges = [_edge(source="c"), _edge(source="a"), _edge(source="a", target_port="z")]
    graphs = [
        PipelineGraph.model_validate(_graph(nodes=list(ns), edges=list(es)))
        for ns in itertools.permutations(nodes)
        for es in itertools.permutations(edges)
    ]
    assert all(g == graphs[0] for g in graphs)
    assert [n.id for n in graphs[0].nodes] == ["a", "b", "c"]
    assert [(e.source, e.target_port) for e in graphs[0].edges] == [
        ("a", "artifact"),
        ("a", "z"),
        ("c", "artifact"),
    ]


def test_explicit_empty_role_differs_from_absent_role():
    assert GraphNode.model_validate(_node(role={})) != GraphNode.model_validate(_node())


def test_out_port_cannot_be_optional_or_collect():
    with pytest.raises(ValidationError):
        NodePort(name="spec", direction="out", payload="ArchitectureSpec", required=False)
    with pytest.raises(ValidationError):
        NodePort(name="spec", direction="out", payload="ArchitectureSpec", multiplicity="many")
    port = NodePort(name="spec", direction="in", payload=None, required=False, multiplicity="many")
    assert port.multiplicity == "many"
