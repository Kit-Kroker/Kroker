"""Graph run view -- raw per-run facts and their projections (E-75, FR-1204).

Spec: docs/superpowers/specs/2026-09-17-graph-queries-design.md §4.1, §5.

GraphWorkflow's `graph_view` query returns a GraphRunView: router state plus
per-activation facts the dispatcher and hosts record in memory. The
projections in this module are pure and shared by the workflow
(RunState.stage_marks) and the dashboard (graph_wire), so the two cannot
disagree. The payload store is never part of a view (E-74 D3).

ACTIVATION is the id of the activation whose handler task is running. It is
set ONLY as the first statement of GraphDispatcher's per-activation task
(pinned by tests/graph_workflow/test_store_import_pin.py): asyncio tasks
copy their context, so sub-tasks a handler spawns inherit it and nothing set
inside a task leaks out. Every workflow module imports this module under
imports_passed_through, so there is one ContextVar per process.

Module-level imports stay within stdlib, pydantic, sdlc.core.models and
sdlc.graph (pinned by tests/graph/test_graph_purity.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from ..core.models import DotState, gate_key
from .model import PipelineGraph
from .node_types import NodeTypeSpec
from .router import RouterState
from .topology import Topology

ACTIVATION: ContextVar[str | None] = ContextVar("sdlc_graph_activation", default=None)

NodeRunStatus = Literal[
    "idle", "running", "blocked", "done", "failed", "stale", "skipped", "cancelled"
]
PendingKind = Literal["gate", "clarify", "escalation"]
OutcomeState = Literal["running", "completed", "rejected", "escalated", "failed"]

_FROZEN = ConfigDict(frozen=True, extra="forbid")

_PENDING_KINDS: dict[str, PendingKind] = {
    "clarify": "clarify",
    "merge_gate": "gate",
    "stage_gate": "gate",
    "task_escalation": "escalation",
}


def pending_kind(decision_kind: str) -> PendingKind:
    """PendingDecision.kind -> wire kind. A new variant raises KeyError until mapped."""
    return _PENDING_KINDS[decision_kind]


class ActivationFacts(BaseModel):
    """What happened to one activation. `cost_usd` is the priced model-role
    spend attributed to it -- the same scope as RunState.cost_usd_total
    (spec §4.3); `priced` turns False once any attributed call was unpriced."""

    model_config = _FROZEN

    started_at: datetime
    ended_at: datetime | None = None
    cost_usd: float = 0.0
    priced: bool = True


class PendingFact(BaseModel):
    model_config = _FROZEN

    key: str  # the pending_decisions key, verbatim
    activation_id: str | None  # None: opened outside any activation
    kind: PendingKind


class UnroutedFailure(BaseModel):
    """An unrouted `fail` being re-raised (E-74 D8). The message is not
    exposed; it stays on the execution's close failure."""

    model_config = _FROZEN

    activation_id: str
    error_type: str


class GraphRunView(BaseModel):
    model_config = _FROZEN

    graph_sha: str
    state: RouterState
    activations: dict[str, ActivationFacts] = {}
    pending: tuple[PendingFact, ...] = ()
    result: str | None = None  # the run's return string; set only after retro returns
    escalated_by: str | None = None  # activation whose emission hit an unavailable port
    unrouted_failure: UnroutedFailure | None = None

    @field_validator("activations")
    @classmethod
    def _sort_activations(cls, value: dict[str, Any]) -> dict[str, Any]:
        return dict(sorted(value.items()))

    @field_validator("pending")
    @classmethod
    def _sort_pending(cls, value: tuple[PendingFact, ...]) -> tuple[PendingFact, ...]:
        return tuple(sorted(value, key=lambda p: p.key))


class RunOutcome(BaseModel):
    model_config = _FROZEN

    state: OutcomeState
    reason: str | None = None
    result: str | None = None


def latest_activation(node_id: str, state: RouterState) -> str | None:
    """The id of a node's most recent activation (router ids are gate_key(node, round))."""
    rnd = state.nodes[node_id].round
    return gate_key(node_id, rnd) if rnd > 0 else None


# ---- projections (spec §5) -----------------------------------------------------


def node_status(
    node_id: str, view: GraphRunView, topology: Topology, *, execution_closed: bool = False
) -> NodeRunStatus:
    """Spec §5.1, first match wins. `execution_closed` is passed True only by
    the dashboard (an open workflow cannot observe its own close)."""
    ns = view.state.nodes[node_id]
    if ns.status == "dead":
        return "skipped"
    if ns.status == "pending":
        return "stale" if ns.round > 0 else "idle"
    aid = latest_activation(node_id, view.state)
    if ns.status == "running":
        if aid is not None and aid == view.escalated_by:
            return "failed"
        if view.state.outcome != "running" or execution_closed:
            return "cancelled"
        if any(p.activation_id == aid for p in view.pending):
            return "blocked"
        return "running"
    port = ns.taken_port or ""
    if port == "fail" or topology.terminal_ports.get(node_id, {}).get(port) == "failed":
        return "failed"
    return "done"


def node_cost(node_id: str, view: GraphRunView, spec: NodeTypeSpec | None) -> float | None:
    """Spec §4.3: null for role-less types, never-run nodes and unpriced activations."""
    if spec is None or spec.role is None:
        return None
    aid = latest_activation(node_id, view.state)
    facts = view.activations.get(aid) if aid is not None else None
    if facts is None or not facts.priced:
        return None
    return facts.cost_usd


def run_outcome(
    view: GraphRunView | None, *, execution_closed: bool, close_status: str | None = None
) -> RunOutcome:
    """Spec §5.2. `close_status` is the lower-case execution status name."""
    if view is None:
        if execution_closed:
            return RunOutcome(state="failed", reason=f"not_started:{close_status}")
        return RunOutcome(state="running")
    if view.unrouted_failure is not None:
        node = view.unrouted_failure.activation_id.rpartition("#")[0]
        return RunOutcome(state="failed", reason=f"{node}.fail: {view.unrouted_failure.error_type}")
    st = view.state
    if st.outcome == "running":
        if execution_closed:
            return RunOutcome(state="failed", reason=f"interrupted:{close_status}")
        return RunOutcome(state="running")
    return RunOutcome(state=st.outcome, reason=st.reason, result=view.result)


_DOT: dict[str, DotState] = {
    "idle": "pending",
    "stale": "pending",
    "running": "active",
    "blocked": "blocked",
    "done": "done",
    "failed": "failed",
    "cancelled": "failed",
    "skipped": "skipped",
}
_RANK: dict[str, int] = {"pending": 0, "done": 1, "active": 2, "blocked": 3, "failed": 4}


def stage_marks(
    view: GraphRunView,
    topology: Topology,
    graph: PipelineGraph,
    registry: Mapping[str, NodeTypeSpec],
    *,
    execution_closed: bool = False,
) -> dict[str, DotState]:
    """Spec §5.3: per canonical stage, failed > blocked > active > done >
    pending; skipped only when every contributing node is skipped."""
    by_stage: dict[str, list[DotState]] = {}
    for n in graph.nodes:  # sorted by PipelineGraph's validator
        spec = registry.get(n.type)
        if spec is None or spec.canonical_stage is None:
            continue
        status = node_status(n.id, view, topology, execution_closed=execution_closed)
        by_stage.setdefault(spec.canonical_stage, []).append(_DOT[status])
    out: dict[str, DotState] = {}
    for name in sorted(by_stage):
        dots = [d for d in by_stage[name] if d != "skipped"]
        out[name] = max(dots, key=_RANK.__getitem__) if dots else "skipped"
    return out


def close_marks(marks: Mapping[str, DotState]) -> dict[str, DotState]:
    """Marks computed while open, adjusted for a closed execution: a live
    (active/blocked) stage is where the run stopped."""
    return {k: ("failed" if v in ("active", "blocked") else v) for k, v in sorted(marks.items())}
