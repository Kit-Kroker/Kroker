"""Graph wire shapes for the dashboard (E-76, FR-1205).

Spec: docs/superpowers/specs/2026-09-14-graph-canvas-design.md §5-§6.

Pure projections over sdlc.graph: the models here are the HTTP contract the
canvas consumes. E-76's routes (catalog, parse, serialize) use them now;
E-75's routes use the run-graph and run-state models, FINAL since E-75
(spec 2026-09-17-graph-queries-design §7.4), so a route cannot drift from
the fixtures `scripts/dump_graph_fixtures.py` records from these same
functions.

Nothing here decides legality (FR-1202): `connectable` is Python's
`ports_compatible` served as data, and there is deliberately no validate
stub -- a fake "no issues" is worse than none.

Module-level imports stay within stdlib, pydantic, sdlc.graph and
sdlc.core.models (pinned by tests/test_dashboard_graph_wire.py).
CANONICAL_STAGES is imported inside catalog(): benchmarks sits on the
benchmarks <-> stages import cycle.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from sdlc.core.models import RoleConfig
from sdlc.graph import (
    NODE_TYPES,
    GraphEdge,
    GraphNode,
    GraphRunView,
    GraphSchemaError,
    NodeTypeSpec,
    PipelineGraph,
    Topology,
    from_yaml,
    latest_activation,
    node_cost,
    node_status,
    ports_compatible,
    run_outcome,
    to_yaml,
)
from sdlc.graph import (
    validate as _validate_graph,
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
            ports=[PortWire(**p.model_dump(exclude={"terminal"})) for p in spec.ports],
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

    @model_validator(mode="after")
    def _validate_shape(self) -> IssueTarget:
        others = (self.id, self.edge, self.node, self.port)
        if self.kind == "graph":
            if any(v is not None for v in others):
                raise ValueError("graph target must have no other fields")
        elif self.kind == "node":
            if self.id is None or any(v is not None for v in (self.edge, self.node, self.port)):
                raise ValueError("node target must have exactly id set")
        elif self.kind == "edge":
            if self.edge is None or any(v is not None for v in (self.id, self.node, self.port)):
                raise ValueError("edge target must have exactly edge set")
        elif self.kind == "port":
            if (
                self.node is None
                or self.port is None
                or any(v is not None for v in (self.id, self.edge))
            ):
                raise ValueError("port target must have exactly node and port set")
        return self


class Issue(BaseModel):
    model_config = _WIRE

    code: str
    severity: Literal["error", "warning", "not_executable"]
    message: str
    target: IssueTarget


class ValidationWire(BaseModel):
    model_config = _WIRE

    issues: list[Issue]
    back_edges: list[EdgeRef]


def _issue_target(p: Any) -> IssueTarget:
    if p.edge is not None:
        edge_ref = EdgeRef(
            source=p.edge[0],
            source_port=p.edge[1],
            target=p.edge[2],
            target_port=p.edge[3],
        )
        return IssueTarget(kind="edge", edge=edge_ref)
    if p.port is not None:
        return IssueTarget(kind="port", node=p.node, port=p.port)
    if p.node is not None:
        return IssueTarget(kind="node", id=p.node)
    return IssueTarget(kind="graph")


def validation(
    graph: PipelineGraph,
    registry: Mapping[str, NodeTypeSpec] = NODE_TYPES,
    *,
    roles: Mapping[str, RoleConfig],
) -> ValidationWire:
    report = _validate_graph(graph, registry, roles=roles)
    issues = [
        Issue(
            code=str(p.code.value if hasattr(p.code, "value") else p.code),
            severity="error",
            message=p.message,
            target=_issue_target(p),
        )
        for p in report.problems
    ]

    seen_edges: set[tuple[str, str, str, str]] = set()
    back_edges: list[EdgeRef] = []
    for e in graph.edges:
        if e.max_traversals is not None:
            key = (e.source, e.source_port, e.target, e.target_port)
            if key not in seen_edges:
                seen_edges.add(key)
                back_edges.append(
                    EdgeRef(
                        source=e.source,
                        source_port=e.source_port,
                        target=e.target,
                        target_port=e.target_port,
                    )
                )

    return ValidationWire(issues=issues, back_edges=back_edges)


def with_executable(wire: ValidationWire, problems: Iterable[Any]) -> ValidationWire:
    """E74-OQ-4: executable() problems beside validate's, with a distinct
    severity -- a legal graph this worker cannot run is not an `error`.
    `problems` are workflows.graph_catalog.ExecutableProblem (duck-typed:
    graph_wire does not import workflow code)."""
    extra = [
        Issue(
            code=p.code,
            severity="not_executable",
            message=p.message,
            target=IssueTarget(kind="node", id=p.node),
        )
        for p in problems
    ]
    return ValidationWire(issues=[*wire.issues, *extra], back_edges=wire.back_edges)


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


# --- run graph and run state (FINAL, E-75 spec §7) ------------------------------


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

    status: Literal["idle", "running", "blocked", "done", "failed", "stale", "skipped", "cancelled"]
    round: int
    started_at: str | None
    ended_at: str | None
    cost_usd: float | None


class EdgeRunState(BaseModel):
    model_config = _WIRE

    edge: EdgeRef
    traversals: int  # back edges only; absent = 0


class PendingRef(BaseModel):
    model_config = _WIRE

    node: str | None  # None: opened outside any activation
    key: str
    kind: Literal["gate", "clarify", "escalation"]


class RunOutcomeWire(BaseModel):
    model_config = _WIRE

    state: Literal["running", "completed", "rejected", "escalated", "failed"]
    reason: str | None
    result: str | None  # the run's return string (E74-OQ-1), once known


class GraphState(BaseModel):
    model_config = _WIRE

    kind: Literal["state"] = "state"
    graph_sha: str
    nodes: dict[str, NodeRunState]
    edges: list[EdgeRunState]
    current_nodes: list[str]
    pending: list[PendingRef]
    outcome: RunOutcomeWire


def _edge_ref(key: tuple[str, str, str, str]) -> EdgeRef:
    return EdgeRef(source=key[0], source_port=key[1], target=key[2], target_port=key[3])


def graph_response(graph: PipelineGraph) -> GraphResponse:
    back = sorted(
        (e.source, e.source_port, e.target, e.target_port)
        for e in graph.edges
        if e.max_traversals is not None
    )
    return GraphResponse(
        sha=graph.content_sha(),
        graph=_graph_json(graph),
        back_edges=[_edge_ref(k) for k in back],
    )


def project_graph_state(
    view: GraphRunView | None,
    graph: PipelineGraph,
    topology: Topology,
    *,
    execution_closed: bool,
    close_status: str | None = None,
    registry: Mapping[str, NodeTypeSpec] = NODE_TYPES,
) -> GraphState:
    """E-75 spec §5, §7.4. Every rule lives in sdlc.graph.run_view; this only
    shapes the wire. No field changes without a state change (E-76 §5.7)."""
    outcome = RunOutcomeWire(
        **run_outcome(
            view, execution_closed=execution_closed, close_status=close_status
        ).model_dump()
    )
    if view is None:
        idle = NodeRunState(status="idle", round=0, started_at=None, ended_at=None, cost_usd=None)
        return GraphState(
            graph_sha=graph.content_sha(),
            nodes={n.id: idle for n in graph.nodes},
            edges=[],
            current_nodes=[],
            pending=[],
            outcome=outcome,
        )
    nodes: dict[str, NodeRunState] = {}
    for n in graph.nodes:
        aid = latest_activation(n.id, view.state)
        facts = view.activations.get(aid) if aid is not None else None
        nodes[n.id] = NodeRunState(
            status=node_status(n.id, view, topology, execution_closed=execution_closed),
            round=view.state.nodes[n.id].round,
            started_at=facts.started_at.isoformat() if facts is not None else None,
            ended_at=(
                facts.ended_at.isoformat()
                if facts is not None and facts.ended_at is not None
                else None
            ),
            cost_usd=node_cost(n.id, view, registry.get(n.type)),
        )
    edges = [
        EdgeRunState(edge=_edge_ref(topology.edges[eid]), traversals=count)
        for eid, count in sorted(view.state.traversals.items())
        if count > 0
    ]
    live = [] if execution_closed else sorted({a.node_id for a in view.state.live})
    pending = (
        []
        if execution_closed
        else [
            PendingRef(
                node=p.activation_id.rpartition("#")[0] if p.activation_id else None,
                key=p.key,
                kind=p.kind,
            )
            for p in view.pending
        ]
    )
    return GraphState(
        graph_sha=view.graph_sha,
        nodes=nodes,
        edges=edges,
        current_nodes=live,
        pending=pending,
        outcome=outcome,
    )
