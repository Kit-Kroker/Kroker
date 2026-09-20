"""E-76 graph wire projections (spec §5.2-§5.4, §6.2, §10.1)."""

from __future__ import annotations

import ast
import importlib.util
import itertools
import re
from pathlib import Path

import pytest

import sdlc.dashboard.graph_wire as graph_wire
from sdlc.benchmarks.heatmap import CANONICAL_STAGES
from sdlc.core.models import GateConfig, RoleConfig
from sdlc.graph import (
    NODE_TYPES,
    NodePort,
    NodeTypeSpec,
    from_yaml,
    ports_compatible,
    to_yaml,
)
from sdlc.graph.model import ID_PATTERN

FIXTURE = Path(__file__).parent / "graph" / "fixtures" / "pre_code.graph.yaml"


def _fixture_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


# --- catalog ------------------------------------------------------------------


def test_catalog_lists_every_registered_type_sorted():
    types = [t.type for t in graph_wire.catalog().node_types]
    assert types == sorted(NODE_TYPES)


def test_connectable_is_exactly_ports_compatible_over_every_pair():
    wire = {t.type: t for t in graph_wire.catalog().node_types}
    for src_key, src in NODE_TYPES.items():
        for out_port in (p for p in src.ports if p.direction == "out"):
            expected = sorted(
                (dst_key, in_port.name)
                for dst_key, dst in NODE_TYPES.items()
                for in_port in dst.ports
                if ports_compatible(out_port, in_port)
            )
            got = sorted((c.type, c.port) for c in wire[src_key].connectable[out_port.name])
            assert got == expected, (src_key, out_port.name)


def test_connectable_follows_an_injected_registry():
    registry = {
        "a": NodeTypeSpec(
            type="a",
            kind="stage",
            role=None,
            canonical_stage=None,
            ports=(NodePort(name="out", direction="out", payload="X"),),
        ),
        "b": NodeTypeSpec(
            type="b",
            kind="stage",
            role=None,
            canonical_stage=None,
            ports=(
                NodePort(name="x", direction="in", payload="X"),
                NodePort(name="y", direction="in", payload="Y"),
            ),
        ),
    }
    (a, b) = graph_wire.catalog(registry).node_types
    assert [(c.type, c.port) for c in a.connectable["out"]] == [("b", "x")]
    assert b.connectable == {}


def test_default_id_matches_the_id_pattern_for_every_type():
    for node_type in graph_wire.catalog().node_types:
        assert re.fullmatch(ID_PATTERN, node_type.default_id), node_type.type
    assert graph_wire.default_id("gate.plan") == "gate_plan"


def test_catalog_serves_the_benchmark_canonical_stages():
    assert graph_wire.catalog().canonical_stages == CANONICAL_STAGES


def test_catalog_capabilities_are_all_true_after_canvas_run_mode():
    # E75-OQ-1 (a), landed 2026-09-20: the canvas run-mode wiring flipped
    # validate and run_graph live beside E-77's save/load. The dict equality
    # also pins the exact four-key alias set (a fifth capability, a dropped
    # one, or a can_validate spelling fails here).
    wire = graph_wire.catalog().model_dump(mode="json")["capabilities"]
    assert wire == {"validate": True, "save": True, "load": True, "run_graph": True}
    assert graph_wire.Capabilities.model_validate({"validate": True}).can_validate is True


# --- canvas run-mode wiring (E75-OQ-1, bug canvas-run-mode) -- RED contracts --


def test_catalog_capabilities_declare_canvas_run_mode_live():
    """The reported symptom: canvas RUN MODE works only on the mock provider
    because the served catalog declares run_graph/validate false, so the http
    provider refuses the E-75 run-graph routes (runGraph gates on
    can('run_graph')). E75-OQ-1 option (a) rules the flip: after the wiring
    the catalog declares all four capabilities true."""
    wire = graph_wire.catalog().model_dump(mode="json")["capabilities"]
    assert wire == {"validate": True, "save": True, "load": True, "run_graph": True}


def test_capability_defaults_flip_exactly_validate_and_run_graph():
    """The ruled backend scope is the two booleans in this module's
    Capabilities (can_validate, run_graph); save/load stay true exactly as
    E-77 landed them (R-11)."""
    caps = graph_wire.Capabilities()
    assert (caps.can_validate, caps.run_graph) == (True, True)
    assert (caps.save, caps.load) == (True, True)


def test_catalog_serves_node_and_edge_schemas_with_embedded_defs():
    schemas = graph_wire.catalog().schemas
    assert set(schemas) == {"GraphNode", "GraphEdge"}
    assert {"RoleConfig", "GateConfig"} <= set(schemas["GraphNode"]["$defs"])
    assert graph_wire.catalog().max_graph_bytes == graph_wire.MAX_GRAPH_BYTES == 256 * 1024


def test_catalog_is_order_independent():
    keys = sorted(NODE_TYPES)
    baseline = graph_wire.catalog().model_dump_json()
    for order in itertools.islice(itertools.permutations(keys), 50):
        registry = {k: NODE_TYPES[k] for k in order}
        assert graph_wire.catalog(registry).model_dump_json() == baseline


# --- schema coverage (SCHEMA_FORM-3's Python mirror) ---------------------------

_SCALARS = {"string", "number", "integer", "boolean"}


def _supported(schema: dict, defs: dict) -> bool:
    """The construct set schema_form renders natively (spec §8.3)."""
    if "$ref" in schema:
        return _supported(defs[schema["$ref"].split("/")[-1]], defs)
    if "anyOf" in schema:
        branches = schema["anyOf"]
        nulls = [b for b in branches if b.get("type") == "null"]
        rest = [b for b in branches if b.get("type") != "null"]
        return len(nulls) == 1 and len(rest) == 1 and _supported(rest[0], defs)
    kind = schema.get("type")
    if kind in _SCALARS:
        return True
    if kind == "array":
        return schema.get("items", {}).get("type") == "string"
    if kind == "object":
        return all(_supported(p, defs) for p in schema.get("properties", {}).values())
    return False


@pytest.mark.parametrize("model", [RoleConfig, GateConfig])
def test_every_role_and_gate_property_is_a_supported_construct(model):
    """Red on purpose if a pydantic upgrade or a new field emits a construct
    schema_form cannot render natively. Extend schema_form, never this set."""
    node_schema = graph_wire.catalog().schemas["GraphNode"]
    defs = node_schema["$defs"]
    for name, prop in defs[model.__name__]["properties"].items():
        assert _supported(prop, defs), (model.__name__, name, prop)


def test_every_edge_property_is_a_supported_construct():
    edge_schema = graph_wire.catalog().schemas["GraphEdge"]
    for name, prop in edge_schema["properties"].items():
        assert _supported(prop, edge_schema.get("$defs", {})), name


# --- parse / serialize ------------------------------------------------------------


def test_parse_text_ok_carries_the_graph_and_its_sha():
    result = graph_wire.parse_text(_fixture_text())
    graph = from_yaml(_fixture_text())
    assert isinstance(result, graph_wire.ParseOk)
    assert result.sha == graph.content_sha()
    assert result.graph == graph.model_dump(mode="json", exclude_defaults=True)


def test_parse_text_maps_a_model_failure_to_loc_and_msg():
    text = "schema_version: 1\nnodes:\n- id: Bad\n  type: intake\nedges: []\n"
    result = graph_wire.parse_text(text)
    assert isinstance(result, graph_wire.ParseErr)
    assert [e.loc for e in result.shape_errors] == [["nodes", 0, "id"]]
    assert result.shape_errors[0].line is None


def test_parse_text_carries_a_one_based_line_for_yaml_failures():
    result = graph_wire.parse_text("schema_version: 1\nnodes: []\nnodes: []\nedges: []\n")
    assert isinstance(result, graph_wire.ParseErr)
    (error,) = result.shape_errors
    assert error.loc == [] and "duplicate key" in error.msg
    assert (error.line, error.column) == (3, 1)


def test_parse_text_reports_version_failures_without_a_location():
    result = graph_wire.parse_text("schema_version: 2\nnodes: []\nedges: []\n")
    assert isinstance(result, graph_wire.ParseErr)
    (error,) = result.shape_errors
    assert error.loc == [] and error.line is None and "schema_version" in error.msg


def test_parse_object_round_trips_the_wire_graph():
    wire = graph_wire.parse_text(_fixture_text())
    again = graph_wire.parse_object(wire.graph)
    assert again == wire


def test_parse_object_maps_failures():
    result = graph_wire.parse_object({"schema_version": 1, "nodes": [{"id": "a"}], "edges": []})
    assert isinstance(result, graph_wire.ParseErr)
    assert [e.loc for e in result.shape_errors] == [["nodes", 0, "type"]]


def test_serialize_is_exactly_to_yaml():
    wire = graph_wire.parse_text(_fixture_text())
    result = graph_wire.serialize(wire.graph)
    assert isinstance(result, graph_wire.SerializeOk)
    assert result.yaml == to_yaml(from_yaml(_fixture_text()))


def test_serialize_refuses_a_misshapen_object():
    result = graph_wire.serialize({"schema_version": 1, "nodes": "x", "edges": []})
    assert isinstance(result, graph_wire.ParseErr)


# --- boundaries ---------------------------------------------------------------------

_ALLOWED = {"__future__", "collections", "typing", "pydantic", "sdlc.graph", "sdlc.core.models"}


def test_module_level_imports_are_pinned():
    tree = ast.parse(Path(graph_wire.__file__).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
    roots = {m if m.startswith("sdlc") else m.split(".")[0] for m in found}
    assert roots <= _ALLOWED, sorted(roots - _ALLOWED)


def test_there_is_no_validate_stub():
    assert not hasattr(graph_wire, "validate")


def test_validation_wire_is_wired_once_validate_exists():
    """Forcing test (spec §10.1): E-73 names its module sdlc.graph.validate
    (handover, spec §11). The day it lands, this goes red until graph_wire
    maps validate.py's result onto ValidationWire."""
    if importlib.util.find_spec("sdlc.graph.validate") is None:
        pytest.skip("E-73 has not landed sdlc.graph.validate")
    assert hasattr(graph_wire, "validation"), (
        "sdlc.graph.validate exists: add graph_wire's mapping onto ValidationWire "
        "and real validate fixtures (E-76 spec §5.5)"
    )
