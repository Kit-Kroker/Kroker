"""HTTP surface for the dashboard (E-10).

Lives under src/ for the reason board/api.py:5 documents: pyproject's
packages.find is rooted at src, so anything outside it is not importable by
tests. interfaces/dashboard/api/main.py is the uvicorn entrypoint and
composes this router beside the board's.

Three write routes, not five: pending.py:9 states that all four render
variants collapse to just two FR-302 signals on reply, so the HTTP surface
mirrors the domain and http.ts maps its four verbs down.

Unauthenticated by design, contained by localhost-bind (spec D4, OQ-11).
X-Actor is self-asserted -- it reaches GateDecision.reviewer, never
decided_by. E-60/FR-1004 is where that stops being acceptable.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..channels.contract import Reply, default_render
from ..channels.transport import NoMatch, resolve_key, submit
from ..cli import slug
from ..core.models import (
    GateOutcome,
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
)
from .channel import DashboardChannel
from .fleet import FleetPoller, FleetSnapshot

HEARTBEAT_S = 15.0


class AnswerBody(BaseModel):
    key: str
    text: str


class DecideBody(BaseModel):
    key: str
    outcome: GateOutcome
    text: str = ""


class StartBody(BaseModel):
    title: str
    description: str = ""
    mode: ProjectMode
    repo: str | None = None


class StartedRun(BaseModel):
    run_id: str


async def _handle(poller: FleetPoller, run_id: str):
    """The workflow handle for a run. Indirected so tests can stub it."""
    client = await poller._client_or_connect()
    return client.get_workflow_handle(run_id)


async def _default_starter(idea: IdeaBrief, cfg: PipelineConfig, wf_id: str) -> str:
    raise HTTPException(503, "no starter configured")


def create_router(poller: FleetPoller, starter: Callable | None = None) -> APIRouter:
    router = APIRouter()
    start_run = starter or _default_starter

    async def _reply(run_id: str, key: str, reply: Reply, actor: str, want: str):
        handle = await _handle(poller, run_id)
        try:
            pending = await resolve_key(handle, key)
        except NoMatch as e:
            raise HTTPException(404, e.message) from e
        # match_key drops match()'s reply-kind narrowing (the operator
        # addressed an exact key), so the route enforces the kind itself:
        # /answer is for questions, /decide for gates. Mismatch is a 404,
        # keeping the surface uniform with NoMatch.
        if default_render(pending).reply_kind != want:
            noun = "a question" if want == "text" else "a gate"
            raise HTTPException(404, f"key {key!r} is not {noun} on this run")
        # confirmed=False is informational, never an error: the dominant
        # cause is another surface winning the race, which is FR-302
        # working as designed (transport._message).
        return await submit(handle, pending, reply, channel=DashboardChannel(actor=actor))

    @router.get("/runs")
    async def list_runs():
        return (await poller.snapshot()).runs

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str):
        snap = await poller.snapshot()
        for r in snap.runs:
            if r.run_id == run_id:
                return r
        for c in snap.closed:
            if c.run_id == run_id:
                return c
        raise HTTPException(404, f"no run {run_id!r}")

    @router.get("/inbox", response_model=FleetSnapshot)
    async def get_inbox():
        return await poller.snapshot()

    @router.get("/events")
    async def events():
        async def stream():
            last: str | None = None
            loop = asyncio.get_running_loop()
            last_emit = loop.time()
            async with poller.subscribe() as q:
                while True:
                    try:
                        snap = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_S)
                    except TimeoutError:
                        # Keeps idle connections alive through proxies and
                        # makes a dead poller detectable.
                        yield ": heartbeat\n\n"
                        last_emit = loop.time()
                        continue
                    body = snap.model_dump_json()
                    payload = json.loads(body)
                    payload.pop("at", None)
                    fingerprint = json.dumps(payload, sort_keys=True)
                    if fingerprint == last:
                        # Nothing changed but the clock -- but the poller
                        # is alive, so heartbeat on emit-idle too: an
                        # unchanged fleet must still see bytes every
                        # HEARTBEAT_S or proxies drop the connection.
                        if loop.time() - last_emit >= HEARTBEAT_S:
                            yield ": heartbeat\n\n"
                            last_emit = loop.time()
                        continue
                    last = fingerprint
                    yield f"data: {body}\n\n"
                    last_emit = loop.time()

        return StreamingResponse(stream(), media_type="text/event-stream")

    @router.post("/runs/{run_id}/answer")
    async def answer(
        run_id: str,
        body: AnswerBody,
        x_actor: str = Header(default="human:unknown", alias="X-Actor"),
    ):
        return await _reply(run_id, body.key, Reply(text=body.text), x_actor, want="text")

    @router.post("/runs/{run_id}/decide")
    async def decide(
        run_id: str,
        body: DecideBody,
        x_actor: str = Header(default="human:unknown", alias="X-Actor"),
    ):
        return await _reply(
            run_id,
            body.key,
            Reply(outcome=body.outcome, text=body.text or None),
            x_actor,
            want="gate",
        )

    @router.post("/runs", response_model=StartedRun)
    async def start(body: StartBody):
        idea = IdeaBrief(
            title=body.title, description=body.description, mode=body.mode, repo_url=body.repo
        )
        wf_id = f"feature-{slug(body.title)}"
        try:
            await start_run(idea, PipelineConfig(), wf_id)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            if "already started" in str(e).lower():
                raise HTTPException(409, f"run {wf_id!r} already exists") from e
            raise HTTPException(502, str(e)) from e
        return StartedRun(run_id=wf_id)

    return router
