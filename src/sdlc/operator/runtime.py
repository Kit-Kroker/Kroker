"""Framework-free composition for operator surfaces (022 research R5).

The dashboard's interfaces/dashboard/api/main.py used to own _connect and
_start; every second consumer (the MCP bridge) would have had to import
that module, which boots the FastAPI app and mount_chat at import time.
This module is the dependency-free seam instead: a Temporal client factory,
the shared FleetPoller builder, a graph starter that names "GraphWorkflow"
as a string (never importing sdlc.worker or the workflow class, so no
3 s worker import and no registry-at-import failure), and the OperatorDeps
composer both surfaces share.

tools.py's verbs stay the behaviour; this file only wires collaborators.
"""

from __future__ import annotations

import functools
import os
from typing import Any

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from ..board.store import BoardStore
from ..dashboard.fleet import FleetPoller
from ..graph.start import start_graph_run
from ..task_queue import TASK_QUEUE
from .deps import OperatorDeps

GRAPH_WORKFLOW_NAME = "GraphWorkflow"


async def connect() -> Client:
    """The Temporal client every operator surface shares.

    pydantic_data_converter is non-negotiable: without it RunState and
    PendingDecision do not round-trip (cli.py:317).
    """
    return await Client.connect(
        os.environ.get("TEMPORAL_HOST", "localhost:7233"), data_converter=pydantic_data_converter
    )


def build_poller() -> FleetPoller:
    return FleetPoller(connect)


def build_run_input(idea: Any, cfg: Any) -> Any:
    """Delegate lazily to workflows.graph_catalog.

    graph_catalog loads temporalio and (via graph selection) the agent
    registry, so it must stay off every read path. The indirection through
    this module's globals is deliberate: tests patch runtime.build_run_input
    without touching the heavy module.
    """
    from ..workflows.graph_catalog import build_run_input as real

    return real(idea, cfg)


async def start_graph(poller: Any, idea: Any, cfg: Any, wf_id: str) -> str:
    """Start one GraphWorkflow run; `run` is passed BY NAME.

    start_graph_run's `run` parameter is duck-typed and forwarded to
    client.start_workflow, so naming the workflow avoids importing
    sdlc.workflows.graph (which constructs the registry at import time and
    fails without provider keys). Callers compose this with
    functools.partial(start_graph, poller).
    """
    client = await poller._client_or_connect()
    handle = await start_graph_run(
        client,
        GRAPH_WORKFLOW_NAME,
        build_run_input(idea, cfg),
        id=wf_id,
        task_queue=TASK_QUEUE,
    )
    return handle.id


def operator_deps(poller: Any, actor: str) -> OperatorDeps:
    """The deps shape every non-chat operator surface shares.

    board is the BoardStore CLASS, not an instance: tools._board opens and
    closes a store per call inside the worker thread it runs on.
    """
    return OperatorDeps(
        poller=poller,
        board=BoardStore,
        starter=functools.partial(start_graph, poller),
        actor=actor,
    )
