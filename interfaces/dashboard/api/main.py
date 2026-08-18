# interfaces/dashboard/api/main.py
"""uvicorn entrypoint composing both operator HTTP surfaces (E-10 D2).

    uvicorn interfaces.dashboard.api.main:app --host 127.0.0.1 --port 8500

Two routers, one process: the board serves durable cross-run state from
SQLite, the dashboard serves live run state from Temporal. They keep
separate factories -- all logic stays in sdlc.board.api and
sdlc.dashboard.api -- and are composed here so the frontend has one origin
and E-60 has one place to install identity.

Board paths are unchanged; anything already hitting /projects/* keeps
working. The dashboard mounts under /api.

Bound to localhost, unauthenticated, by design (spec D4 / OQ-11).
"""
import os

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from sdlc.board.api import create_app
from sdlc.dashboard.api import create_router
from sdlc.dashboard.fleet import FleetPoller
from sdlc.models import IdeaBrief, PipelineConfig
from sdlc.worker import TASK_QUEUE
from sdlc.workflows.feature import FeatureWorkflow

app = create_app()


async def _connect() -> Client:
    # pydantic_data_converter is non-negotiable: without it RunState and
    # PendingDecision do not round-trip (cli.py:317).
    return await Client.connect(
        os.environ.get("TEMPORAL_HOST", "localhost:7233"),
        data_converter=pydantic_data_converter)


poller = FleetPoller(_connect)


async def _start(idea: IdeaBrief, cfg: PipelineConfig, wf_id: str) -> str:
    client = await poller._client_or_connect()
    handle = await client.start_workflow(
        FeatureWorkflow.run, args=[idea, cfg, None],
        id=wf_id, task_queue=TASK_QUEUE)
    return handle.id


app.include_router(create_router(poller, starter=_start), prefix="/api")


async def _shutdown() -> None:
    await poller.aclose()


app.router.add_event_handler("shutdown", _shutdown)


__all__ = ["app"]
