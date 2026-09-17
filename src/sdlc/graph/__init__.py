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
from .run_view import (
    ACTIVATION,
    ActivationFacts,
    GraphRunView,
    NodeRunStatus,
    OutcomeState,
    PendingFact,
    PendingKind,
    RunOutcome,
    UnroutedFailure,
    latest_activation,
    pending_kind,
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
    "ACTIVATION",
    "NODE_TYPES",
    "PAYLOAD_TYPES",
    "RESERVED_GATE_NAMES",
    "Activation",
    "ActivationFacts",
    "Emitted",
    "GraphEdge",
    "GraphNode",
    "GraphRouter",
    "GraphRunView",
    "GraphSchemaError",
    "Halt",
    "InvalidGraph",
    "NodePort",
    "NodePosition",
    "NodeRunStatus",
    "NodeTypeSpec",
    "OutcomeState",
    "PendingFact",
    "PendingKind",
    "PipelineGraph",
    "Problem",
    "ProblemCode",
    "RouterError",
    "RouterState",
    "RunOutcome",
    "Step",
    "Topology",
    "UnroutedFailure",
    "ValidationReport",
    "canonical_json",
    "check_node_types",
    "find_port",
    "from_graph",
    "from_yaml",
    "latest_activation",
    "pending_kind",
    "ports_compatible",
    "to_yaml",
    "validate",
]
