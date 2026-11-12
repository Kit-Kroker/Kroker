"""FR-113: the requirements node type, its clarify in-port, and the
opt-in default-requirements graph.

The Product drafter never REJECTS (a partial freeze still flows
downstream -- FR-112's constitution ruling, re-applied): the type has NO
reject port, only optional trigger/constitution/codebase_map ins, the
artifact out, and the shared fail port. The graph is default.graph.yaml
plus one node and three edges; the default file itself must stay
byte-identical (pinned below) because its content_sha identifies every
stored run built on it.

Namespace pin: the node TYPE string "requirements" and clarify's out-PORT
named "requirements" are distinct things -- the type's out-port emits
Requirements, clarify's emits ClarifiedRequirements.
"""

from __future__ import annotations

import hashlib

import pytest

from sdlc.core.models import RoleConfig
from sdlc.graph import NODE_TYPES, PAYLOAD_TYPES, check_node_types, find_port, from_yaml, validate
from sdlc.workflows.graph_catalog import GRAPHS_DIR
from tests.graph.fixtures.registries import roles

# Pinned on purpose (E-72 identity discipline): FR-113 adds a SEPARATE graph
# and must not re-identify the default one. If this fails, default.graph.yaml
# changed -- a schema decision, not a test to update blindly.
DEFAULT_GRAPH_SHA = "fec96d09f7813dfb48597f6f6ab52c0f29b5440e6efe359d7bb90fe240ab4684"

REQUIREMENTS_EDGES = {
    ("intake", "ok", "requirements", "trigger"),
    ("intake", "brownfield", "requirements", "trigger"),
    ("requirements", "requirements", "clarify", "requirements"),
}

# default-requirements is not in graph_catalog.SHIPPED until FR-113 Task 8
# wires selection; this module loads every graph by path so the sha pin below
# stays independent of catalog wiring.
GRAPH_NAMES = (
    "default",
    "default-research",
    "default-constitution",
    "seeded",
    "default-requirements",
)


def _graph(name: str):
    return from_yaml((GRAPHS_DIR / f"{name}.graph.yaml").read_text(encoding="utf-8"))


def _roles() -> dict[str, RoleConfig]:
    return roles(product=RoleConfig(kind="proposer", model="anthropic:glm-5.2"))


def _keys(graph) -> set[tuple[str, str, str, str]]:
    return {(e.source, e.source_port, e.target, e.target_port) for e in graph.edges}


# --- the catalog spec ---------------------------------------------------------


def test_requirements_spec_metadata():
    spec = NODE_TYPES["requirements"]
    assert spec.kind == "stage"
    assert spec.role == "product"
    assert spec.canonical_stage == "requirements"
    assert spec.budget_after == "continuing"


def test_requirements_spec_ports():
    spec = NODE_TYPES["requirements"]
    table = {(p.direction, p.name): (p.payload, p.required, p.terminal) for p in spec.ports}
    assert table == {
        ("in", "trigger"): (None, False, None),
        ("in", "constitution"): ("Constitution", False, None),
        ("in", "codebase_map"): ("CodebaseMap", False, None),
        ("out", "requirements"): ("Requirements", True, None),
        ("out", "fail"): ("NodeFailure", True, "failed"),
    }


def test_requirements_has_no_reject_port():
    """Partial freeze never rejects (FR-112's ruling, re-applied): no reject out."""
    assert find_port(NODE_TYPES["requirements"], "reject", "out") is None


def test_clarify_takes_an_optional_requirements_in_port():
    port = find_port(NODE_TYPES["clarify"], "requirements", "in")
    assert port is not None
    assert (port.payload, port.required, port.multiplicity) == ("Requirements", False, "one")


def test_requirements_payload_is_registered_and_resolves():
    assert PAYLOAD_TYPES["Requirements"] == "sdlc.stages.requirements.models:Requirements"

    from sdlc.graph.node_types import _resolve_payload

    assert _resolve_payload("Requirements") is None


# --- the namespace pin ----------------------------------------------------------


def test_the_type_string_and_clarifys_out_port_named_requirements_are_distinct():
    """Two namespaces share the word: the node TYPE "requirements" whose
    out-port emits Requirements, and clarify's out-PORT "requirements" that
    emits ClarifiedRequirements. Both exist; neither shadows the other."""
    clarify_out = find_port(NODE_TYPES["clarify"], "requirements", "out")
    assert clarify_out is not None
    assert clarify_out.payload == "ClarifiedRequirements"

    own_out = find_port(NODE_TYPES["requirements"], "requirements", "out")
    assert own_out is not None
    assert own_out.payload == "Requirements"


def test_a_port_identity_is_its_direction_and_name():
    """FR-113 ruling: clarify's in-port may echo its out-port's name
    (`requirements` in beside `requirements` out) -- find_port, the topology
    and the duplicate check all key a port by (direction, name), so the
    shared name is legal and the shipped registry stays healthy."""
    assert check_node_types() == []


# --- the graphs ---------------------------------------------------------------


def test_default_graph_bytes_are_pinned():
    digest = hashlib.sha256((GRAPHS_DIR / "default.graph.yaml").read_bytes()).hexdigest()
    assert digest == DEFAULT_GRAPH_SHA


@pytest.mark.parametrize("name", GRAPH_NAMES)
def test_every_graph_yaml_validates(name):
    report = validate(_graph(name), roles=_roles())
    assert report.problems == ()
    assert report.topology is not None


def test_requirements_graph_is_default_plus_requirements():
    """Exactly default's nodes and edges plus one node and the three edges:
    nothing else about the default topology may drift."""
    base = _graph("default")
    graph = _graph("default-requirements")
    assert {n.id for n in graph.nodes} == {n.id for n in base.nodes} | {"requirements"}
    assert {n.type for n in graph.nodes if n.id == "requirements"} == {"requirements"}
    assert _keys(graph) == _keys(base) | REQUIREMENTS_EDGES


def test_requirements_graph_node_types_match_default():
    """Every node the two graphs share keeps default's type (ids alone lie)."""
    base = {n.id: n.type for n in _graph("default").nodes}
    graph = {n.id: n.type for n in _graph("default-requirements").nodes}
    for node_id, type_ in base.items():
        assert graph[node_id] == type_


def test_requirements_edges_present():
    assert REQUIREMENTS_EDGES <= _keys(_graph("default-requirements"))
