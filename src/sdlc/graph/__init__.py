"""Pipeline as data -- the graph schema and node-type registry (E-72, FR-1201).

Spec: docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md.
Nothing outside this package imports it until E-74.
"""

from __future__ import annotations

from .io import GraphSchemaError, from_yaml, to_yaml
from .model import (
    GraphEdge,
    GraphNode,
    NodePort,
    NodePosition,
    PipelineGraph,
    canonical_json,
)
from .node_types import (
    NODE_TYPES,
    NodeTypeSpec,
    check_node_types,
    find_port,
    ports_compatible,
)
from .payloads import PAYLOAD_TYPES

__all__ = [
    "NODE_TYPES",
    "PAYLOAD_TYPES",
    "GraphEdge",
    "GraphNode",
    "GraphSchemaError",
    "NodePort",
    "NodePosition",
    "NodeTypeSpec",
    "PipelineGraph",
    "canonical_json",
    "check_node_types",
    "find_port",
    "from_yaml",
    "ports_compatible",
    "to_yaml",
]
