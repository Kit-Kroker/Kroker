"""Pipeline as data -- the graph schema and node-type registry (E-72, FR-1201).

Spec: docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md.
Nothing outside this package imports it until E-74.
"""

from __future__ import annotations

from .model import GraphEdge, GraphNode, NodePort, NodePosition, PipelineGraph

__all__ = [
    "GraphEdge",
    "GraphNode",
    "NodePort",
    "NodePosition",
    "PipelineGraph",
]
