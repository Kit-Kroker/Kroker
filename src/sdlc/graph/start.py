"""Client-side graph run start (E-75 spec §6.1; E-77 start-time persistence).

Every CLIENT start site (CLI, dashboard, operator) starts a GraphWorkflow
through here, so the pinned graph lands in the store at start. Children
started inside a workflow (tidy-up, benchmark) cannot do file I/O and are
backfilled from history by the dashboard (§6.2). `client` and `run` are
duck-typed: this module imports no Temporal or workflow code, so sdlc.graph
stays pure and workflow modules never reach it (pinned).

E-77 (R-8, FR-011/013/022): before the start, this writes the graph identity
+ layout, a registry snapshot and a per-run pointer. Every write is guarded:
a storage hiccup warns and the run still starts; `latest` is never written.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from .store import GraphStore, RunGraphPointer

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
    st = store if store is not None else GraphStore()
    try:
        st.put(run_input.graph)  # identity + layout (E-77), never `latest`
    except Exception:  # noqa: BLE001 -- a storage hiccup must not block a run; §6.2 backfills
        _log.warning("graph store write failed for %s", id, exc_info=True)
    registry_sha: str | None
    try:
        registry_sha = st.put_registry()  # the shipped registry snapshot
    except Exception:  # noqa: BLE001
        _log.warning("registry snapshot write failed for %s", id, exc_info=True)
        registry_sha = None
    try:
        st.put_pointer(
            RunGraphPointer(
                run_id=id,
                graph_sha=run_input.graph.content_sha(),
                layout_sha=run_input.graph.document_sha(),
                registry_sha=registry_sha,
                roles=dict(run_input.roles),
                started_at=datetime.now(UTC),
            )
        )
    except Exception:  # noqa: BLE001 -- the pointer is never fatal (FR-012)
        _log.warning("run pointer write failed for %s", id, exc_info=True)
    return await client.start_workflow(run, run_input, id=id, task_queue=task_queue)
