"""The graph node handler contract (E-74 spec §5.2, §5.3, §7.2; D2-D5).

A handler is `async (NodeContext, Activation, PipelineConfig) -> NodeResult`
(user ruling U10). Inputs arrive only through the Activation's payload refs;
run facts, stage services and the payload store ride NodeContext. Handlers
never mint refs and never touch router state (the dispatcher owns both).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from pydantic import BaseModel

    from ...core.models import GateDecision, IdeaBrief, PipelineConfig
    from ...graph.model import GraphNode, PipelineGraph
    from ...graph.node_types import NodeTypeSpec
    from ...graph.router import Activation
    from ...graph.topology import Topology
    from ...vcs import IntegrationHandle
    from ..models import SeededWork


@dataclass(frozen=True)
class StoredPayload:
    model: BaseModel | None
    producer: str  # activation id
    author_model: str | None = None
    meta: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class NodeResult:
    port: str
    payload: BaseModel | None = None
    author_model: str | None = None
    meta: Mapping[str, str] = field(default_factory=dict)
    result: str | None = None  # only on a terminal port or a sink (§5.6)
    finalize: Callable[[], Awaitable[None]] | None = None  # runs after the budget boundary


class RunFacts:
    """Run context. Written once by the entry node (integration, base_sha);
    never a port (E-72 D8)."""

    def __init__(
        self,
        *,
        idea: IdeaBrief,
        repo_path: str,
        run_id: str,
        seeded: SeededWork | None,
        memory_watermark: str | None,
    ) -> None:
        self._idea = idea
        self._repo_path = repo_path
        self._run_id = run_id
        self._seeded = seeded
        self._memory_watermark = memory_watermark
        self._integration: IntegrationHandle | None = None

    idea = property(lambda self: self._idea)
    repo_path = property(lambda self: self._repo_path)
    run_id = property(lambda self: self._run_id)
    seeded = property(lambda self: self._seeded)
    memory_watermark = property(lambda self: self._memory_watermark)

    @property
    def integration(self) -> IntegrationHandle | None:
        return self._integration

    @property
    def base_sha(self) -> str | None:
        return self._integration.head_sha if self._integration is not None else None

    def set_integration(self, handle: IntegrationHandle) -> None:
        if self._integration is not None:
            raise RuntimeError("RunFacts.integration is write-once")
        self._integration = handle


@dataclass(frozen=True)
class NodeContext:
    ctx: Any  # the StageContext services (core/context.py)
    host: Any  # the workflow instance: observability writes + TaskHost capabilities (D5)
    facts: RunFacts
    node: GraphNode
    spec: NodeTypeSpec
    topology: Topology | None
    payloads: Mapping[str, StoredPayload]
    carries: dict[str, dict[str, Any]]

    def payload(self, ref: str) -> StoredPayload:
        return self.payloads[ref]

    def carry(self, node_id: str) -> dict[str, Any]:
        """Cross-activation, per-node state; never reset by region invalidation (D4)."""
        return self.carries.setdefault(node_id, {})

    def connected(self, port: str) -> bool:
        assert self.topology is not None
        return bool(self.topology.out_ports[self.node.id].get(port))


Handler = Callable[[NodeContext, Activation, PipelineConfig], Awaitable[NodeResult]]


def input_model(nc: NodeContext, act: Activation, port: str) -> Any | None:
    ref = act.inputs.get(port)
    return nc.payload(ref).model if isinstance(ref, str) else None


def guidance_text(nc: NodeContext, act: Activation) -> str | None:
    decision = input_model(nc, act, "guidance")
    if not isinstance(decision, GateDecision):
        return None
    return (decision.guidance or decision.comments) or None  # role_host.py:261


def graph_has_research(graph: PipelineGraph) -> bool:
    return any(n.type == "research" for n in graph.nodes)


def project_cfg(
    cfg: PipelineConfig, node: GraphNode, spec: NodeTypeSpec, *, research_in_graph: bool
) -> PipelineConfig:
    """The per-activation cfg (spec §5.2): a node role fills an unoverridden
    role (U5), a node gate overlays cfg.gates[node.id], research_enabled
    follows the graph. Equal to `cfg` for every shipped graph (pinned in Task 14)."""
    roles = dict(cfg.roles)
    if node.role is not None and spec.role is not None and spec.role not in cfg.roles:
        roles[spec.role] = node.role
    gates = dict(cfg.gates)
    if node.gate is not None:
        gates[node.id] = node.gate
    return cfg.model_copy(
        update={"roles": roles, "gates": gates, "research_enabled": research_in_graph}
    )
