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
from tests.graph.fixtures.registries import edge, graph, node, roles


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


# ---- scenario graphs over GENERIC (spec §8 router tables and property tier) ----


def nested_loops_graph() -> PipelineGraph:
    """a -> ga (revise -> a); a -> r -> gr (revise -> r): REGION(a) contains
    the inner loop, REGION(r) does not contain ga."""
    return graph(
        [
            node("start", "start"),
            node("a", "work"),
            node("ga", "gate.art"),
            node("r", "refine"),
            node("gr", "gate.art"),
        ],
        [
            edge("start.ok", "a.trigger"),
            edge("a.out", "ga.artifact"),
            edge("a.out", "r.art"),
            edge("ga.revise", "a.guidance", bound=2),
            edge("r.out", "gr.artifact"),
            edge("gr.revise", "r.guidance", bound=2),
        ],
    )


def disjoint_loops_graph() -> PipelineGraph:
    """Two independent revise loops whose approvals meet at an optional join."""
    return graph(
        [
            node("start", "start"),
            node("a", "work"),
            node("ga", "gate.art"),
            node("b", "work"),
            node("gb", "gate.art"),
            node("j", "opt2"),
        ],
        [
            edge("start.ok", "a.trigger"),
            edge("start.ok", "b.trigger"),
            edge("a.out", "ga.artifact"),
            edge("b.out", "gb.artifact"),
            edge("ga.revise", "a.guidance", bound=1),
            edge("gb.revise", "b.guidance", bound=1),
            edge("ga.approve", "j.a"),
            edge("gb.approve", "j.b"),
        ],
    )


def self_loop_graph() -> PipelineGraph:
    """A bounded self-loop: REGION(r) = {r}."""
    return graph(
        [node("start", "start"), node("r", "retry")],
        [edge("start.ok", "r.trigger"), edge("r.redo", "r.again", bound=2)],
    )


def collect_graph() -> PipelineGraph:
    """Static fan-out to fast, slow and a brancher, collected by a many port."""
    return graph(
        [
            node("start", "start"),
            node("fast", "work"),
            node("slow", "work"),
            node("br", "brancher"),
            node("c", "collect"),
        ],
        [
            edge("start.ok", "fast.trigger"),
            edge("start.ok", "slow.trigger"),
            edge("start.ok", "br.trigger"),
            edge("fast.out", "c.items"),
            edge("slow.out", "c.items"),
            edge("br.left", "c.items"),
        ],
    )


def running_target_graph(*, dead_target_variant: bool = False) -> PipelineGraph:
    """Spec §6.7 T1 counterexample: u can become ready while v runs. The
    variant makes v wait on y behind gate g1, so v can die after u is issued
    (advisor Q3 script B, spec §6.5)."""
    nodes = [
        node("e", "start"),
        node("a", "work"),
        node("g0", "gate.art"),
        node("q", "join"),
        node("z", "work"),
        node("u", "fixer"),
    ]
    edges = [
        edge("e.ok", "a.trigger"),
        edge("e.ok", "u.trigger"),
        edge("a.out", "g0.artifact"),
        edge("g0.approve", "q.req"),
        edge("g0.reject", "z.trigger"),
        edge("v.out", "q.opt"),
        edge("q.out", "u.opt"),
        edge("u.fix", "v.guidance", bound=2),
    ]
    if not dead_target_variant:
        nodes.append(node("v", "work"))
        edges.append(edge("e.ok", "v.trigger"))
    else:  # V waits on Y, Y on gate G1 (advisor Q3 script B)
        nodes += [node("v", "refine"), node("b", "work"), node("g1", "gate.art")]
        nodes += [node("y", "refine"), node("z2", "work")]
        edges += [
            edge("e.ok", "b.trigger"),
            edge("b.out", "g1.artifact"),
            edge("g1.approve", "y.art"),
            edge("g1.reject", "z2.trigger"),
            edge("y.out", "v.art"),
        ]
    return graph(nodes, edges)
