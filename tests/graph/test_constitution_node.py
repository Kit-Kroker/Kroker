"""FR-112: the constitution node type, its downstream in-ports, and the
opt-in default-constitution graph.

Partial freeze never rejects (stages/constitution): the type has NO reject
port -- only an optional trigger in, the artifact out, and the shared fail
port. The graph is default.graph.yaml plus one node and five edges; the
default file itself must stay byte-identical (pinned below) because its
content_sha identifies every stored run built on it.
"""

from __future__ import annotations

import hashlib

import pytest

from sdlc.core.models import RoleConfig
from sdlc.graph import NODE_TYPES, find_port, from_yaml, validate
from sdlc.workflows.graph_catalog import GRAPHS_DIR
from tests.graph.fixtures.registries import roles

# Pinned on purpose (E-72 identity discipline): FR-112 adds a SEPARATE graph
# and must not re-identify the default one. If this fails, default.graph.yaml
# changed -- a schema decision, not a test to update blindly.
DEFAULT_GRAPH_SHA = "fec96d09f7813dfb48597f6f6ab52c0f29b5440e6efe359d7bb90fe240ab4684"

CONSTITUTION_EDGES = {
    ("intake", "ok", "constitution", "trigger"),
    ("intake", "brownfield", "constitution", "trigger"),
    ("constitution", "constitution", "clarify", "constitution"),
    ("constitution", "constitution", "architect", "constitution"),
    ("constitution", "constitution", "planner", "constitution"),
}

# default-constitution is opt-in: NOT in graph_catalog.SHIPPED_NAMES until a
# later task wires selection, so this module loads it by path.
GRAPH_NAMES = ("default", "default-research", "seeded", "default-constitution")


def _graph(name: str):
    return from_yaml((GRAPHS_DIR / f"{name}.graph.yaml").read_text(encoding="utf-8"))


def _roles() -> dict[str, RoleConfig]:
    return roles(constitution=RoleConfig(kind="proposer", model="anthropic:glm-5.2"))


def _keys(graph) -> set[tuple[str, str, str, str]]:
    return {(e.source, e.source_port, e.target, e.target_port) for e in graph.edges}


# --- the catalog spec ---------------------------------------------------------


def test_constitution_spec_metadata():
    spec = NODE_TYPES["constitution"]
    assert spec.kind == "stage"
    assert spec.role == "constitution"
    assert spec.canonical_stage == "constitution"
    assert spec.budget_after == "continuing"


def test_constitution_spec_ports():
    spec = NODE_TYPES["constitution"]
    table = {(p.direction, p.name): (p.payload, p.required, p.terminal) for p in spec.ports}
    assert table == {
        ("in", "trigger"): (None, False, None),
        ("out", "constitution"): ("Constitution", True, None),
        ("out", "fail"): ("NodeFailure", True, "failed"),
    }


def test_constitution_has_no_reject_port():
    """Partial freeze never rejects (design ruling): no terminal reject out."""
    assert find_port(NODE_TYPES["constitution"], "reject", "out") is None


@pytest.mark.parametrize("type_", ["clarify", "architect", "plan"])
def test_downstream_types_take_an_optional_constitution_in_port(type_):
    port = find_port(NODE_TYPES[type_], "constitution", "in")
    assert port is not None
    assert (port.payload, port.required, port.multiplicity) == ("Constitution", False, "one")


# --- the graphs ---------------------------------------------------------------


def test_default_graph_bytes_are_pinned():
    digest = hashlib.sha256((GRAPHS_DIR / "default.graph.yaml").read_bytes()).hexdigest()
    assert digest == DEFAULT_GRAPH_SHA


@pytest.mark.parametrize("name", GRAPH_NAMES)
def test_every_graph_yaml_validates(name):
    report = validate(_graph(name), roles=_roles())
    assert report.problems == ()
    assert report.topology is not None


def test_constitution_graph_is_default_plus_constitution():
    """Exactly default's nodes and edges plus one node and the five edges:
    nothing else about the default topology may drift."""
    base = _graph("default")
    graph = _graph("default-constitution")
    assert {n.id for n in graph.nodes} == {n.id for n in base.nodes} | {"constitution"}
    assert {n.type for n in graph.nodes if n.id == "constitution"} == {"constitution"}
    assert _keys(graph) == _keys(base) | CONSTITUTION_EDGES


def test_constitution_graph_node_types_match_default():
    """Every node the two graphs share keeps default's type (ids alone lie)."""
    base = {n.id: n.type for n in _graph("default").nodes}
    graph = {n.id: n.type for n in _graph("default-constitution").nodes}
    for node_id, type_ in base.items():
        assert graph[node_id] == type_


def test_constitution_edges_present():
    assert CONSTITUTION_EDGES <= _keys(_graph("default-constitution"))
