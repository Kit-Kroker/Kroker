"""Client-side graph run start (E-75 spec §6.1).

Every CLIENT start site (CLI, dashboard, operator) starts a GraphWorkflow
through here, so the pinned graph lands in the store at start. Children
started inside a workflow (tidy-up, benchmark) cannot do file I/O and are
backfilled from history by the dashboard (§6.2). `client` and `run` are
duck-typed: this module imports no Temporal or workflow code, so sdlc.graph
stays pure and workflow modules never reach it (pinned).
"""

from __future__ import annotations

import logging
from typing import Any

from .store import GraphStore

_log = logging.getLogger(__name__)


async def start_graph_run(
    client: Any,
    run: Any,
    run_input: Any,
    *,
    id: str,
    task_queue: str,
    store: GraphStore | None = None,
) -> Any:
    try:
        (store if store is not None else GraphStore()).put(run_input.graph)
    except Exception:  # noqa: BLE001 -- a storage hiccup must not block a run; §6.2 backfills
        _log.warning("graph store write failed for %s", id, exc_info=True)
    return await client.start_workflow(run, run_input, id=id, task_queue=task_queue)
