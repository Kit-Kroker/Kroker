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

from contextvars import ContextVar
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from ..core.models import gate_key
from .router import RouterState

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
