"""GET /api/fleet/summary (018 T046; R-6, read-routes.md, data-model §2.1).

One summary row per run in ``poller.snapshot()`` — open and closed — with
the v5 Fleet columns derivable per run: the pinned graph's sha and its
SHIPPED name, the dev arm, the bounded edges' traversal counts, the
graph-state outcome and current nodes, and the gate timeout copy. Every
rule is read-only (read-routes rule 1): the summary reads through
``RunGraphs.source_readonly`` and never writes to the store.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from ..graph.run_view import run_outcome
from ..graph.topology import edge_id
from ..workflows.graph_catalog import SHIPPED, resolved_roles
from .graph_wire import EdgeRef, RunOutcomeWire
from .run_graph import GRAPH_TYPE, RunGraphs, RunSource

_log = logging.getLogger(__name__)


class ArmWire(BaseModel):
    harness: str | None = None
    model: str | None = None


class TraversalWire(BaseModel):
    edge: EdgeRef
    used: int
    max: int | None = None


class GateTimeoutWire(BaseModel):
    gate: str
    on_timeout: str


class FleetRunSummaryWire(BaseModel):
    run_id: str
    graph_sha: str | None = None  # None = legacy run (no graph)
    graph_name: str | None = None  # a SHIPPED name when the sha matches, else None
    arm: ArmWire | None = None  # None = run input unreadable
    traversals: list[TraversalWire] = Field(default_factory=list)
    outcome: RunOutcomeWire | None = None  # None for legacy
    where: list[str] = Field(default_factory=list)  # current node ids, or [] when final
    gate_timeouts: list[GateTimeoutWire] = Field(default_factory=list)


class FleetSummaryWire(BaseModel):
    runs: list[FleetRunSummaryWire] = Field(default_factory=list)
    unreadable: list[str] = Field(default_factory=list)


_SHIPPED_BY_SHA = {g.content_sha(): name for name, g in SHIPPED.items()}


def _arm(src: RunSource) -> ArmWire | None:
    if src.run_input is None:
        return None
    dev = resolved_roles(src.run_input.cfg).get("dev")
    if dev is None:
        return ArmWire()
    return ArmWire(harness=dev.harness.value if dev.harness else None, model=dev.model)


def _row(run_id: str, src: RunSource, view: Any) -> FleetRunSummaryWire:
    row = FleetRunSummaryWire(run_id=run_id, arm=_arm(src))
    if src.run_input is None:
        return row  # the null arm: a legacy run carries no graph facts
    graph = src.run_input.graph
    row.graph_sha = graph.content_sha()
    row.graph_name = _SHIPPED_BY_SHA.get(row.graph_sha)
    counts: dict[str, int] = dict(view.state.traversals) if view is not None else {}
    row.traversals = [
        TraversalWire(
            edge=EdgeRef(
                source=e.source,
                source_port=e.source_port,
                target=e.target,
                target_port=e.target_port,
            ),
            used=counts.get(edge_id(e), 0),
            max=e.max_traversals,
        )
        for e in graph.edges
        if e.max_traversals is not None
    ]
    outcome = run_outcome(view, execution_closed=src.closed, close_status=src.close_status)
    row.outcome = RunOutcomeWire(**outcome.model_dump())
    if view is not None and not src.closed:
        row.where = sorted({a.node_id for a in view.state.live})
    row.gate_timeouts = [
        GateTimeoutWire(gate=name, on_timeout=cfg.on_timeout.value)
        for name, cfg in (src.run_input.cfg.gates or {}).items()
    ]
    return row


async def fleet_summary(poller: Any, run_graphs: RunGraphs) -> FleetSummaryWire:
    snapshot = await poller.snapshot()
    ids = [r.run_id for r in snapshot.runs] + [c.run_id for c in snapshot.closed]
    runs: list[FleetRunSummaryWire] = []
    unreadable: list[str] = []
    for run_id in ids:
        try:
            src = await run_graphs.source_readonly(run_id)
            view = None
            if src.workflow_type == GRAPH_TYPE and src.run_input is not None:
                view = await run_graphs.view(src, run_id)
            runs.append(_row(run_id, src, view))
        except Exception as e:  # noqa: BLE001 -- read-routes rule 3: never a 500
            _log.warning("fleet summary: run %s unreadable: %s", run_id, e)
            unreadable.append(run_id)
    return FleetSummaryWire(runs=runs, unreadable=unreadable)
