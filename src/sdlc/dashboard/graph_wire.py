"""Graph wire shapes for the dashboard (E-76, FR-1205).

Spec: docs/superpowers/specs/2026-09-14-graph-canvas-design.md §5-§6.

Pure projections over sdlc.graph: the models here are the HTTP contract the
canvas consumes. E-76's routes (catalog, parse, serialize) use them now;
E-75's routes use the PROVISIONAL ones as `response_model=` later, so a
route cannot drift from the fixtures `scripts/dump_graph_fixtures.py`
records from these same functions.

Nothing here decides legality (FR-1202): `connectable` is Python's
`ports_compatible` served as data, and there is deliberately no validate
stub -- a fake "no issues" is worse than none.

Module-level imports stay within stdlib, pydantic, sdlc.graph and
sdlc.core.models (pinned by tests/test_dashboard_graph_wire.py).
CANONICAL_STAGES is imported inside catalog(): benchmarks sits on the
benchmarks <-> stages import cycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sdlc.graph import (
    NODE_TYPES,
    GraphEdge,
    GraphNode,
    GraphSchemaError,
    NodeTypeSpec,
    PipelineGraph,
    from_yaml,
    ports_compatible,
    to_yaml,
)

MAX_GRAPH_BYTES = 256 * 1024

_WIRE = ConfigDict(frozen=True, extra="forbid")


# --- shared -----------------------------------------------------------------


class ShapeError(BaseModel):
    model_config = _WIRE

    loc: list[str | int]
    msg: str
    line: int | None = None
    column: int | None = None


class EdgeRef(BaseModel):
    model_config = _WIRE

    source: str
    source_port: str
    target: str
    target_port: str


# --- catalog (FINAL) -----------------------------------------------------------


class PortWire(BaseModel):
    model_config = _WIRE

    name: str
    direction: Literal["in", "out"]
    payload: str | None
    required: bool
    multiplicity: Literal["one", "many"]


class ConnectTarget(BaseModel):
    model_config = _WIRE

    type: str
    port: str


class NodeTypeWire(BaseModel):
    model_config = _WIRE

    type: str
    kind: Literal["stage", "gate"]
    role: str | None
    canonical_stage: str | None
    default_id: str
    ports: list[PortWire]
    connectable: dict[str, list[ConnectTarget]]


class Capabilities(BaseModel):
    """Server-declared graph capabilities (spec D9). E-76 serves all False;
    E-73 flips `validate`, E-75/E-77 the rest. The wire key `validate` is an
    alias: a field of that name would shadow BaseModel.validate."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", serialize_by_alias=True, validate_by_name=True
    )

    can_validate: bool = Field(default=False, alias="validate")
    save: bool = False
    load: bool = False
    run_graph: bool = False


class CatalogWire(BaseModel):
    model_config = _WIRE

    node_types: list[NodeTypeWire]
    canonical_stages: list[str]
    schemas: dict[str, dict[str, Any]]
    capabilities: Capabilities
    max_graph_bytes: int


def default_id(type_: str) -> str:
    """A node id for a fresh node of `type_`: TYPE_PATTERN with its one dot
    turned into '_' is always an ID_PATTERN (pinned by a test)."""
    return type_.replace(".", "_")


def _connectable(
    spec: NodeTypeSpec, registry: Mapping[str, NodeTypeSpec]
) -> dict[str, list[ConnectTarget]]:
    out: dict[str, list[ConnectTarget]] = {}
    for port in spec.ports:
        if port.direction != "out":
            continue
        out[port.name] = [
            ConnectTarget(type=other_key, port=in_port.name)
            for other_key in sorted(registry)
            for in_port in registry[other_key].ports
            if ports_compatible(port, in_port)
        ]
    return out


def catalog(registry: Mapping[str, NodeTypeSpec] = NODE_TYPES) -> CatalogWire:
    from sdlc.benchmarks.heatmap import CANONICAL_STAGES

    node_types = [
        NodeTypeWire(
            type=spec.type,
            kind=spec.kind,
            role=spec.role,
            canonical_stage=spec.canonical_stage,
            default_id=default_id(spec.type),
            ports=[PortWire(**p.model_dump()) for p in spec.ports],
            connectable=_connectable(spec, registry),
        )
        for spec in (registry[key] for key in sorted(registry))
    ]
    return CatalogWire(
        node_types=node_types,
        canonical_stages=list(CANONICAL_STAGES),
        schemas={
            "GraphNode": GraphNode.model_json_schema(),
            "GraphEdge": GraphEdge.model_json_schema(),
        },
        capabilities=Capabilities(),
        max_graph_bytes=MAX_GRAPH_BYTES,
    )


# --- parse / serialize (FINAL) -------------------------------------------------


class ParseOk(BaseModel):
    model_config = _WIRE

    ok: Literal[True] = True
    graph: dict[str, Any]
    sha: str


class ParseErr(BaseModel):
    model_config = _WIRE

    ok: Literal[False] = False
    shape_errors: list[ShapeError]


class SerializeOk(BaseModel):
    model_config = _WIRE

    ok: Literal[True] = True
    yaml: str


def _graph_json(graph: PipelineGraph) -> dict[str, Any]:
    return graph.model_dump(mode="json", exclude_defaults=True)


def _validation_errors(exc: ValidationError) -> list[ShapeError]:
    return [ShapeError(loc=list(e["loc"]), msg=e["msg"]) for e in exc.errors()]


def _schema_errors(exc: GraphSchemaError) -> list[ShapeError]:
    cause = exc.__cause__
    if isinstance(cause, ValidationError):
        return _validation_errors(cause)
    mark = getattr(cause, "problem_mark", None)
    if mark is not None:
        # PyYAML marks are 0-based; editors count from 1.
        return [ShapeError(loc=[], msg=str(exc), line=mark.line + 1, column=mark.column + 1)]
    return [ShapeError(loc=[], msg=str(exc))]


def parse_text(text: str) -> ParseOk | ParseErr:
    try:
        graph = from_yaml(text)
    except GraphSchemaError as exc:
        return ParseErr(shape_errors=_schema_errors(exc))
    return ParseOk(graph=_graph_json(graph), sha=graph.content_sha())


def parse_object(obj: Any) -> ParseOk | ParseErr:
    try:
        graph = PipelineGraph.model_validate(obj)
    except ValidationError as exc:
        return ParseErr(shape_errors=_validation_errors(exc))
    return ParseOk(graph=_graph_json(graph), sha=graph.content_sha())


def serialize(obj: Any) -> SerializeOk | ParseErr:
    try:
        graph = PipelineGraph.model_validate(obj)
    except ValidationError as exc:
        return ParseErr(shape_errors=_validation_errors(exc))
    return SerializeOk(yaml=to_yaml(graph))


# --- PROVISIONAL: validate (E-73 + E-75) ---------------------------------------


class IssueTarget(BaseModel):
    model_config = _WIRE

    kind: Literal["graph", "node", "edge", "port"]
    id: str | None = None
    edge: EdgeRef | None = None
    node: str | None = None
    port: str | None = None


class Issue(BaseModel):
    model_config = _WIRE

    code: str
    severity: Literal["error", "warning"]
    message: str
    target: IssueTarget


class ValidationWire(BaseModel):
    model_config = _WIRE

    issues: list[Issue]
    back_edges: list[EdgeRef]


# --- PROVISIONAL: save / load (E-75 + E-77) ------------------------------------


class SaveOk(BaseModel):
    model_config = _WIRE

    ok: Literal[True] = True
    sha: str
    validation: ValidationWire | None


class LoadOk(BaseModel):
    model_config = _WIRE

    ok: Literal[True] = True
    sha: str
    graph: dict[str, Any]


class LoadMissing(BaseModel):
    model_config = _WIRE

    ok: Literal[False] = False
    reason: Literal["not_found"] = "not_found"


# --- PROVISIONAL: run graph and run state (E-75 on E-74) -----------------------


class GraphResponse(BaseModel):
    model_config = _WIRE

    kind: Literal["graph"] = "graph"
    sha: str
    graph: dict[str, Any]
    back_edges: list[EdgeRef]


class NoGraph(BaseModel):
    model_config = _WIRE

    kind: Literal["no_graph"] = "no_graph"
    reason: Literal["legacy_run"] = "legacy_run"


class NodeRunState(BaseModel):
    model_config = _WIRE

    status: Literal["idle", "running", "blocked", "done", "failed", "stale"]
    round: int
    started_at: str | None
    ended_at: str | None
    cost_usd: float | None


class EdgeRunState(BaseModel):
    model_config = _WIRE

    edge: EdgeRef
    traversals: int


class PendingRef(BaseModel):
    model_config = _WIRE

    node: str
    key: str
    kind: Literal["gate", "clarify", "escalation"]


class GraphState(BaseModel):
    model_config = _WIRE

    kind: Literal["state"] = "state"
    graph_sha: str
    nodes: dict[str, NodeRunState]
    edges: list[EdgeRunState]
    current_nodes: list[str]
    pending: list[PendingRef]
    terminal: Literal["done", "failed", "escalated"] | None
