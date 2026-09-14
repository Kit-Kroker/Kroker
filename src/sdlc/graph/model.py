"""The stored pipeline graph (E-72, FR-1201).

Spec: docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md.

Parsing is SHAPE-ONLY (spec D5): field types, id/type regexes, forbidden
extra keys, the schema version, and unknown keys under `role`/`gate`. Every
referential or legality check -- unique ids, dangling edges, unknown types,
port compatibility -- belongs to E-73's validate.py, so the canvas can load a
broken draft to show its errors.

Module-level imports stay within stdlib, pydantic and sdlc.core.models
(spec §4; pinned by tests/graph/test_graph_purity.py).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..core.models import GateConfig, RoleConfig

# Node ids become gate names, gate_key "name#round" and CLI args (spec §5),
# so '#', ':' and '.' are excluded by shape. Port names share the pattern.
ID_PATTERN = r"^[a-z][a-z0-9_]*$"
# Node TYPE names may carry one dot: "architect", "gate.plan".
TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$"

_STORED = ConfigDict(frozen=True, extra="forbid")

# Canvas cosmetics: excluded from identity (FR-1201), kept in storage.
_NODE_COSMETIC: frozenset[str] = frozenset({"position", "label"})
_EDGE_COSMETIC: frozenset[str] = frozenset({"label"})


def _dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _element_json(element: BaseModel, exclude: frozenset[str]) -> str:
    return _dumps(element.model_dump(mode="json", exclude_defaults=True, exclude=set(exclude)))


class NodePosition(BaseModel):
    """Canvas coordinates. Cosmetic: never part of content_sha()."""

    model_config = _STORED

    x: float
    y: float


class NodePort(BaseModel):
    """A port declared by a node TYPE in the registry (spec §6.1).

    Authored in code and never stored in a graph, so it can gain fields
    without a graph schema_version bump.
    """

    model_config = _STORED

    name: str = Field(pattern=ID_PATTERN)
    direction: Literal["in", "out"]
    payload: str | None  # a PAYLOAD_TYPES key; None = signal port
    required: bool = True  # meaningful on in-ports only
    multiplicity: Literal["one", "many"] = "one"  # "many" = collect; in-ports only

    @model_validator(mode="after")
    def _out_ports_are_plain(self) -> NodePort:
        if self.direction == "out" and (self.multiplicity != "one" or not self.required):
            raise ValueError(
                f"out-port {self.name!r} must be required with multiplicity 'one' "
                f"(optional and collect apply to in-ports only)"
            )
        return self


class GraphNode(BaseModel):
    """One node. `role`/`gate` carry the core models verbatim (spec D6/D7):
    a PipelineConfig.roles / PipelineConfig.gates ENTRY's semantics, resolved
    by E-74 -- nothing here interprets them."""

    model_config = _STORED

    id: str = Field(pattern=ID_PATTERN)
    type: str = Field(pattern=TYPE_PATTERN)
    role: RoleConfig | None = None
    gate: GateConfig | None = None
    position: NodePosition | None = None  # cosmetic
    label: str | None = None  # cosmetic

    @model_validator(mode="before")
    @classmethod
    def _reject_unknown_role_gate_keys(cls, data: Any) -> Any:
        """RoleConfig/GateConfig use pydantic's default extra='ignore', so a
        typo like `modle:` would be dropped silently -- and once dropped,
        validate.py can never see it. Checked here, at the model, so YAML and
        E-75 JSON are covered alike, without touching core/models.py."""
        if not isinstance(data, dict):
            return data
        for field, model in (("role", RoleConfig), ("gate", GateConfig)):
            value = data.get(field)
            if isinstance(value, dict):
                unknown = sorted(str(k) for k in set(value) - set(model.model_fields))
                if unknown:
                    raise ValueError(f"unknown {field} key(s): {', '.join(unknown)}")
        return data


class GraphEdge(BaseModel):
    """A directed connection. Identity is the endpoint 4-tuple (no id field);
    duplicates are validate.py's to reject."""

    model_config = _STORED

    source: str = Field(pattern=ID_PATTERN)
    source_port: str = Field(pattern=ID_PATTERN)
    target: str = Field(pattern=ID_PATTERN)
    target_port: str = Field(pattern=ID_PATTERN)
    # Stored data only: which cycles need a bound and what exhaustion does
    # are E-73's. None = this edge itself is unbounded.
    max_traversals: int | None = Field(default=None, ge=1)
    label: str | None = None  # cosmetic


class PipelineGraph(BaseModel):
    """The whole graph. Nodes and edges are normalized into a total order on
    construction, so author order never affects equality, YAML or sha."""

    model_config = _STORED

    schema_version: Literal[1]
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _version_is_an_int(cls, v: Any) -> Any:
        # A lax Literal[1] accepts `true` and `1.0` (and Field(strict=True)
        # cannot apply to a literal schema); type() because bool is an int.
        if type(v) is not int:
            raise ValueError(f"schema_version must be an integer, got {type(v).__name__}")
        return v

    @field_validator("nodes")
    @classmethod
    def _sort_nodes(cls, nodes: list[GraphNode]) -> list[GraphNode]:
        # The cosmetic-stripped tiebreak comes first so that even an illegal
        # duplicate-id draft never hashes differently by layout.
        return sorted(
            nodes,
            key=lambda n: (
                n.id,
                _element_json(n, _NODE_COSMETIC),
                _element_json(n, frozenset()),
            ),
        )

    @field_validator("edges")
    @classmethod
    def _sort_edges(cls, edges: list[GraphEdge]) -> list[GraphEdge]:
        return sorted(
            edges,
            key=lambda e: (
                e.source,
                e.source_port,
                e.target,
                e.target_port,
                _element_json(e, _EDGE_COSMETIC),
                _element_json(e, frozenset()),
            ),
        )
