"""GraphDispatcher -- the E-74 dispatch loop over GraphRouter (spec §5.4-§5.6).

Router state is owned by `run` alone. Handler tasks catch and append; `run`
classifies, runs the budget boundary, finalize, then advances. No per-step
commands: the command stream is a function of the handlers alone, which is
what makes the golden command projection reproducible.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from temporalio import workflow
from temporalio.exceptions import FailureError, is_cancelled_exception
from temporalio.workflow import _NotInWorkflowEventLoopError

with workflow.unsafe.imports_passed_through():
    from pydantic import PydanticUserError
    from pydantic_ai.exceptions import AgentRunError, UserError

    from ..core.models import NodeFailure, PipelineConfig
    from ..graph.model import PipelineGraph
    from ..graph.node_types import NodeTypeSpec, resolve_stage
    from ..graph.router import Activation, Emitted, GraphRouter, Halt, RouterState, Step
    from ..graph.run_view import (
        ACTIVATION,
        ActivationFacts,
        GraphRunView,
        PendingFact,
        UnroutedFailure,
    )
    from ..graph.topology import Topology
    from .graph_nodes.base import (
        Handler,
        NodeContext,
        NodeResult,
        RunFacts,
        StoredPayload,
        graph_has_research,
        project_cfg,
    )
    from .role_host import _BudgetRejected

# FailureError fails an execution in temporalio itself; the other three are
# what PydanticAIPlugin registers as workflow_failure_exception_types (D8).
FAILURE_TYPES: tuple[type[BaseException], ...] = (
    FailureError,
    UserError,
    PydanticUserError,
    AgentRunError,
)


@dataclass
class DispatchOutcome:
    state: RouterState
    terminal_result: str | None
    last_sink_result: str | None
    budget_halted: bool
    stored_failure: BaseException | None


@dataclass(frozen=True, slots=True)
class ActivationAttrib:
    """E-77 per-activation facts (data-model "Dispatcher per-activation
    facts"): the router round, the resolved canonical stage and (from T031)
    the fail-edge re-entry indicator, captured at issue time. Owner:
    GraphDispatcher, filled in _start. Reader: GraphWorkflow._stamp. Memory
    only — it issues no commands (FR-025)."""

    node_id: str
    round: int
    node_stage: str
    fail_reentry: Literal[0, 1] | None = None  # T031 replaces this with the derived indicator


class GraphDispatcher:
    def __init__(
        self,
        *,
        host: Any,
        services: Any,
        router: GraphRouter,
        graph: PipelineGraph,
        registry: Mapping[str, NodeTypeSpec],
        handlers: Mapping[str, Handler],
        facts: RunFacts,
        cfg: PipelineConfig,
    ) -> None:
        self._host = host
        self._services = services
        self._router = router
        self._registry = registry
        self._handlers = handlers
        self._facts = facts
        self._cfg = cfg
        self._nodes = {n.id: n for n in graph.nodes}
        self._research = graph_has_research(graph)
        self._payloads: dict[str, StoredPayload] = {}
        self._carries: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancelled: list[asyncio.Task[None]] = []
        self._results: list[tuple[str, Any]] = []
        self._state: RouterState = router.start().state  # replaced by _loop's start
        self._terminal_result: str | None = None
        self._last_sink_result: str | None = None
        self._budget_halted = False
        self._stored_failure: BaseException | None = None
        # E-75 §4.2: memory-only facts for the graph_view query (no commands).
        self._started: dict[str, datetime] = {}
        self._ended: dict[str, datetime] = {}
        # E-77: memory-only attribution facts, keyed by activation id (FR-014).
        self._attrib: dict[str, ActivationAttrib] = {}
        self._escalated_by: str | None = None
        self._unrouted: UnroutedFailure | None = None

    @property
    def _t(self) -> Topology:
        return self._router.topology

    @property
    def topology(self) -> Topology:
        return self._router.topology

    async def run(self) -> DispatchOutcome:
        try:
            return await self._loop()
        except BaseException as e:
            if is_cancelled_exception(e):
                # §5.4 step 8: Temporal cancels only the primary task.
                running = [self._tasks[k] for k in sorted(self._tasks)]
                for task in running:
                    task.cancel()
                await workflow.wait_condition(lambda: all(t.done() for t in running))
            raise

    async def _loop(self) -> DispatchOutcome:
        step = self._router.start()
        self._state = step.state
        held = list(step.activations)
        while True:
            for act in held:
                self._start(act)
            held = []
            if self._state.outcome != "running":
                break
            await workflow.wait_condition(lambda: bool(self._results))
            aid, raw = self._results.pop(0)
            self._tasks.pop(aid, None)
            self._ended.setdefault(aid, workflow.now())
            if aid not in {a.activation_id for a in self._state.live}:
                continue  # cancelled by an invalidation or a terminal step
            node_id = aid.rpartition("#")[0]
            result = self._classify(aid, node_id, raw)
            if result is None:
                continue
            edges = self._t.out_ports[node_id].get(result.port)
            if edges is None:
                raise RuntimeError(f"{aid}: {result.port!r} is not an out-port of {node_id!r}")
            terminal = self._t.terminal_ports.get(node_id, {})
            if result.result is not None and edges and result.port not in terminal:
                raise RuntimeError(f"{aid}: result on the edged non-terminal port {result.port!r}")
            if self._is_boundary(node_id, result.port, edges):
                await workflow.wait_condition(
                    lambda: all(self._tasks[k].done() for k in sorted(self._tasks))
                )
                if await self._budget_rejects():
                    self._halt_budget()
                    continue  # finalize skipped: feature.py:588 raises before :589 publishes
            if result.finalize is not None:
                await result.finalize()
            ref = f"{aid}.{result.port}"
            self._payloads[ref] = StoredPayload(
                model=result.payload,
                producer=aid,
                author_model=result.author_model,
                meta=dict(sorted(result.meta.items())),
            )
            live = next(a for a in self._state.live if a.activation_id == aid)
            if result.port in live.unavailable_ports and self._escalated_by is None:
                self._escalated_by = aid  # router step 2 terminates ESCALATED on this emission
            step = self._router.advance(
                self._state, Emitted(activation_id=aid, port=result.port, payload_ref=ref)
            )
            self._apply(step)
            if result.result is not None:
                if step.outcome in ("rejected", "failed"):
                    self._terminal_result = result.result
                elif not edges:
                    self._last_sink_result = result.result
            held = list(step.activations)
        await workflow.wait_condition(lambda: all(t.done() for t in self._cancelled))
        return DispatchOutcome(
            state=self._state,
            terminal_result=self._terminal_result,
            last_sink_result=self._last_sink_result,
            budget_halted=self._budget_halted,
            stored_failure=self._stored_failure,
        )

    def _start(self, act: Activation) -> None:
        node = self._nodes[act.node_id]
        spec = self._registry[node.type]
        handler = self._handlers[node.type]
        cfg = project_cfg(self._cfg, node, spec, research_in_graph=self._research)
        nc = NodeContext(
            ctx=self._services,
            host=self._host,
            facts=self._facts,
            node=node,
            spec=spec,
            topology=self._t,
            payloads=self._payloads,
            carries=self._carries,
        )

        self._started[act.activation_id] = workflow.now()
        self._attrib[act.activation_id] = ActivationAttrib(  # E-77 FR-014
            node_id=act.node_id,
            round=act.round,
            node_stage=resolve_stage(node.type, self._registry),
            fail_reentry=None,  # T031 wires the router-derived indicator
        )

        async def _one() -> None:
            ACTIVATION.set(act.activation_id)  # the ONLY set site (E-75 D4; pinned)
            try:
                out: Any = await handler(nc, act, cfg)
            except BaseException as e:  # noqa: BLE001 -- run() classifies (§5.4 step 2)
                out = e
            self._results.append((act.activation_id, out))

        self._tasks[act.activation_id] = asyncio.create_task(_one())

    def _classify(self, aid: str, node_id: str, raw: Any) -> NodeResult | None:
        """§5.4 step 4. Called outside any except block, so a raise here never
        picks up a spurious __context__ (advisor Q2 F5 trap)."""
        if not isinstance(raw, BaseException):
            return raw
        if is_cancelled_exception(raw):
            raise raw
        if isinstance(raw, _BudgetRejected):
            self._halt_budget()
            return None
        spec = self._registry[self._nodes[node_id].type]
        declares_fail = any(p.name == "fail" and p.direction == "out" for p in spec.ports)
        if isinstance(raw, FAILURE_TYPES) and declares_fail:
            if not self._t.out_ports[node_id]["fail"]:
                self._stored_failure = raw
                self._unrouted = UnroutedFailure(activation_id=aid, error_type=type(raw).__name__)
            return NodeResult(
                port="fail",
                payload=NodeFailure(
                    activation_id=aid, error_type=type(raw).__name__, message=str(raw)
                ),
            )
        raise raw

    def _is_boundary(self, node_id: str, port: str, edges: tuple[str, ...]) -> bool:
        mode = self._registry[self._nodes[node_id].type].budget_after
        if mode == "none" or any(e in self._t.bounds for e in edges):
            return False
        if mode == "exiting":
            return True
        return bool(edges)

    async def _budget_rejects(self) -> bool:
        try:
            await self._host._check_budget(self._cfg)
        except _BudgetRejected:
            return True
        return False

    def _halt_budget(self) -> None:
        self._apply(self._router.advance(self._state, Halt(outcome="rejected", reason="budget")))
        self._budget_halted = True

    def _apply(self, step: Step) -> None:
        self._state = step.state
        for cid in step.cancelled:
            try:
                self._ended.setdefault(cid, workflow.now())
            except _NotInWorkflowEventLoopError:
                # E-75 §4.2 stamps cancelled activations' end only inside a
                # real workflow run; chaos tests drive _classify/_apply
                # outside an event loop, where workflow.now() cannot exist.
                pass
            task = self._tasks.pop(cid, None)
            if task is not None:
                task.cancel()
                self._cancelled.append(task)

    def view(
        self,
        *,
        graph_sha: str,
        result: str | None,
        pending: tuple[PendingFact, ...],
        spend: Mapping[str, tuple[float, bool]],
    ) -> GraphRunView:
        """E-75 §4.2: the only reader of router state from outside. Sync and
        read-only -- safe inside a query handler."""
        activations = {
            aid: ActivationFacts(
                started_at=started,
                ended_at=self._ended.get(aid),
                cost_usd=spend.get(aid, (0.0, True))[0],
                priced=spend.get(aid, (0.0, True))[1],
            )
            for aid, started in sorted(self._started.items())
        }
        return GraphRunView(
            graph_sha=graph_sha,
            state=self._state,
            activations=activations,
            pending=pending,
            result=result,
            escalated_by=self._escalated_by,
            unrouted_failure=self._unrouted,
        )


def outcome_string(outcome: DispatchOutcome, topology: Topology) -> str:
    """§5.6: the run's return string, a wire contract."""
    state = outcome.state
    if state.outcome == "rejected":
        if outcome.budget_halted:
            return "rejected:budget"
        if outcome.terminal_result is not None:
            return outcome.terminal_result
        return f"rejected:{(state.reason or '').split('.', 1)[0]}"
    if state.outcome == "failed":
        if outcome.terminal_result is not None:
            return outcome.terminal_result
        return f"failed:{state.reason}"
    if state.outcome == "escalated":
        return f"escalated:{state.reason}"
    if outcome.last_sink_result is not None:
        return outcome.last_sink_result
    sinks = sorted(
        n
        for n, ns in sorted(state.nodes.items())
        if ns.status == "done"
        and ns.taken_port is not None
        and not topology.out_ports[n][ns.taken_port]
    )
    return f"completed:{','.join(sinks)}"
