"""GraphWorkflow -- the pipeline as data (E-74, FR-1203).

A thin Temporal layer over E-73's GraphRouter: validate the pinned graph,
capture the memory watermark, run the dispatcher, return today's outcome
string (spec §5.6), run retro. Every new run starts here; FeatureWorkflow
stays registered only for in-flight executions (grace-retention, OQ-10).
"""

from __future__ import annotations

from temporalio import workflow
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from ..agents import (
        loader as _loader,  # noqa: F401 -- validate()'s lazy import stays passthrough
    )
    from ..core.context import StageServices
    from ..core.models import RunState, RunSummary
    from ..graph.model import PipelineGraph
    from ..graph.node_types import NODE_TYPES
    from ..graph.run_view import GraphRunView, stage_marks
    from ..graph.validate import InvalidGraph, from_graph
    from ..memory.activities import WatermarkInput, capture_watermark
    from .benchmark_host import BenchmarkHost
    from .board_host import BoardHost
    from .gates import GateHost
    from .graph_catalog import executable
    from .graph_dispatch import GraphDispatcher, outcome_string
    from .graph_nodes import HANDLERS
    from .graph_nodes.base import RunFacts
    from .memory_host import MEM_ACT, MemoryHost
    from .models import GraphRunInput
    from .question_host import QuestionHost
    from .report_host import ReportHost
    from .role_host import RoleHost
    from .run_host import RunHost
    from .task_host import TaskHost


@workflow.defn
class GraphWorkflow(
    RunHost,
    GateHost,
    ReportHost,
    BoardHost,
    BenchmarkHost,
    MemoryHost,
    RoleHost,
    QuestionHost,
    TaskHost,
):
    def __init__(self) -> None:
        super().__init__()
        self._integration_head: str = ""
        self._base_sha: str = ""
        self._integration_wt: str = ""
        self._codebase_map = None
        # E-75 §4.2: read by graph_view / run_state only; set once by run().
        self._graph: PipelineGraph | None = None
        self._graph_sha: str = ""
        self._dispatcher: GraphDispatcher | None = None
        self._result: str | None = None
        self._ctx = StageServices(
            emit=self._emit,
            stage=self._stage,
            run_role=self._run_role,
            cached_stage=self._cached_stage,
            revisable_stage=self._revisable_stage,
            record=self._record,
            judge=self._judge,
            recall=self._recall,
            retain=self._retain,
            gate=self._gate,
            ask_and_wait=self.ask_and_wait,
        )

    @workflow.query
    def run_summary(self) -> RunSummary | None:
        """The retro-stage RunSummary; None until the run terminates (E-32)."""
        return self._run_summary

    @workflow.query
    def run_state(self) -> RunState | None:
        """Live run state for the dashboard fleet view (E-10), with the
        graph's stage marks once dispatch has started (E-75 §5.3)."""
        snap = self._snapshot_run_state()
        view = self._graph_run_view()
        if snap is None or view is None or self._graph is None or self._dispatcher is None:
            return snap
        marks = stage_marks(view, self._dispatcher.topology, self._graph, NODE_TYPES)
        return snap.model_copy(update={"stage_marks": marks})

    @workflow.query
    def graph_view(self) -> GraphRunView | None:
        """Router state + per-activation facts (E-75 §4.2); None before dispatch."""
        return self._graph_run_view()

    def _graph_run_view(self) -> GraphRunView | None:
        d = self._dispatcher
        if d is None:
            return None
        return d.view(
            graph_sha=self._graph_sha,
            result=self._result,
            pending=self._pending_facts(),
            spend=self._activation_spend,
        )

    @workflow.run
    async def run(self, inp: GraphRunInput) -> str:
        if isinstance(inp, dict):
            inp = GraphRunInput.model_validate(inp)
        idea, cfg = inp.idea, inp.cfg
        invalid: InvalidGraph | None = None
        try:
            router = from_graph(inp.graph, NODE_TYPES, roles=inp.roles)
        except InvalidGraph as e:
            invalid = e
        if invalid is not None:
            raise ApplicationError(f"invalid graph: {invalid}", non_retryable=True)
        problems = executable(inp.graph, HANDLERS)
        if problems:
            raise ApplicationError(
                "graph not executable: " + "; ".join(p.message for p in problems),
                non_retryable=True,
            )

        self._graph = inp.graph
        self._graph_sha = inp.graph.content_sha()

        self._idea = idea
        self._started_at = workflow.now()
        self._run_id = workflow.info().workflow_id
        self._cfg = cfg
        self._budget_threshold = cfg.run_budget_usd  # E-33
        if cfg.memory.enabled:
            self._memory_watermark = cfg.memory.watermark or (
                await workflow.execute_activity(
                    capture_watermark,
                    WatermarkInput(
                        bank=cfg.memory.project_bank,
                        backend=cfg.memory.backend,
                        base_url=cfg.memory.base_url,
                    ),
                    **MEM_ACT,
                )
            )
        facts = RunFacts(
            idea=idea,
            repo_path=idea.repo_url or "/var/sdlc/repo",
            run_id=self._run_id,
            seeded=inp.seeded,
            memory_watermark=self._memory_watermark,
        )
        dispatcher = GraphDispatcher(
            host=self,
            services=self._ctx,
            router=router,
            graph=inp.graph,
            registry=NODE_TYPES,
            handlers=HANDLERS,
            facts=facts,
            cfg=cfg,
        )
        self._dispatcher = dispatcher
        outcome = await dispatcher.run()
        if outcome.stored_failure is not None:
            raise outcome.stored_failure  # D8: same failure as FeatureWorkflow; retro not run (U9)
        result = outcome_string(outcome, router.topology)
        await self._retro(cfg, idea, result)
        self._result = result  # E-75 F3: never a success string while retro can still fail
        return result
