"""A scripted driver for GraphRouter table tests (spec §8).

`Run` validates a graph, starts a router over its Topology, and threads the
state through each `emit`. It records every Step so tables can assert on the
sequence of issued activations, cancellations and outcomes.
"""

from __future__ import annotations

from collections.abc import Mapping

from sdlc.core.models import RoleConfig
from sdlc.graph.model import PipelineGraph
from sdlc.graph.node_types import NodeTypeSpec
from sdlc.graph.router import Activation, Emitted, GraphRouter, RouterState, Step
from sdlc.graph.validate import validate
from tests.graph.fixtures.registries import roles


class Run:
    def __init__(
        self,
        graph: PipelineGraph,
        registry: Mapping[str, NodeTypeSpec],
        role_map: Mapping[str, RoleConfig] | None = None,
    ) -> None:
        report = validate(graph, registry, roles=role_map if role_map is not None else roles())
        assert report.topology is not None, [p.message for p in report.problems]
        self.router = GraphRouter(report.topology)
        self.steps: list[Step] = [self.router.start()]

    @property
    def state(self) -> RouterState:
        return self.steps[-1].state

    @property
    def last(self) -> Step:
        return self.steps[-1]

    def emit(self, activation_id: str, port: str, ref: str | None = None) -> Step:
        event = Emitted(
            activation_id=activation_id,
            port=port,
            payload_ref=ref if ref is not None else f"{activation_id}:{port}",
        )
        step = self.router.advance(self.state, event)
        self.steps.append(step)
        return step

    def issued(self) -> list[str]:
        return [a.activation_id for s in self.steps for a in s.activations]

    def activation(self, activation_id: str) -> Activation:
        return next(
            a
            for s in reversed(self.steps)
            for a in s.activations
            if a.activation_id == activation_id
        )

    def live(self) -> list[str]:
        return [a.activation_id for a in self.state.live]
