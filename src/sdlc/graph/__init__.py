"""Pipeline as data -- the graph schema, node-type registry, validator and
router (E-72 FR-1201, E-73 FR-1202).

Specs: docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md,
docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md.
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
from .router import (
    Activation,
    Emitted,
    GraphRouter,
    Halt,
    RouterError,
    RouterState,
    Step,
)
from .topology import Topology
from .validate import (
    RESERVED_GATE_NAMES,
    InvalidGraph,
    Problem,
    ProblemCode,
    ValidationReport,
    from_graph,
    validate,
)

__all__ = [
    "NODE_TYPES",
    "PAYLOAD_TYPES",
    "RESERVED_GATE_NAMES",
    "Activation",
    "Emitted",
    "GraphEdge",
    "GraphNode",
    "GraphRouter",
    "GraphSchemaError",
    "Halt",
    "InvalidGraph",
    "NodePort",
    "NodePosition",
    "NodeTypeSpec",
    "PipelineGraph",
    "Problem",
    "ProblemCode",
    "RouterError",
    "RouterState",
    "Step",
    "Topology",
    "ValidationReport",
    "canonical_json",
    "check_node_types",
    "find_port",
    "from_graph",
    "from_yaml",
    "ports_compatible",
    "to_yaml",
    "validate",
]
