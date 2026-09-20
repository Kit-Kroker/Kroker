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
import re
from collections.abc import Callable

from fastapi import APIRouter, Header, HTTPException, Request
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
from ..graph import NODE_TYPES, PipelineGraph
from ..graph.store import GraphStoreCorrupt
from ..workflows.graph_catalog import GraphStartError, executable, resolved_roles
from . import graph_wire
from .channel import DashboardChannel
from .fleet import (
    FleetCapacityExceeded,
    FleetPoller,
    FleetSnapshot,
    check_fleet_capacity,
    fleet_pending_cap,
)
from .run_graph import RunGraphs, RunNotFound, RunQueryFailed

HEARTBEAT_S = 15.0
_SHA_RE = re.compile(r"[0-9a-f]{64}")  # E-77: /graphs/{sha} path shape


class AnswerBody(BaseModel):
    key: str
    text: str


class DecideBody(BaseModel):
    key: str
    outcome: GateOutcome
    text: str = ""
    thaw_tests: bool = False  # C2, revise only


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


def create_router(
    poller: FleetPoller, starter: Callable | None = None, run_graphs: RunGraphs | None = None
) -> APIRouter:
    router = APIRouter()
    start_run = starter or _default_starter
    # Lazy: the pure graph routes' tests pass a poller that fails on any attribute access.
    graphs = (
        run_graphs if run_graphs is not None else RunGraphs(lambda: poller._client_or_connect())
    )

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
            Reply(outcome=body.outcome, text=body.text or None, thaw_tests=body.thaw_tests),
            x_actor,
            want="gate",
        )

    async def _graph_body(request: Request) -> dict:
        """The capped JSON body of a graph route (E-76 spec §5.3). Read raw
        so the cap applies before any parsing: /graphs/parse accepts
        arbitrary YAML on an unauthenticated, localhost-bound surface."""
        raw = await request.body()
        if len(raw) > graph_wire.MAX_GRAPH_BYTES:
            raise HTTPException(413, f"graph body exceeds {graph_wire.MAX_GRAPH_BYTES} bytes")
        try:
            body = json.loads(raw)
        except ValueError as e:
            raise HTTPException(422, "body is not JSON") from e
        if not isinstance(body, dict):
            raise HTTPException(422, "body must be a JSON object")
        return body

    @router.get("/graphs/catalog", response_model=graph_wire.CatalogWire)
    async def graph_catalog():
        return graph_wire.catalog()

    @router.post("/graphs/parse", response_model=graph_wire.ParseOk | graph_wire.ParseErr)
    async def graph_parse(request: Request):
        body = await _graph_body(request)
        if set(body) == {"yaml"} and isinstance(body["yaml"], str):
            return graph_wire.parse_text(body["yaml"])
        if set(body) == {"graph"}:
            return graph_wire.parse_object(body["graph"])
        raise HTTPException(422, "body must be exactly one of {yaml: string} or {graph: object}")

    @router.post("/graphs/serialize", response_model=graph_wire.SerializeOk | graph_wire.ParseErr)
    async def graph_serialize(request: Request):
        body = await _graph_body(request)
        if set(body) != {"graph"}:
            raise HTTPException(422, "body must be {graph: object}")
        return graph_wire.serialize(body["graph"])

    @router.post("/graphs/validate", response_model=graph_wire.ValidationWire)
    async def graph_validate(request: Request):
        """validate + executable (E-75 §7.3). Capability `validate` stays false
        until the canvas follow-up (spec D7)."""
        body = await _graph_body(request)
        if set(body) != {"graph"}:
            raise HTTPException(422, "body must be {graph: object}")
        parsed = graph_wire.parse_object(body["graph"])
        if isinstance(parsed, graph_wire.ParseErr):
            raise HTTPException(422, "graph does not parse; use /graphs/parse for shape errors")
        graph = PipelineGraph.model_validate(parsed.graph)
        wire = graph_wire.validation(graph, roles=resolved_roles(PipelineConfig()))
        return graph_wire.with_executable(wire, executable(graph))

    @router.post("/graphs", response_model=graph_wire.SaveOk)
    async def graph_save(request: Request):
        """E-77 US4 (contracts/http-graphs.md): save a draft. A graph that
        fails legality is still saved -- legality comes only from the single
        validator, reported in `validation` exactly as /graphs/validate."""
        body = await _graph_body(request)
        if set(body) != {"graph"}:
            raise HTTPException(422, "body must be {graph: object}")
        parsed = graph_wire.parse_object(body["graph"])
        if isinstance(parsed, graph_wire.ParseErr):
            raise HTTPException(422, "graph does not parse; use /graphs/parse for shape errors")
        graph = PipelineGraph.model_validate(parsed.graph)
        wire = graph_wire.with_executable(
            graph_wire.validation(graph, roles=resolved_roles(PipelineConfig())),
            executable(graph),
        )
        try:
            sha, layout_sha = graphs.store.save(graph)
        except Exception as e:  # noqa: BLE001 -- store I/O failure is 500, never half-visible
            raise HTTPException(500, f"graph store write failed: {e}") from e
        return graph_wire.SaveOk(sha=sha, layout_sha=layout_sha, validation=wire)

    @router.get("/graphs/{sha}", response_model=graph_wire.LoadOk | graph_wire.LoadMissing)
    async def graph_load(sha: str, layout: str | None = None):
        """E-77 US4: load by identity. `?layout=` selects one document; the
        default serves the verifying latest, else the identity file."""
        if not _SHA_RE.fullmatch(sha):
            raise HTTPException(422, "sha must be 64 lowercase hex chars")
        if layout is not None and not _SHA_RE.fullmatch(layout):
            raise HTTPException(422, "layout must be 64 lowercase hex chars")
        try:
            graph = graphs.store.get(sha, layout=layout)
        except GraphStoreCorrupt as e:
            raise HTTPException(500, str(e)) from e
        if graph is None:
            return graph_wire.LoadMissing()
        return graph_wire.load_response(sha, graph, layout_sha=graph.document_sha())

    @router.get(
        "/runs/{run_id}/graph",
        response_model=graph_wire.GraphResponse | graph_wire.NoGraph,
    )
    async def run_graph(run_id: str):
        try:
            src = await graphs.source(run_id)
        except RunNotFound:
            # E-77 FR-012/FR-013: after retention, the pointer still names the
            # stored graph; without one, today's 404 stands.
            graph = await graphs.graph_from_pointer(run_id)
            if graph is None:
                raise HTTPException(404, f"no run {run_id!r}") from None
            return graph_wire.graph_response(graph)
        if src.run_input is None:
            return graph_wire.NoGraph()
        return graph_wire.graph_response(src.run_input.graph)

    @router.get(
        "/runs/{run_id}/graph_state",
        response_model=graph_wire.GraphState
        | graph_wire.GraphStateUnavailable
        | graph_wire.NoGraph,
    )
    async def run_graph_state(run_id: str):
        try:
            src = await graphs.source(run_id)
        except RunNotFound:
            if graphs.pointer_exists(run_id):
                return graph_wire.GraphStateUnavailable(reason="retention_expired", problems=[])
            raise HTTPException(404, f"no run {run_id!r}") from None
        if src.run_input is None:
            return graph_wire.NoGraph()
        if src.topology is None:
            # E-77 R-10/FR-021: registry drift degrades the projection, it is
            # never a server error.
            return graph_wire.GraphStateUnavailable(
                reason="registry_drift", problems=list(src.problems)
            )
        try:
            view = await graphs.view(src, run_id)
        except RunQueryFailed as e:
            raise HTTPException(502, str(e)) from e
        return graph_wire.project_graph_state(
            view,
            src.run_input.graph,
            src.topology,
            execution_closed=src.closed,
            close_status=src.close_status,
            registry=src.registry if src.registry is not None else NODE_TYPES,
        )

    @router.post("/runs", response_model=StartedRun)
    async def start(body: StartBody):
        idea = IdeaBrief(
            title=body.title, description=body.description, mode=body.mode, repo_url=body.repo
        )
        wf_id = f"feature-{slug(body.title)}"
        # B4 fleet back-pressure -- see
        # docs/superpowers/specs/2026-09-09-b4-fleet-backpressure-design.md.
        # 429 rather than 502: a full review queue is a load limit to back off
        # from, not a broken upstream. The cap is read first so an un-opted-in
        # deployment never pays the snapshot.
        cap = fleet_pending_cap()
        if cap is not None:
            try:
                check_fleet_capacity(await poller.snapshot(), cap)
            except FleetCapacityExceeded as e:
                raise HTTPException(429, str(e)) from None
        try:
            await start_run(idea, PipelineConfig(), wf_id)
        except HTTPException:
            raise
        except GraphStartError as e:
            raise HTTPException(422, str(e)) from e
        except Exception as e:  # noqa: BLE001
            if "already started" in str(e).lower():
                raise HTTPException(409, f"run {wf_id!r} already exists") from e
            raise HTTPException(502, str(e)) from e
        return StartedRun(run_id=wf_id)

    return router
