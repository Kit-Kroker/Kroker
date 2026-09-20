"""Where a run's graph and graph state come from (E-75 spec §6.2, §7.1-§7.2).

The graph is the run's pinned START INPUT, read from the first history event
-- never from workflow memory, and needing no worker. It is stored
content-addressed on first read (backfill), which covers children started
inside a workflow and runs started before E-75. Before E-77 records
graph_sha per run, history is also the only place outside the workflow where
a run's sha exists. Bounded by namespace retention, like every fleet query.

Closed runs are immutable: their start input and view are cached per run id
(LRU-bounded), so a closed run is queried at most once per process (D8).
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from temporalio.client import WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from ..graph import NODE_TYPES, GraphRunView, Topology, validate
from ..graph.store import GraphStore
from ..workflows.models import GraphRunInput

_log = logging.getLogger(__name__)
GRAPH_TYPE = "GraphWorkflow"


class RunNotFound(LookupError):
    pass


class RunQueryFailed(RuntimeError):
    """graph_view could not be answered (no worker, replay failure). Never
    projected as a fake idle view and never cached."""


@dataclass(frozen=True)
class RunSource:
    handle: Any
    workflow_type: str
    closed: bool
    close_status: str | None  # lower-case WorkflowExecutionStatus name when closed
    run_input: GraphRunInput | None  # None unless a GraphWorkflow
    topology: Topology | None
    # E-77 R-10: None topology = the pinned graph no longer validates against
    # the CURRENT registry (or even the pointer's snapshot); problems carries
    # why. registry is the mapping the topology was built under (the pointer's
    # snapshot when it restored projection; None = the shipped NODE_TYPES).
    registry: Any = None
    problems: tuple[str, ...] = ()


class _Lru(OrderedDict):
    def __init__(self, size: int) -> None:
        super().__init__()
        self._size = size

    def put(self, key: str, value: Any) -> None:
        self[key] = value
        self.move_to_end(key)
        while len(self) > self._size:
            self.popitem(last=False)


class RunGraphs:
    def __init__(
        self,
        client_getter: Callable[[], Awaitable[Any]],
        *,
        store: GraphStore | None = None,
        cache_size: int = 256,
    ) -> None:
        self._client = client_getter
        self._store = store if store is not None else GraphStore()
        self._inputs: _Lru = _Lru(cache_size)
        self._closed_views: _Lru = _Lru(cache_size)
        self._registries: _Lru = _Lru(cache_size)
        self._problems: _Lru = _Lru(cache_size)

    @property
    def store(self) -> GraphStore:
        """The content-addressed store backfill and the save/load routes
        share (E-77 US4)."""
        return self._store

    async def source(self, run_id: str) -> RunSource:
        client = await self._client()
        handle = client.get_workflow_handle(run_id)
        try:
            desc = await handle.describe()
        except RPCError as e:
            if e.status == RPCStatusCode.NOT_FOUND:
                raise RunNotFound(run_id) from e
            raise
        closed = desc.status is not None and desc.status != WorkflowExecutionStatus.RUNNING
        close_status = desc.status.name.lower() if closed and desc.status is not None else None
        if desc.workflow_type != GRAPH_TYPE:
            return RunSource(handle, desc.workflow_type, closed, close_status, None, None)
        run_input, topology = await self._input(client, handle, run_id)
        return RunSource(
            handle,
            desc.workflow_type,
            closed,
            close_status,
            run_input,
            topology,
            registry=self._projection_registry(run_id),
            problems=self._drift_problems(run_id) if topology is None else (),
        )

    async def _input(
        self, client: Any, handle: Any, run_id: str
    ) -> tuple[GraphRunInput, Topology | None]:
        cached = self._inputs.get(run_id)
        if cached is not None:
            return cached
        run_input: GraphRunInput | None = None
        try:
            async for event in handle.fetch_history_events():
                payloads = list(event.workflow_execution_started_event_attributes.input.payloads)
                if payloads:
                    [run_input] = await client.data_converter.decode(payloads, [GraphRunInput])
                break
        except RPCError as e:
            if e.status == RPCStatusCode.NOT_FOUND:  # retention expired between describe and read
                raise RunNotFound(run_id) from e
            raise
        if run_input is None:
            raise RunNotFound(run_id)
        report = validate(run_input.graph, NODE_TYPES, roles=run_input.roles)
        topology = report.topology
        registry: Any = None
        problems: tuple[str, ...] = ()
        if topology is None:
            # E-77 R-10/FR-022: registry drift is a degraded projection, not a
            # server error. The run's pointer may name the registry snapshot
            # the graph validated under at start.
            pointer = self._pointer(run_id)
            snapshot = (
                self._store.get_registry(pointer.registry_sha)
                if pointer is not None and pointer.registry_sha is not None
                else None
            )
            if snapshot is not None:
                snap_report = validate(run_input.graph, snapshot, roles=run_input.roles)
                if snap_report.topology is not None:
                    topology = snap_report.topology
                    registry = snapshot
            if topology is None:
                problems = tuple(p.message for p in report.problems)
        try:
            self._store.put(run_input.graph)
        except Exception:  # noqa: BLE001 -- serving never depends on the store
            _log.warning("graph store backfill failed for %s", run_id, exc_info=True)
        self._inputs.put(run_id, (run_input, topology))
        self._registries.put(run_id, registry)
        self._problems.put(run_id, problems)
        return run_input, topology

    def _pointer(self, run_id: str):
        try:
            return self._store.get_pointer(run_id)
        except Exception:  # noqa: BLE001 -- the pointer is never fatal (FR-012)
            _log.warning("run pointer read failed for %s", run_id, exc_info=True)
            return None

    def _projection_registry(self, run_id: str) -> Any:
        return self._registries.get(run_id)

    def _drift_problems(self, run_id: str) -> tuple[str, ...]:
        return self._problems.get(run_id, ())

    def pointer_exists(self, run_id: str) -> bool:
        """Whether a per-run pointer is recorded (E-77 FR-012)."""
        return self._pointer(run_id) is not None

    async def graph_from_pointer(self, run_id: str) -> Any:
        """The retention fallback (E-77 FR-012/FR-013): after history is gone,
        the per-run pointer still names the stored graph and layout. None when
        there is no usable pointer — the caller keeps today's 404."""
        pointer = self._pointer(run_id)
        if pointer is None:
            return None
        graph = self._store.get(pointer.graph_sha, layout=pointer.layout_sha)
        if graph is None:
            graph = self._store.get(pointer.graph_sha)
        return graph

    async def view(self, src: RunSource, run_id: str) -> GraphRunView | None:
        if src.closed and run_id in self._closed_views:
            return self._closed_views[run_id]
        try:
            raw = await src.handle.query("graph_view")
        except Exception as e:  # noqa: BLE001 -- surfaced as 502 by the route
            raise RunQueryFailed(f"{run_id}: graph_view query failed: {e}") from e
        view = GraphRunView.model_validate(raw) if raw is not None else None
        if src.closed:
            self._closed_views.put(run_id, view)
        return view
