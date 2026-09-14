"""GraphRouter -- the pure control-flow core of pipeline-as-data (E-73, FR-1202).

Spec: docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md
§4, §6.

A reducer: `advance(state, event) -> Step`. No Temporal, no I/O, no clock, no
async. The router never inspects payloads; `payload_ref` is opaque. It runs
only over a `Topology`, which only sdlc.graph.validate produces (spec U7).

Semantics in one breath (spec §6): an activation emits on exactly one
out-port; forward edges deliver a token into a per-edge SLOT; a back edge
(one carrying `max_traversals`) counts a traversal, invalidates REGION(target)
-- clearing every slot whose producer lies in it, cancelling live activations
in it, resetting its nodes -- and only then delivers (5b before 5c). Slots are
never cleared by activation; node status stops a second activation per
generation. Rounds and counters never reset (spec U5).

Module-level imports stay within stdlib, pydantic, sdlc.core.models and
sdlc.graph.topology (spec §4; pinned by tests/graph/test_graph_purity.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from ..core.models import gate_key
from .topology import PortWiring, Topology

Outcome = Literal["running", "completed", "rejected", "escalated"]
Unavailable = Literal["exhausted", "target_dead"]
DropReason = Literal["stale", "duplicate", "post_terminal"]
NodeStatus = Literal["pending", "running", "done", "dead"]

_FROZEN = ConfigDict(frozen=True, extra="forbid")
_TERMINAL: tuple[Outcome, ...] = ("rejected", "escalated")


class RouterError(Exception):
    """An interpreter bug -- never an async-delivery race (spec §4, skeptic F3)."""


def _sorted_dict(value: dict[str, Any]) -> dict[str, Any]:
    return dict(sorted(value.items()))


def _node_of(activation_id: str) -> str:
    return activation_id.rpartition("#")[0]


class NodeState(BaseModel):
    model_config = _FROZEN

    round: int = 0  # monotonic activation count (spec D1)
    status: NodeStatus = "pending"
    taken_port: str | None = None


class Token(BaseModel):
    model_config = _FROZEN

    payload_ref: str
    producer: str  # activation id


class LiveActivation(BaseModel):
    """An issued, unfinished activation and its issue-time snapshot of
    unavailable ports -- the contract its emission is judged by (spec §6.5)."""

    model_config = _FROZEN

    activation_id: str
    node_id: str
    unavailable_ports: dict[str, Unavailable]

    _sort = field_validator("unavailable_ports")(_sorted_dict)


class Emission(BaseModel):
    model_config = _FROZEN

    activation_id: str
    port: str
    payload_ref: str


class Dropped(BaseModel):
    model_config = _FROZEN

    activation_id: str
    port: str
    reason: DropReason


class RouterState(BaseModel):
    """Frozen, JSON-serialisable, no timestamps, no set types (spec §4)."""

    model_config = _FROZEN

    nodes: dict[str, NodeState]
    slots: dict[str, Token] = {}  # edge id -> token (occupied slots only)
    traversals: dict[str, int] = {}  # back edge id -> count
    live: tuple[LiveActivation, ...] = ()
    retired: tuple[str, ...] = ()
    emissions: tuple[Emission, ...] = ()  # applied emissions, sorted by activation id
    dropped: tuple[Dropped, ...] = ()  # sorted audit of dropped emissions
    outcome: Outcome = "running"
    reason: str | None = None

    _sort_maps = field_validator("nodes", "slots", "traversals")(_sorted_dict)

    @field_validator("live")
    @classmethod
    def _sort_live(cls, value: tuple[LiveActivation, ...]) -> tuple[LiveActivation, ...]:
        return tuple(sorted(value, key=lambda a: a.activation_id))

    @field_validator("emissions")
    @classmethod
    def _sort_emissions(cls, value: tuple[Emission, ...]) -> tuple[Emission, ...]:
        # A lookup table, not a history: sorted so that forward emissions
        # applied in either order yield equal states (spec §6.7 T2).
        return tuple(sorted(value, key=lambda e: e.activation_id))

    @field_validator("dropped")
    @classmethod
    def _sort_dropped(cls, value: tuple[Dropped, ...]) -> tuple[Dropped, ...]:
        # Sorted like every other collection (plan skeptic P1): late emissions
        # arriving in either order leave equal states.
        return tuple(sorted(value, key=lambda d: (d.activation_id, d.port, d.reason)))

    @field_validator("retired")
    @classmethod
    def _sort_retired(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(value)))


class Emitted(BaseModel):
    """A handler's single emission. `kind` makes room for E72-OQ-4's
    `Failed` in a discriminated union without breaking this one."""

    model_config = _FROZEN

    kind: Literal["emitted"] = "emitted"
    activation_id: str
    port: str
    payload_ref: str


class Activation(BaseModel):
    model_config = _FROZEN

    activation_id: str  # gate_key(node_id, round)
    node_id: str
    round: int
    inputs: dict[str, str | tuple[str, ...]]  # in-port -> payload ref(s)
    unavailable_ports: dict[str, Unavailable]

    _sort = field_validator("inputs", "unavailable_ports")(_sorted_dict)


class Step(BaseModel):
    model_config = _FROZEN

    state: RouterState
    activations: tuple[Activation, ...]  # sorted by node id
    cancelled: tuple[str, ...]  # activation ids, sorted
    outcome: Outcome
    reason: str | None


@dataclass
class _Work:
    """Mutable scratch copy of a RouterState for one advance()."""

    nodes: dict[str, NodeState]
    slots: dict[str, Token]
    traversals: dict[str, int]
    live: dict[str, LiveActivation]
    retired: set[str]
    emissions: list[Emission]
    dropped: list[Dropped]
    outcome: Outcome
    reason: str | None

    @classmethod
    def of(cls, state: RouterState) -> _Work:
        return cls(
            nodes=dict(state.nodes),
            slots=dict(state.slots),
            traversals=dict(state.traversals),
            live={a.activation_id: a for a in state.live},
            retired=set(state.retired),
            emissions=list(state.emissions),
            dropped=list(state.dropped),
            outcome=state.outcome,
            reason=state.reason,
        )

    def freeze(self) -> RouterState:
        return RouterState(
            nodes=self.nodes,
            slots=self.slots,
            traversals=self.traversals,
            live=tuple(self.live.values()),
            retired=tuple(self.retired),
            emissions=tuple(self.emissions),
            dropped=tuple(self.dropped),
            outcome=self.outcome,
            reason=self.reason,
        )


class GraphRouter:
    def __init__(self, topology: Topology) -> None:
        self._t = topology

    @property
    def topology(self) -> Topology:
        return self._t

    # ---- public reducer ---------------------------------------------------

    def start(self) -> Step:
        """Issue `entry#1` (spec §6.1)."""
        state = RouterState(nodes={n: NodeState() for n in self._t.node_ids})
        return self._settle(_Work.of(state), cancelled=[])

    def advance(self, state: RouterState, event: Emitted) -> Step:
        """Apply one emission (spec §6.2)."""
        if not isinstance(event, Emitted):
            raise RouterError(f"unsupported event {type(event).__name__}")
        w = _Work.of(state)
        node_id = self._issued_node(w, event.activation_id)
        if event.port not in self._t.out_ports[node_id]:
            raise RouterError(
                f"{event.activation_id}: {event.port!r} is not an out-port of {node_id!r}"
            )

        # 1. activation check
        live = w.live.get(event.activation_id)
        if live is None:
            return self._not_live(w, event)

        # 2. unavailable port (issue-time snapshot): ESCALATED, emission not applied
        why = live.unavailable_ports.get(event.port)
        if why is not None:
            return self._terminate(
                w, "escalated", f"{node_id}.{event.port}: {why}", emitter=event.activation_id
            )

        # 3. done
        del w.live[event.activation_id]
        w.emissions.append(
            Emission(
                activation_id=event.activation_id, port=event.port, payload_ref=event.payload_ref
            )
        )
        w.nodes[node_id] = NodeState(
            round=w.nodes[node_id].round, status="done", taken_port=event.port
        )
        token = Token(payload_ref=event.payload_ref, producer=event.activation_id)
        edges = self._t.out_ports[node_id][event.port]

        # 4. no edges: a gate's unconnected reject ends the run; anything else is a sink
        if not edges:
            if event.port == "reject" and node_id in self._t.gate_nodes:
                return self._terminate(w, "rejected", f"{node_id}.reject", emitter=None)
            return self._settle(w, cancelled=[])

        # 5. back edge: the port carries exactly this edge (validate T4)
        if edges[0] in self._t.bounds:
            cancelled = self._traverse_back(w, edges[0], token)
            return self._settle(w, cancelled=cancelled)

        # 6. forward edges
        for eid in edges:
            if eid in w.slots:
                return self._terminate(
                    w,
                    "escalated",
                    f"router_invariant: delivery into occupied slot {eid}",
                    emitter=None,
                )
            w.slots[eid] = token
        return self._settle(w, cancelled=[])

    # ---- step 1: ids that are not live --------------------------------------

    def _issued_node(self, w: _Work, activation_id: str) -> str:
        node_id, sep, k = activation_id.rpartition("#")
        issued = (
            sep == "#"
            and node_id in w.nodes
            and k.isdigit()
            and 1 <= int(k) <= w.nodes[node_id].round
        )
        if not issued:
            raise RouterError(f"{activation_id!r} was never issued")
        return node_id

    def _not_live(self, w: _Work, event: Emitted) -> Step:
        aid = event.activation_id
        if aid in w.retired:
            reason: DropReason = "post_terminal" if w.outcome in _TERMINAL else "stale"
            return self._drop(w, event, reason)
        applied = next((e for e in w.emissions if e.activation_id == aid), None)
        if applied is None:
            raise RouterError(f"{aid!r} is issued but neither live, retired nor finished")
        if (applied.port, applied.payload_ref) == (event.port, event.payload_ref):
            return self._drop(w, event, "duplicate")
        raise RouterError(
            f"{aid!r} already emitted {applied.port!r}/{applied.payload_ref!r}; "
            f"got a conflicting {event.port!r}/{event.payload_ref!r}"
        )

    def _drop(self, w: _Work, event: Emitted, reason: DropReason) -> Step:
        w.dropped.append(Dropped(activation_id=event.activation_id, port=event.port, reason=reason))
        return Step(
            state=w.freeze(), activations=(), cancelled=(), outcome=w.outcome, reason=w.reason
        )

    # ---- step 5: region invalidation ----------------------------------------

    def _traverse_back(self, w: _Work, eid: str, token: Token) -> list[str]:
        w.traversals[eid] = w.traversals.get(eid, 0) + 1
        target = self._t.edges[eid][2]
        region = set(self._t.regions[target])
        for slot in [s for s, tok in w.slots.items() if _node_of(tok.producer) in region]:
            del w.slots[slot]
        cancelled = sorted(a for a, live in w.live.items() if live.node_id in region)
        for aid in cancelled:
            del w.live[aid]
            w.retired.add(aid)
        for n in region:
            w.nodes[n] = NodeState(round=w.nodes[n].round)
        w.slots[eid] = token  # 5c after 5b: a self-loop's new token survives
        return cancelled

    # ---- terminal outcomes -------------------------------------------------

    def _terminate(
        self,
        w: _Work,
        outcome: Outcome,
        reason: str,
        *,
        emitter: str | None,
        cancelled: list[str] | None = None,
    ) -> Step:
        others = sorted(a for a in w.live if a != emitter)
        w.retired.update(w.live)  # includes an escalating emitter: its emission was not applied
        w.live.clear()
        w.outcome = outcome
        w.reason = reason
        return Step(
            state=w.freeze(),
            activations=(),
            cancelled=tuple(sorted({*(cancelled or []), *others})),
            outcome=outcome,
            reason=reason,
        )

    # ---- step 7: readiness, deadness, issue ---------------------------------

    def _edge_dead(self, w: _Work, eid: str) -> bool:
        source, source_port = self._t.edges[eid][:2]
        ns = w.nodes[source]
        return ns.status == "dead" or (ns.status == "done" and ns.taken_port != source_port)

    def _port_state(self, w: _Work, wiring: PortWiring) -> Literal["filled", "dead", "empty"]:
        dead = [self._edge_dead(w, e) for e in wiring.forward_edges]
        filled = [e in w.slots for e in wiring.forward_edges]
        if all(dead):
            return "dead"
        if wiring.multiplicity == "one":
            return "filled" if any(filled) else "empty"
        resolved = all(f or d for f, d in zip(filled, dead, strict=True))
        return "filled" if resolved and any(filled) else "empty"

    def _fed_port_states(self, w: _Work, node_id: str) -> list[tuple[PortWiring, str]]:
        return [
            (wiring, self._port_state(w, wiring))
            for _, wiring in sorted(self._t.in_ports[node_id].items())
            if wiring.forward_edges
        ]

    def _is_dead(self, w: _Work, node_id: str) -> bool:
        states = self._fed_port_states(w, node_id)
        if not states:
            return False
        if any(wiring.required and s == "dead" for wiring, s in states):
            return True
        return all(s == "dead" for _, s in states)

    def _is_ready(self, w: _Work, node_id: str) -> bool:
        return all(
            s == "filled" if wiring.required else s in ("filled", "dead")
            for wiring, s in self._fed_port_states(w, node_id)
        )

    def _inputs(self, w: _Work, node_id: str) -> dict[str, str | tuple[str, ...]] | None:
        """None when a `one` port holds two tokens (spec §6.4 backstop)."""
        inputs: dict[str, str | tuple[str, ...]] = {}
        for name, wiring in sorted(self._t.in_ports[node_id].items()):
            occupied = sorted(
                e for e in (*wiring.forward_edges, *wiring.back_edges) if e in w.slots
            )
            if not occupied:
                continue
            if wiring.multiplicity == "many":
                inputs[name] = tuple(w.slots[e].payload_ref for e in occupied)
            elif len(occupied) > 1:
                return None
            else:
                inputs[name] = w.slots[occupied[0]].payload_ref
        return inputs

    def _unavailable(self, w: _Work, node_id: str) -> dict[str, Unavailable]:
        out: dict[str, Unavailable] = {}
        for port, eids in sorted(self._t.out_ports[node_id].items()):
            if len(eids) != 1 or eids[0] not in self._t.bounds:
                continue
            eid = eids[0]
            if w.traversals.get(eid, 0) >= self._t.bounds[eid]:
                out[port] = "exhausted"
            elif w.nodes[self._t.edges[eid][2]].status == "dead":
                out[port] = "target_dead"
        return out

    def _settle(self, w: _Work, cancelled: list[str]) -> Step:
        # Phase A: deadness to a fixpoint (activation never changes deadness).
        changed = True
        while changed:
            changed = False
            for n in self._t.node_ids:
                if w.nodes[n].status == "pending" and self._is_dead(w, n):
                    w.nodes[n] = NodeState(round=w.nodes[n].round, status="dead")
                    changed = True
        # Phase B: every ready node, judged against the same post-A state.
        ready: list[tuple[str, dict[str, str | tuple[str, ...]]]] = []
        for n in self._t.node_ids:
            if w.nodes[n].status == "pending" and self._is_ready(w, n):
                inputs = self._inputs(w, n)
                if inputs is None:
                    return self._terminate(
                        w,
                        "escalated",
                        f"router_invariant: {n} holds two tokens on a one port",
                        emitter=None,
                        cancelled=cancelled,
                    )
                ready.append((n, inputs))
        issued: list[Activation] = []
        for n, inputs in ready:
            unavailable = self._unavailable(w, n)
            round_ = w.nodes[n].round + 1
            aid = gate_key(n, round_)
            w.nodes[n] = NodeState(round=round_, status="running")
            w.live[aid] = LiveActivation(
                activation_id=aid, node_id=n, unavailable_ports=unavailable
            )
            issued.append(
                Activation(
                    activation_id=aid,
                    node_id=n,
                    round=round_,
                    inputs=inputs,
                    unavailable_ports=unavailable,
                )
            )
        w.outcome = "running" if w.live else "completed"
        w.reason = None
        return Step(
            state=w.freeze(),
            activations=tuple(issued),
            cancelled=tuple(sorted(cancelled)),
            outcome=w.outcome,
            reason=None,
        )
