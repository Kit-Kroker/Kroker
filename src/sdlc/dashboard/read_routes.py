"""The read-only routes (018 read-routes.md). One registration point for
every route that serves the v5 dashboard's extra reads; each is stateless,
GET-only and never writes (rule 1), and never a 500 for missing data
(rule 3). The router is mounted un-prefixed the way ``create_router``'s
other routers are; production mounts ``/api`` around everything.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .catalog_wire import ShippedGraphsWire, shipped_graphs
from .compare_wire import CompareWire, compare
from .fleet_summary import FleetSummaryWire, fleet_summary
from .run_graph import RunGraphs


def register_read_routes(
    poller: Any, *, run_graphs: RunGraphs, runs_root: str | None = None
) -> APIRouter:
    router = APIRouter()

    @router.get("/fleet/summary")
    async def read_fleet_summary() -> FleetSummaryWire:
        return await fleet_summary(poller, run_graphs)

    @router.get("/graphs/shipped")
    async def read_graphs_shipped() -> ShippedGraphsWire:
        return shipped_graphs()

    @router.get("/compare")
    async def read_compare() -> CompareWire:
        # 018 T068 (R-9): the runs root rides the env contract
        # ($SDLC_RUNS_ROOT or ./runs) unless the caller pins one.
        return compare(runs_root)

    return router
