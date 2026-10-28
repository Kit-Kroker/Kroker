"""The read-only routes (018 read-routes.md). One registration point for
every route that serves the v5 dashboard's extra reads; each is stateless,
GET-only and never writes (rule 1), and never a 500 for missing data
(rule 3). The router is mounted un-prefixed the way ``create_router``'s
other routers are; production mounts ``/api`` around everything.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .fleet_summary import FleetSummaryWire, fleet_summary
from .run_graph import RunGraphs


def register_read_routes(poller: Any, *, run_graphs: RunGraphs) -> APIRouter:
    router = APIRouter()

    @router.get("/fleet/summary")
    async def read_fleet_summary() -> FleetSummaryWire:
        return await fleet_summary(poller, run_graphs)

    return router
