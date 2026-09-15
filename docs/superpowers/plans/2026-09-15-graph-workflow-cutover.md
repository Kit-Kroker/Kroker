# E-74 GraphWorkflow Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `FeatureWorkflow._pipeline` with a thin Temporal `GraphWorkflow` that drives E-73's `GraphRouter` over a pinned `PipelineGraph`, and move every new run onto it while `FeatureWorkflow` stays registered, behaviourally unchanged and replay-proven, for in-flight runs.

**Architecture:** Two fast-forward merges. **M1** is behaviour-neutral: it records FeatureWorkflow histories and golden traces from unchanged `main`, extracts the code both workflows share under a `Replayer` test, and extends the pure graph layer (terminal ports, `Halt`, `budget_after`, the post-plan catalog). **M2** adds the dispatcher, node handlers, shipped graphs and `GraphWorkflow`; proves exact golden-trace equality; then cuts over the four start sites, patches the two parent workflows per child, and updates inbox/fleet queries.

**Tech Stack:** Python 3.11+, temporalio 1.30.0 (`WorkflowEnvironment.start_time_skipping`, `Replayer`, `workflow.patched`), pydantic v2, pydantic-ai `PydanticAIPlugin`, PyYAML, pytest (+ pytest-asyncio, pytest-timeout).

**Spec:** `docs/superpowers/specs/2026-09-15-graph-workflow-cutover-design.md` (user rulings U1–U10 in §2.1 are settled; read it beside this plan).

**Plan review:** reviewer-approved 2026-09-16 (round 2, after one CHANGES REQUESTED round); skeptic and advisor rounds dispositioned in the last section. Consultation logs: `.workspace/tmp/e74-plan-skeptic.md`, `advisor-e74-q3.md`, `e74-plan-reviewer-r1.md`, `e74-plan-reviewer-r2.md` (uncommitted scratch).

## Global Constraints

- **Branch:** all work happens on `feat/graph-workflow` in the exec worktree. Never commit on `main`.
- **Milestones are plan-structural:** Task 12 ends **CHECKPOINT M1** and Task 23 ends **CHECKPOINT M2**. At each checkpoint the executor STOPS; the orchestrator verifies and fast-forwards `main`. M2 work starts only after the orchestrator confirms the M1 merge.
- **Task 1 runs on unchanged `main` code.** It adds test files and fixtures only. No file under `src/` changes before Task 1's commit lands.
- **Commits:** write the message with the Write tool to `.workspace/tmp/e74-t<N>-msg.txt` (subject line + blank line + body), then `git add <path>` with **one path per `git add` invocation**, then `git commit -F .workspace/tmp/e74-t<N>-msg.txt`.
  - **No attribution trailers of any kind**: no `Co-Authored-By:` line in any form, no `Claude-Session:` links, no generated-by footers, even where a skill template prints one. Name the deviation in your final report.
  - **No heredocs.** The host shell may be PowerShell 5.1.
- **Per-task review gate:** do not start Task N+1 until the reviewer seat has replied approve / fixes-needed on Task N's diff.
- **File ceiling:** 1000 physical lines per file (`python scripts/check_file_size.py`). `feature.py` may only shrink.
- **JavaScript checks:** run only `python scripts/check_ui.py` (`interfaces/AGENTS.md`). Never run `npm`, `npx`, `vitest` or `playwright` directly.
- **Formatting of plan code:** code blocks in this plan are exact in content, not in layout. Run `ruff format <file>` and `ruff check --fix <file>` on every file you create or edit before the gates; they only reorder imports and wrap lines.
- **Every task's gates before commit:**
  - the task's named tests;
  - `ruff check .`;
  - `ruff format --check .`;
  - `mypy`;
  - `python scripts/check_file_size.py`.
- **Checkpoint gates** additionally run the whole fast tier (`pytest -q`).
- **Temporal tier:** run with `pytest <path> -m temporal -q --timeout=300 --timeout-method=thread`.
  - Never chain two pytest invocations in one shell command.
  - This workstation can hang on the temporal tier (`.workspace/tasks/2026-09-09-temporal-tier-hangs-on-windows.md`). Run one test file at a time. If a run exceeds its timeout without a verdict, STOP and report; do not retry in a loop.
- **Sandbox imports:** every new module that executes inside a workflow imports sdlc models under `with workflow.unsafe.imports_passed_through():`. This avoids the pydantic class-duplication trap (memory `temporal-sandbox-pydantic-duplication`).
- **Graph purity:** `src/sdlc/graph/` never imports `temporalio`, `sdlc.stages`, `sdlc.agents` or `sdlc.benchmarks` at module level (pinned by `tests/graph/test_graph_purity.py`).
- **Binding stop-guards.** On fire: stop, diagnose (reproduce, isolate causally), report. Clearance comes only from the orchestrator.
  - **SG-1:** a capture run's two projections differ.
  - **SG-2:** the Replayer test goes red after any `src/` change. Never re-record histories to make it pass; that is U6.
  - **SG-3:** a GraphWorkflow golden run differs from its golden file.
  - **SG-4:** any temporal-tier hang.
  - **SG-5:** a pre-existing test fails and the task does not name it.
- **Grace-edit rule (from Task 2 on, U6):** a command-changing edit to code FeatureWorkflow executes must be wrapped in `workflow.patched("<epic>-<slug>")`. The Replayer test enforces it.

## File Structure

**M1 — tests/replay (capture + proof):**
- `tests/replay/__init__.py`: empty package marker.
- `tests/replay/projection.py`: golden projections from a `WorkflowHistory`, plus the trace recorder.
- `tests/replay/scenarios.py`: the scenario matrix (inputs, fakes, drivers), shared by capture (M1) and golden runs (M2).
- `tests/replay/harness.py`: runs one scenario against a starter, returns `Captured`, reads and writes fixtures.
- `tests/replay/test_capture_feature.py`: env-gated capture (temporal tier).
- `tests/replay/test_fixtures_present.py`: fixture presence and provenance (fast tier).
- `tests/replay/test_feature_replay.py`: Replayer over every history (fast tier).
- `tests/replay/histories/<scenario>.json`, `tests/replay/golden/<scenario>.json`: data.

**M1 — src extractions:**
- `src/sdlc/workflows/run_host.py` (new `RunHost` mixin): gate hooks, run-state snapshot, `_retro`.
- `src/sdlc/workflows/build.py` (new): `run_tasks`, the task scheduler moved verbatim from `feature.py:635-716`.
- `src/sdlc/stages/plan/validation.py` (new): `validate_task_graph`, moved from `feature.py`.
- `src/sdlc/stages/architecture/step.py`, `src/sdlc/stages/plan/step.py`: split into `prepare`/`produce`/`finish`; `step()` composes them.
- `src/sdlc/workflows/feature.py`: shrinks, and inherits `RunHost`.

**M1 — graph layer:**
- `src/sdlc/graph/model.py`: `NodePort.terminal`.
- `src/sdlc/graph/topology.py`: `Topology.terminal_ports`.
- `src/sdlc/graph/validate.py`: builds `terminal_ports`.
- `src/sdlc/graph/router.py`: step 4 generalised, `failed` outcome, `Halt`.
- `src/sdlc/graph/node_types.py`: `budget_after`, gate `reject` terminal, post-plan catalog, catch hardening.
- `src/sdlc/graph/payloads.py`: four new payloads.
- `src/sdlc/graph/__init__.py`: export `Halt`.
- `src/sdlc/core/models.py`: `NodeFailure`.
- `src/sdlc/workflows/models.py`: `BuildResult`, `AnalyzeResult`, `PullRequest` (M1); `GraphRunInput` (M2).

**M2 — interpreter:**
- `src/sdlc/workflows/graph_nodes/__init__.py`: `HANDLERS`, `NOT_EXECUTABLE`.
- `src/sdlc/workflows/graph_nodes/base.py`: `StoredPayload`, `NodeResult`, `RunFacts`, `NodeContext`, `Handler`, `project_cfg`, input helpers.
- `src/sdlc/workflows/graph_nodes/precode.py`: intake, context, research, clarify, architect, plan handlers.
- `src/sdlc/workflows/graph_nodes/gate.py`: the generic gate handler plus the finish table.
- `src/sdlc/workflows/graph_nodes/postplan.py`: plan_check, seed.spec, seed.plan, code, analyze, merge, deploy.
- `src/sdlc/workflows/graph_catalog.py`: shipped graphs, `select_graph`, templating, `resolved_roles`, `executable`, `build_run_input`, `GraphStartError`.
- `src/sdlc/workflows/graphs/{default,default-research,seeded}.graph.yaml`.
- `src/sdlc/workflows/graph_dispatch.py`: `GraphDispatcher`, `DispatchOutcome`, `FAILURE_TYPES`, `outcome_string`.
- `src/sdlc/workflows/graph.py`: `GraphWorkflow`.
- `src/sdlc/workflows/pipeline_child.py`: `execute_pipeline_child` (per-child patch).

**M2 — cutover:**
- Modified: `src/sdlc/cli.py`, `interfaces/dashboard/api/main.py`, `src/sdlc/dashboard/api.py`, `src/sdlc/operator/tools.py`, `src/sdlc/channels/inbox.py`, `src/sdlc/dashboard/fleet.py`, `src/sdlc/workflows/tidyup.py`, `src/sdlc/benchmarks/workflow.py`, `src/sdlc/worker.py`.
- Tests are named per task. Docs are listed in Tasks 12 and 23.

---

## MILESTONE M1 — behaviour-neutral foundation

### Task 1: Capture FeatureWorkflow histories and golden traces from UNCHANGED main

No `src/` file changes in this task (Global Constraints). Everything here is test code and recorded data.

**Files:**
- Create: `tests/replay/__init__.py`
- Create: `tests/replay/projection.py`
- Create: `tests/replay/scenarios.py`
- Create: `tests/replay/harness.py`
- Create: `tests/replay/test_projection.py`
- Create: `tests/replay/test_capture_feature.py`
- Create: `tests/replay/test_fixtures_present.py`
- Create (generated): `tests/replay/histories/*.json`, `tests/replay/golden/*.json`

**Interfaces:**
- Produces:
  - `projection.command_projection(history: WorkflowHistory) -> list[str]`
  - `projection.close_projection(history: WorkflowHistory) -> str`
  - `projection.TraceRecorder` with `.install(monkeypatch)` and `.trace(workflow_id) -> list[list[str]]`
  - `scenarios.Scenario`, `scenarios.SCENARIOS: tuple[Scenario, ...]`, `scenarios.GOLDEN_SCENARIOS`
  - `harness.Starter`, `harness.FEATURE_STARTER`
  - `harness.capture(scenario, starter, monkeypatch, tmp_path) -> Captured`
  - `harness.load_golden(name) -> dict`, `harness.load_history(name) -> WorkflowHistory`
  - `harness.write_fixtures(name, captured, starter_name)`
  - M2 Tasks 19–20 add a `GRAPH_STARTER` beside `FEATURE_STARTER`.

- [ ] **Step 1: Write the failing projection unit test**

Create `tests/replay/__init__.py` (empty) and `tests/replay/test_projection.py`:

```python
"""Golden projections over a synthetic history (E-74 spec §4.1)."""

from __future__ import annotations

from temporalio.api.enums.v1 import EventType
from temporalio.api.history.v1 import HistoryEvent
from temporalio.client import WorkflowHistory
from temporalio.contrib.pydantic import pydantic_data_converter

from tests.replay.projection import close_projection, command_projection


def _history(*events: HistoryEvent) -> WorkflowHistory:
    return WorkflowHistory("wf-1", list(events))


def _scheduled(name: str) -> HistoryEvent:
    ev = HistoryEvent(event_type=EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED)
    ev.activity_task_scheduled_event_attributes.activity_type.name = name
    return ev


def test_command_projection_keeps_order_and_kinds():
    child = HistoryEvent(event_type=EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED)
    child.start_child_workflow_execution_initiated_event_attributes.workflow_type.name = (
        "DeploymentWorkflow"
    )
    timer = HistoryEvent(event_type=EventType.EVENT_TYPE_TIMER_STARTED)
    cancel = HistoryEvent(event_type=EventType.EVENT_TYPE_ACTIVITY_TASK_CANCEL_REQUESTED)
    marker = HistoryEvent(event_type=EventType.EVENT_TYPE_MARKER_RECORDED)
    history = _history(_scheduled("classify_repo"), timer, marker, child, cancel)
    assert command_projection(history) == [
        "activity:classify_repo",
        "timer",
        "child:DeploymentWorkflow",
        "cancel_requested",
    ]


def test_close_projection_completed_failed_canceled():
    done = HistoryEvent(event_type=EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED)
    payloads = pydantic_data_converter.payload_converter.to_payloads(["deployed:x"])
    done.workflow_execution_completed_event_attributes.result.payloads.extend(payloads)
    assert close_projection(_history(done)) == "deployed:x"

    failed = HistoryEvent(event_type=EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED)
    failure = failed.workflow_execution_failed_event_attributes.failure
    failure.message = "boom"
    failure.application_failure_info.type = "ApplicationError"
    assert close_projection(_history(failed)) == "FAILED:ApplicationError:boom"

    canceled = HistoryEvent(event_type=EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CANCELED)
    assert close_projection(_history(canceled)) == "CANCELED"
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/replay/test_projection.py -q`
Expected: FAIL. `ModuleNotFoundError: No module named 'tests.replay.projection'`.

- [ ] **Step 3: Implement `tests/replay/projection.py`**

```python
"""Golden-trace projections (E-74 spec §4.1).

Four projections make up a golden trace:
(1) STAGE_STARTED stage names;
(2) GATE_DECIDED rows;
(3) the ordered command projection of the history;
(4) the close.

(1) and (2) come from the in-memory run trace, so they are captured by
wrapping ReportHost._emit on an UNSANDBOXED capture worker. An unsandboxed
worker issues exactly the same commands as a sandboxed one.
"""

from __future__ import annotations

from typing import Any

from temporalio import workflow
from temporalio.api.enums.v1 import EventType
from temporalio.client import WorkflowHistory
from temporalio.contrib.pydantic import pydantic_data_converter


def command_projection(history: WorkflowHistory) -> list[str]:
    out: list[str] = []
    for ev in history.events:
        t = ev.event_type
        if t == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
            out.append(f"activity:{ev.activity_task_scheduled_event_attributes.activity_type.name}")
        elif t == EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED:
            attrs = ev.start_child_workflow_execution_initiated_event_attributes
            out.append(f"child:{attrs.workflow_type.name}")
        elif t == EventType.EVENT_TYPE_TIMER_STARTED:
            out.append("timer")
        elif t == EventType.EVENT_TYPE_ACTIVITY_TASK_CANCEL_REQUESTED:
            out.append("cancel_requested")
    return out


def close_projection(history: WorkflowHistory) -> str:
    for ev in reversed(history.events):
        t = ev.event_type
        if t == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED:
            payloads = list(ev.workflow_execution_completed_event_attributes.result.payloads)
            (value,) = pydantic_data_converter.payload_converter.from_payloads(payloads, [str])
            return str(value)
        if t == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED:
            failure = ev.workflow_execution_failed_event_attributes.failure
            return f"FAILED:{failure.application_failure_info.type}:{failure.message}"
        if t == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CANCELED:
            return "CANCELED"
        if t == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TERMINATED:
            return "TERMINATED"
    return "OPEN"


class TraceRecorder:
    """Records STAGE_STARTED and GATE_DECIDED per workflow id, skipping replays."""

    def __init__(self) -> None:
        self._rows: dict[str, list[list[str]]] = {}

    def install(self, monkeypatch: Any) -> None:
        from sdlc.observability.trace import RunEventKind
        from sdlc.workflows.report_host import ReportHost

        original = ReportHost._emit
        rows = self._rows

        def _emit(host: Any, kind: Any, stage: str | None = None, **data: str) -> None:
            if not workflow.unsafe.is_replaying():
                wid = workflow.info().workflow_id
                if kind is RunEventKind.STAGE_STARTED:
                    rows.setdefault(wid, []).append(["stage", stage or ""])
                elif kind is RunEventKind.GATE_DECIDED:
                    rows.setdefault(wid, []).append(
                        [
                            "gate",
                            data.get("gate", ""),
                            data.get("round", ""),
                            data.get("decided_by", ""),
                            data.get("approved", ""),
                        ]
                    )
            original(host, kind, stage, **data)

        monkeypatch.setattr(ReportHost, "_emit", _emit)

    def trace(self, workflow_id: str) -> list[list[str]]:
        return list(self._rows.get(workflow_id, []))
```

- [ ] **Step 4: Run the projection test and verify it passes**

Run: `pytest tests/replay/test_projection.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Write the scenario matrix `tests/replay/scenarios.py`**

Every scenario reuses an existing FeatureWorkflow test's fakes and driver logic. Drivers query and signal **by name**, so the same scenario later drives GraphWorkflow unchanged.

```python
"""The E-74 capture matrix (spec §4.1). Shared by M1 capture and M2 golden runs.

Drivers talk to the workflow by query/signal NAME ("pending_gate",
"answer_question", "submit_gate_decision"), never by a class attribute, so one
scenario drives FeatureWorkflow (captured) and GraphWorkflow (asserted).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from sdlc.assessment.activities import AssessmentTreeInput
from sdlc.core.models import (
    ExecutionMode,
    GateConfig,
    GateDecision,
    GateOutcome,
    GatePolicy,
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
)
from sdlc.harness.models import HarnessRunResult
from sdlc.observability.activities import export_run_artifacts
from sdlc.pricing import PriceUsageInput
from sdlc.pricing import price_usage as real_price_usage
from sdlc.stages.architecture.models import ArchitectureSpec, ValidationContract
from sdlc.stages.clarify.models import ClarifiedRequirements
from sdlc.stages.code.activities import CodingTaskInput
from sdlc.stages.merge.activities import evaluate_gate
from sdlc.stages.plan.models import DevTask, ImplementationPlan
from sdlc.stages.research.verify import verify_brief_activity
from sdlc.workflows.models import SeededWork
from tests.fakes.canned import (
    AGENT_SPECS,
    ARCH,
    PLAN,
    QUESTION_IDS,
    e2e_config,
    greenfield_idea,
)
from tests.fakes.fake_activities import GIT_FAKES, fake_classify_repo, git_fakes_except
from tests.fakes.fake_agents import fake_agent_activities
from tests.fakes.fake_deploy import DEPLOY_FAKES
from tests.fakes.fake_deploy import reset as reset_deploy
from tests.research.test_research_e2e import _research_fake_activities
from tests.test_feature_brownfield_stages import (
    BROWNFIELD_SPECS,
    SCAN_FAKES,
    fake_resolve_tree,
)

Handle = Any


# ---- driver helpers (by name) -------------------------------------------------


async def wait_for(handle: Handle, target: str, timeout_s: float = 30.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    last = None
    while asyncio.get_event_loop().time() < deadline:
        last = await handle.query("status")
        if last == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r} (last={last!r})")


async def answer_clarify(handle: Handle) -> None:
    await wait_for(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal("answer_question", args=[qid, "yes"])


async def decide(handle: Handle, gate: str, round_: int, outcome: GateOutcome, **kw: Any) -> None:
    await wait_for(handle, f"awaiting:{gate}")
    await handle.signal(
        "submit_gate_decision",
        GateDecision(gate=gate, round=round_, outcome=outcome, decided_by="human", **kw),
    )


A, R, V = GateOutcome.APPROVE, GateOutcome.REJECT, GateOutcome.REVISE


# ---- scenario-specific fakes ---------------------------------------------------


@activity.defn(name="price_usage")
async def fixed_price(inp: PriceUsageInput) -> float | None:
    return 1.0  # every metered proposer call costs exactly $1 (tests/test_budget_gate.py)


@activity.defn(name="assessment_resolve_tree")
async def unresolvable_tree(inp: AssessmentTreeInput) -> None:
    raise ApplicationError("no tree for this commit", non_retryable=True)


_BLOCKING: dict[str, asyncio.Event] = {}


@activity.defn(name="run_coding_task")
async def blocking_coding_task(inp: CodingTaskInput) -> HarnessRunResult:
    _BLOCKING["started"].set()
    while not activity.is_cancelled():
        activity.heartbeat()
        await asyncio.sleep(0.2)
    raise asyncio.CancelledError()


_WAVES: dict[str, asyncio.Event] = {}


def _waves_before() -> None:
    reset_deploy()
    _WAVES["t1_done"] = asyncio.Event()


def _t1_gated_evidence() -> Any:
    """t1's LAST command in run_one is its `review` evidence write
    (build.run_tasks: qa, review, deep_review=None). Setting the event there
    orders every command of the wave, whichever completion lands first."""
    from sdlc.board.activities import AttachEvidenceInput
    from sdlc.core.models import ArtifactRef

    @activity.defn(name="attach_task_evidence")
    async def gated(inp: AttachEvidenceInput) -> ArtifactRef:
        if inp.task_id == "t1" and inp.kind == "review":
            _WAVES["t1_done"].set()
        return ArtifactRef(kind="board_evidence", uri="file:///fake/evidence", sha256="0" * 64)

    return gated


def _staggered_coding_task() -> Any:
    @activity.defn(name="run_coding_task")
    async def staggered(inp: CodingTaskInput) -> HarnessRunResult:
        if inp.task_id == "t2":
            await asyncio.wait_for(_WAVES["t1_done"].wait(), timeout=120)
        return HarnessRunResult(
            harness=inp.harness,
            session_id=f"s-{inp.task_id}",
            exit_code=0,
            summary="implemented",
            commit_sha="cafe1234",
            input_tokens=1000,
            output_tokens=200,
            context_window=200000,
        )

    return staggered


def _two_task_plan() -> ImplementationPlan:
    def task(tid: str) -> DevTask:
        return DevTask(
            id=tid,
            title=f"Implement {tid}",
            description=f"Task {tid}.",
            acceptance_criteria=[f"{tid} works"],
            contract=ValidationContract(
                task_id=tid,
                assertions=[f"{tid} works"],
                test_commands=["pytest -q"],
                lint_commands=["ruff check ."],
                stack="Python/FastAPI",
            ),
        )

    return ImplementationPlan(tasks=[task("t1"), task("t2")], confidence=0.95)


def _specs_with_plan(plan: ImplementationPlan) -> list:
    return [
        (name, typ, plan if name == "planner_agent" else value) for name, typ, value in AGENT_SPECS
    ]


def brownfield_idea() -> IdeaBrief:
    return IdeaBrief(
        title="Brownfield task",
        description="Modify endpoint",
        mode=ProjectMode.BROWNFIELD,
        repo_url="/fake/repo",
        base_branch="main",
    )


def _deploying(cfg: PipelineConfig) -> PipelineConfig:
    cfg.deploy.enabled = True
    return cfg


# ---- the scenario record -------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    name: str
    idea: Callable[[], IdeaBrief]
    cfg: Callable[[], PipelineConfig]
    activities: Callable[[], list]
    drive: Callable[[Handle, Any], Awaitable[None]]
    seeded: Callable[[], SeededWork | None] = lambda: None
    before: Callable[[], None] = lambda: None
    # "concurrent": driver runs beside handle.result() with time skipping off.
    # "then_skip": driver runs with skipping off, then result() with skipping on.
    # "partial": driver reaches a mid-flight point; the harness then terminates.
    # "expect_error": driver runs beside result(), and result() is expected to raise.
    mode: str = "concurrent"
    golden: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


def _base_activities(specs: list = AGENT_SPECS) -> list:
    return [evaluate_gate, export_run_artifacts, *GIT_FAKES, *DEPLOY_FAKES, *fake_agent_activities(specs)]


async def _drive_happy(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    for gate in ("architecture", "plan", "deploy"):
        await decide(handle, gate, 1, A)


async def _drive_arch_revise_final(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "architecture", 1, V, guidance="split the service")
    await decide(handle, "architecture", 2, V, guidance="keep it single")
    await decide(handle, "architecture", 3, A)
    await decide(handle, "plan", 1, A)
    await decide(handle, "deploy", 1, A)


async def _drive_rounds_1(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "architecture", 1, V, guidance="once more")
    await decide(handle, "architecture", 2, A)
    await decide(handle, "plan", 1, A)
    await decide(handle, "deploy", 1, A)


async def _drive_plan_revise(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "architecture", 1, A)
    await decide(handle, "plan", 1, V, guidance="smaller tasks")
    await decide(handle, "plan", 2, A)
    await decide(handle, "deploy", 1, A)


async def _drive_timeout(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await wait_for(handle, "awaiting:architecture")


async def _drive_nothing(handle: Handle, env: Any) -> None:
    return None


async def _drive_deploy_only(handle: Handle, env: Any) -> None:
    await decide(handle, "deploy", 1, A)


async def _drive_budget_clarify_reject(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "budget", 1, R)


async def _drive_budget_arch_reject(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "architecture", 1, R)
    await decide(handle, "budget", 1, A)


async def _drive_research(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "deploy", 1, A)


async def _drive_clarify_only(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)


async def _drive_cancel(handle: Handle, env: Any) -> None:
    await answer_clarify(handle)
    await decide(handle, "architecture", 1, A)
    await decide(handle, "plan", 1, A)
    await asyncio.wait_for(_BLOCKING["started"].wait(), timeout=60)
    await handle.cancel()


def _budget_cfg(budget: float) -> Callable[[], PipelineConfig]:
    def make() -> PipelineConfig:
        cfg = e2e_config()
        cfg.run_budget_usd = budget
        return cfg

    return make


def _budget_activities() -> list:
    fakes = [a for a in GIT_FAKES if a is not real_price_usage]
    return [evaluate_gate, export_run_artifacts, fixed_price, *fakes, *DEPLOY_FAKES, *fake_agent_activities(AGENT_SPECS)]


def _research_cfg() -> PipelineConfig:
    cfg = PipelineConfig(
        research_enabled=True,
        gates={
            "research": GateConfig(policy=GatePolicy.OFF),
            "architecture": GateConfig(policy=GatePolicy.OFF),
            "plan": GateConfig(policy=GatePolicy.OFF),
            "deploy": GateConfig(policy=GatePolicy.HARD),
        },
        memoization_enabled=False,
        review_enabled=True,
    )
    cfg.deploy.enabled = True
    return cfg


def _rounds_1_cfg() -> PipelineConfig:
    cfg = _deploying(e2e_config())
    cfg.max_gate_rounds = 1
    return cfg


def _timeout_cfg() -> PipelineConfig:
    cfg = e2e_config()
    cfg.gate_timeout_hours = 1
    return cfg


def _waves_cfg() -> PipelineConfig:
    cfg = _deploying(e2e_config())
    cfg.execution_mode = ExecutionMode.WAVES
    return cfg


def _cancel_before() -> None:
    _BLOCKING["started"] = asyncio.Event()


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("greenfield_happy", greenfield_idea, lambda: _deploying(e2e_config()), _base_activities, _drive_happy, before=reset_deploy),
    Scenario(
        "brownfield_happy",
        brownfield_idea,
        lambda: _deploying(e2e_config()),
        lambda: [evaluate_gate, export_run_artifacts, fake_resolve_tree, *SCAN_FAKES, *GIT_FAKES, *DEPLOY_FAKES, *fake_agent_activities(BROWNFIELD_SPECS)],
        _drive_happy,
        before=reset_deploy,
    ),
    Scenario(
        "intake_reject",
        lambda: IdeaBrief(title="Brownfield task", description="Modify endpoint", mode=ProjectMode.BROWNFIELD, repo_url="/invalid/repo", base_branch="main"),
        e2e_config,
        lambda: [evaluate_gate, export_run_artifacts, *[a for a in GIT_FAKES if a is not fake_classify_repo], _bad_classify()],
        _drive_nothing,
    ),
    Scenario(
        "context_reject",
        brownfield_idea,
        e2e_config,
        lambda: [evaluate_gate, export_run_artifacts, unresolvable_tree, *SCAN_FAKES, *GIT_FAKES],
        _drive_nothing,
    ),
    Scenario("arch_revise_final", greenfield_idea, lambda: _deploying(e2e_config()), _base_activities, _drive_arch_revise_final, before=reset_deploy),
    Scenario("arch_timeout_reject", greenfield_idea, _timeout_cfg, lambda: [evaluate_gate, export_run_artifacts, *GIT_FAKES, *fake_agent_activities(AGENT_SPECS)], _drive_timeout, mode="then_skip"),
    Scenario("plan_revise_approve", greenfield_idea, lambda: _deploying(e2e_config()), _base_activities, _drive_plan_revise, before=reset_deploy),
    Scenario(
        "waves",
        greenfield_idea,
        _waves_cfg,
        lambda: [evaluate_gate, export_run_artifacts, *git_fakes_except("run_coding_task", "attach_task_evidence"), _staggered_coding_task(), _t1_gated_evidence(), *DEPLOY_FAKES, *fake_agent_activities(_specs_with_plan(_two_task_plan()))],
        _drive_happy,
        before=_waves_before,
    ),
    Scenario(
        "seeded",
        greenfield_idea,
        lambda: _deploying(e2e_config()),
        lambda: [evaluate_gate, export_run_artifacts, *GIT_FAKES, *DEPLOY_FAKES, *fake_agent_activities([s for s in AGENT_SPECS if s[0] not in {"clarify_agent", "architect_agent", "planner_agent"}])],
        _drive_deploy_only,
        seeded=lambda: SeededWork(arch=ARCH, plan=PLAN),
        before=reset_deploy,
    ),
    Scenario("budget_clarify_reject", greenfield_idea, _budget_cfg(0.5), _budget_activities, _drive_budget_clarify_reject),
    Scenario("budget_arch_reject", greenfield_idea, _budget_cfg(1.5), _budget_activities, _drive_budget_arch_reject),
    Scenario(
        "research_greenfield",
        greenfield_idea,
        _research_cfg,
        lambda: [evaluate_gate, verify_brief_activity, export_run_artifacts, *GIT_FAKES, *DEPLOY_FAKES, *_research_fake_activities(), *fake_agent_activities(AGENT_SPECS)],
        _drive_research,
        before=reset_deploy,
    ),
    Scenario(
        "delta_failed",
        brownfield_idea,
        e2e_config,
        lambda: [evaluate_gate, export_run_artifacts, fake_resolve_tree, *SCAN_FAKES, *git_fakes_except("check_brownfield_delta"), _failing_delta(), *fake_agent_activities(BROWNFIELD_SPECS)],
        _drive_clarify_only,
        mode="expect_error",
    ),
    Scenario(
        "cancel_during_code",
        greenfield_idea,
        e2e_config,
        lambda: [evaluate_gate, export_run_artifacts, *git_fakes_except("run_coding_task"), blocking_coding_task, *fake_agent_activities(AGENT_SPECS)],
        _drive_cancel,
        before=_cancel_before,
        mode="expect_error",
    ),
    Scenario("max_gate_rounds_1", greenfield_idea, _rounds_1_cfg, _base_activities, _drive_rounds_1, before=reset_deploy),
    Scenario(
        "partial_awaiting_architecture",
        greenfield_idea,
        e2e_config,
        lambda: [evaluate_gate, export_run_artifacts, *GIT_FAKES, *fake_agent_activities(AGENT_SPECS)],
        _drive_timeout,
        mode="partial",
        golden=False,
    ),
)

GOLDEN_SCENARIOS: tuple[Scenario, ...] = tuple(s for s in SCENARIOS if s.golden)


def _bad_classify() -> Any:
    from sdlc.context.models import RepoObservation
    from sdlc.stages.context.activities import RepoProbeInput

    @activity.defn(name="classify_repo")
    async def bad_classify(inp: RepoProbeInput) -> RepoObservation:
        return RepoObservation(is_git_repo=False, base_branch_resolves=False, reason="not a git repository")

    return bad_classify


def _failing_delta() -> Any:
    from sdlc.context.delta import DELTA_CHECK
    from sdlc.gate import CheckClass, CheckResult, build_check
    from sdlc.stages.context.activities import DeltaCheckInput

    @activity.defn(name="check_brownfield_delta")
    async def failing_delta(inp: DeltaCheckInput) -> CheckResult:
        return build_check(DELTA_CHECK, False, CheckClass.ABSOLUTE, "delta path nonexistent.py not in git tree")

    return failing_delta
```

`ClarifiedRequirements`, `ArchitectureSpec` and `ImplementationPlan` are type imports the canned specs rely on. Keep them if ruff asks. Run `ruff format tests/replay/scenarios.py` after writing; the long tuple lines are formatted by the tool, not by hand.

- [ ] **Step 6: Write `tests/replay/harness.py`**

```python
"""Run one scenario against a workflow starter and read/write fixtures (E-74 §4.1)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import subprocess
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.client import Client, WorkflowHandle, WorkflowHistory
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from tests.replay.projection import TraceRecorder, close_projection, command_projection
from tests.replay.scenarios import Scenario

ROOT = Path(__file__).parent
HISTORIES = ROOT / "histories"
GOLDEN = ROOT / "golden"
TASK_QUEUE = "e74-replay"


@dataclass(frozen=True)
class Starter:
    name: str
    workflows: tuple[type, ...]
    start: Callable[[Client, Scenario, str], Awaitable[WorkflowHandle]]


async def _start_feature(client: Client, scenario: Scenario, wf_id: str) -> WorkflowHandle:
    from sdlc.workflows.feature import FeatureWorkflow

    return await client.start_workflow(
        FeatureWorkflow.run,
        args=[scenario.idea(), scenario.cfg(), scenario.seeded()],
        id=wf_id,
        task_queue=TASK_QUEUE,
    )


def _feature_workflows() -> tuple[type, ...]:
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.feature import FeatureWorkflow

    return (FeatureWorkflow, DeploymentWorkflow)


FEATURE_STARTER = Starter("FeatureWorkflow", _feature_workflows(), _start_feature)


@dataclass(frozen=True)
class Captured:
    workflow_id: str
    history: WorkflowHistory
    golden: dict[str, Any]


async def capture(
    scenario: Scenario,
    starter: Starter,
    monkeypatch: Any,
    tmp_path: Path,
    *,
    sandboxed: bool = False,
) -> Captured:
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    scenario.before()
    recorder = TraceRecorder()
    if not sandboxed:
        recorder.install(monkeypatch)
    wf_id = f"e74-{scenario.name}-{uuid.uuid4()}"
    runner_kw: dict[str, Any] = {} if sandboxed else {"workflow_runner": UnsandboxedWorkflowRunner()}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=list(starter.workflows),
            activities=scenario.activities(),
            plugins=[PydanticAIPlugin()],
            **runner_kw,
        ):
            if scenario.mode == "then_skip":
                handle = await starter.start(env.client, scenario, wf_id)
                with env.auto_time_skipping_disabled():
                    await scenario.drive(handle, env)
                with contextlib.suppress(Exception):
                    await handle.result()
            else:
                with env.auto_time_skipping_disabled():
                    handle = await starter.start(env.client, scenario, wf_id)
                    driver = asyncio.create_task(scenario.drive(handle, env))
                    if scenario.mode == "partial":
                        await driver
                    else:
                        try:
                            await handle.result()
                        except Exception:
                            if scenario.mode != "expect_error":
                                raise
                        await driver
            history = await handle.fetch_history()
            if scenario.mode == "partial":
                await handle.terminate("e74 partial capture")
    golden = {
        "trace": recorder.trace(wf_id),
        "commands": command_projection(history),
        "close": close_projection(history),
    }
    return Captured(workflow_id=wf_id, history=history, golden=golden)


def source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def write_fixtures(name: str, captured: Captured, starter_name: str) -> None:
    HISTORIES.mkdir(exist_ok=True)
    GOLDEN.mkdir(exist_ok=True)
    commit = source_commit()
    (HISTORIES / f"{name}.json").write_text(
        json.dumps(
            {
                "workflow_id": captured.workflow_id,
                "workflow": starter_name,
                "source_commit": commit,
                "history": json.loads(captured.history.to_json()),
            },
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (GOLDEN / f"{name}.json").write_text(
        json.dumps(
            {"workflow": starter_name, "source_commit": commit, **captured.golden},
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def load_history(name: str) -> WorkflowHistory:
    data = json.loads((HISTORIES / f"{name}.json").read_text(encoding="utf-8"))
    return WorkflowHistory.from_json(data["workflow_id"], json.dumps(data["history"]))


def load_golden(name: str) -> dict[str, Any]:
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
```

For the `partial` scenario, the capture writes only the history. The golden file carries `trace`/`commands`/`close` too, but `golden=False` keeps it out of every equality assertion.

- [ ] **Step 7: Write the env-gated capture test `tests/replay/test_capture_feature.py`**

```python
"""E-74 Task 1: capture FeatureWorkflow histories + golden traces from unchanged main.

Runs only with SDLC_CAPTURE_HISTORIES=1. Capture-twice rule (spec §4.1): each
scenario runs twice and the fixtures are written only when both projections
agree. A disagreement is stop-guard SG-1 -- fix the scenario's fixture, never
the projection.
"""

from __future__ import annotations

import os

import pytest

from tests.replay.harness import FEATURE_STARTER, capture, write_fixtures
from tests.replay.scenarios import SCENARIOS

pytestmark = [
    pytest.mark.temporal,
    pytest.mark.skipif(
        os.environ.get("SDLC_CAPTURE_HISTORIES") != "1",
        reason="capture runs only on demand (E-74 Task 1)",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
async def test_capture_feature_scenario(scenario, monkeypatch, tmp_path):
    first = await capture(scenario, FEATURE_STARTER, monkeypatch, tmp_path / "a")
    second = await capture(scenario, FEATURE_STARTER, monkeypatch, tmp_path / "b")
    assert first.golden["commands"] == second.golden["commands"], "SG-1: unstable commands"
    assert first.golden["trace"] == second.golden["trace"], "SG-1: unstable trace"
    assert first.golden["close"] == second.golden["close"], "SG-1: unstable close"
    write_fixtures(scenario.name, first, FEATURE_STARTER.name)
```

- [ ] **Step 8: Write the failing fixture-presence test `tests/replay/test_fixtures_present.py`**

```python
"""Every scenario has a committed history + golden, captured from FeatureWorkflow."""

from __future__ import annotations

import pytest

from tests.replay.harness import load_golden, load_history
from tests.replay.scenarios import SCENARIOS

EXPECTED_CLOSES = {
    "greenfield_happy": "deployed:",
    "brownfield_happy": "deployed:",
    "intake_reject": "rejected:intake",
    "context_reject": "rejected:context",
    "arch_revise_final": "deployed:",
    "arch_timeout_reject": "rejected:architecture",
    "plan_revise_approve": "deployed:",
    "waves": "deployed:",
    "seeded": "deployed:",
    "budget_clarify_reject": "rejected:budget",
    "budget_arch_reject": "rejected:architecture",
    "research_greenfield": "deployed:",
    "delta_failed": "FAILED:",
    "cancel_during_code": "CANCELED",
    "max_gate_rounds_1": "deployed:",
    "partial_awaiting_architecture": "OPEN",  # history fetched before terminate: unfinished on purpose
}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_fixture_is_present_and_from_feature_workflow(scenario):
    golden = load_golden(scenario.name)
    assert golden["workflow"] == "FeatureWorkflow"
    assert len(golden["source_commit"]) == 40
    assert golden["close"].startswith(EXPECTED_CLOSES[scenario.name]), golden["close"]
    assert load_history(scenario.name).events


def test_every_scenario_has_an_expected_close():
    assert sorted(EXPECTED_CLOSES) == sorted(s.name for s in SCENARIOS)
```

Run: `pytest tests/replay/test_fixtures_present.py -q`
Expected: FAIL. `FileNotFoundError` for `tests/replay/golden/greenfield_happy.json`.

- [ ] **Step 9: Capture (unchanged main), one scenario per invocation**

For each scenario name in `SCENARIOS` order, run one invocation. Set the variable for the command only (bash form `SDLC_CAPTURE_HISTORIES=1 pytest ...`; PowerShell form `$env:SDLC_CAPTURE_HISTORIES='1'; pytest ...`):

Run: `pytest "tests/replay/test_capture_feature.py::test_capture_feature_scenario[greenfield_happy]" -m temporal -q --timeout=300 --timeout-method=thread`
Expected: PASS, and `tests/replay/histories/greenfield_happy.json` plus `tests/replay/golden/greenfield_happy.json` are written.

Repeat for the other 15 ids:
- `brownfield_happy`, `intake_reject`, `context_reject`, `arch_revise_final`
- `arch_timeout_reject`, `plan_revise_approve`, `waves`, `seeded`
- `budget_clarify_reject`, `budget_arch_reject`, `research_greenfield`
- `delta_failed`, `cancel_during_code`, `max_gate_rounds_1`, `partial_awaiting_architecture`

Only a failure inside the driver may be fixed inside `tests/replay/scenarios.py`, and only as an input or fake fix, never a projection fix. One more correction is allowed in Step 10: an `EXPECTED_CLOSES` entry in `test_fixtures_present.py` may be changed to the observed close prefix, citing the golden file's actual `close` in the task report. An SG-1 assertion or a hang is a STOP.

- [ ] **Step 10: Verify the fixture-presence test passes**

Run: `pytest tests/replay/test_fixtures_present.py -q`
Expected: PASS (17 passed). Confirm `git status --short src` prints nothing: no `src/` change exists.

- [ ] **Step 11: Commit**

Message file `.workspace/tmp/e74-t1-msg.txt`:

```text
test(replay): E-74 capture FeatureWorkflow histories and golden traces

Captured from unchanged main before any refactor (spec 4.1): 16 scenarios,
each run twice with equal projections (capture-twice rule). Golden traces
carry stage/gate trace, ordered command projection and close; histories
feed the Replayer proof of U2.
```

```bash
git add tests/replay/__init__.py
git add tests/replay/projection.py
git add tests/replay/scenarios.py
git add tests/replay/harness.py
git add tests/replay/test_projection.py
git add tests/replay/test_capture_feature.py
git add tests/replay/test_fixtures_present.py
git commit -F .workspace/tmp/e74-t1-msg.txt
```

Before that commit, stage every fixture file individually. There are 16 files under `tests/replay/histories/` and 16 under `tests/replay/golden/`. List them with `git status --short tests/replay`, then run one `git add tests/replay/histories/<scenario>.json` and one `git add tests/replay/golden/<scenario>.json` per scenario.

### Task 2: Replayer proof over the captured histories (fast tier) + grace-edit rule

**Files:**
- Create: `tests/replay/test_feature_replay.py`
- Modify: `src/sdlc/workflows/AGENTS.md` (append the grace-edit rule)

**Interfaces:**
- Consumes: `harness.load_history(name)`, `scenarios.SCENARIOS` (Task 1).
- Produces: `tests/replay/test_feature_replay.py::replayer()`, the configured `Replayer` reused by Task 22.

- [ ] **Step 1: Write the test**

```python
"""U2 proof: FeatureWorkflow replays every history captured from pre-change code.

Stop-guard SG-2: red after a src/ change means that change altered
FeatureWorkflow's command sequence. Never re-record a history to turn this
green (U6 grace-edit rule, workflows/AGENTS.md).
"""

from __future__ import annotations

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from pydantic_ai.exceptions import AgentRunError, UserError
from pydantic import PydanticUserError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Replayer
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

from sdlc.workflows.crew import CrewTaskWorkflow
from sdlc.workflows.deployment import DeploymentWorkflow
from sdlc.workflows.feature import FeatureWorkflow
from tests.replay.harness import load_history
from tests.replay.scenarios import SCENARIOS


def replayer(*workflows: type) -> Replayer:
    return Replayer(
        workflows=list(workflows) or [FeatureWorkflow, DeploymentWorkflow, CrewTaskWorkflow],
        data_converter=pydantic_data_converter,
        plugins=[PydanticAIPlugin()],
    )


def test_replayer_matches_the_production_worker_effect():
    config = replayer().config(active_config=True)
    runner = config["workflow_runner"]
    assert isinstance(runner, SandboxedWorkflowRunner)
    assert "pydantic_ai" in runner.restrictions.passthrough_modules
    assert {UserError, PydanticUserError, AgentRunError} <= set(
        config["workflow_failure_exception_types"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
async def test_feature_workflow_replays_captured_history(scenario):
    result = await replayer().replay_workflow(
        load_history(scenario.name), raise_on_replay_failure=True
    )
    assert result.replay_failure is None
```


- [ ] **Step 2: Run the test to get the baseline**

Run: `pytest tests/replay/test_feature_replay.py -q`
Expected: PASS (17 passed). There is nothing to fail yet: this task pins the baseline the refactors in Tasks 3–6 must keep green. A red result here, before any `src/` change, is SG-2.

- [ ] **Step 3: Record the grace-edit rule in `src/sdlc/workflows/AGENTS.md`**

Append at the end of the file:

```markdown

## Grace edits while FeatureWorkflow is registered (E-74 U6)

`FeatureWorkflow` stays registered only to carry in-flight runs to terminal
state (PRD OQ-10 grace-retention). Until it is deleted, any edit that changes
the COMMAND SEQUENCE of code it executes (stage steps, hosts, `build.run_tasks`,
`run_host.py`) must be wrapped in `workflow.patched("<epic>-<slug>")`.
`tests/replay/test_feature_replay.py` is the enforcement: its histories are
never re-recorded to make an edit pass. After deletion, intentional golden
changes re-baseline from GraphWorkflow with the projection diff attached to
the review.
```

- [ ] **Step 4: Run gates**

Run: `ruff check .` then `ruff format --check .` then `mypy` then `python scripts/check_file_size.py` (separate invocations).
Expected: all clean.

- [ ] **Step 5: Commit**

Message file `.workspace/tmp/e74-t2-msg.txt`:

```text
test(replay): E-74 Replayer proof over captured FeatureWorkflow histories

Fast-tier replay of every Task 1 history under the worker's own sandboxed
runner and plugin failure types; records the U6 grace-edit rule.
```

```bash
git add tests/replay/test_feature_replay.py
git add src/sdlc/workflows/AGENTS.md
git commit -F .workspace/tmp/e74-t2-msg.txt
```

### Task 3: Extract the `RunHost` mixin (gate hooks, run-state snapshot, retro)

**Files:**
- Create: `src/sdlc/workflows/run_host.py`
- Modify: `src/sdlc/workflows/feature.py` (bases, `__init__`, delete hooks `:230-277`, `run_state` body `:286-314`, delete `_retro` `:425-450`)
- Modify: `src/sdlc/workflows/AGENTS.md` (ownership rows)
- Test: `tests/test_run_host.py`

**Interfaces:**
- Produces: `RunHost` with `_on_gate_awaited(name, round)`, `_on_gate_decided(name, round, policy, decision, confidence=None, author_model=None)`, `_on_notified(gate, reason, notifier, delivered, error="")`, `_snapshot_run_state() -> RunState | None`, `async _retro(cfg, idea, result) -> None`. It owns `_cfg`, `_idea`, `_started_at`, `_run_id`, `_run_summary`. GraphWorkflow (Task 19) composes `RunHost` first.

- [ ] **Step 1: Write the failing test `tests/test_run_host.py`**

```python
"""E-74 §4.3: RunHost carries what FeatureWorkflow and GraphWorkflow share."""

from __future__ import annotations

from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.gates import GateHost
from sdlc.workflows.run_host import RunHost

_MOVED = ("_on_gate_awaited", "_on_gate_decided", "_on_notified", "_retro", "_snapshot_run_state")


def test_feature_workflow_composes_run_host_before_gate_host():
    mro = FeatureWorkflow.__mro__
    assert mro.index(RunHost) < mro.index(GateHost)


def test_moved_members_resolve_to_run_host():
    for name in _MOVED:
        assert getattr(FeatureWorkflow, name) is getattr(RunHost, name), name
        assert name not in vars(FeatureWorkflow), name


def test_run_host_declares_no_workflow_handlers():
    # workflows/AGENTS.md rule 4: handlers live on the concrete class or GateHost.
    for name, member in vars(RunHost).items():
        assert not hasattr(member, "__temporal_query_definition"), name
        assert not hasattr(member, "__temporal_signal_definition"), name


def test_run_state_query_delegates_to_the_snapshot():
    wf = FeatureWorkflow()
    assert wf.run_state() is None  # no brief stashed yet
    assert wf._run_id == "" and wf._run_summary is None
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/test_run_host.py -q`
Expected: FAIL. `ModuleNotFoundError: No module named 'sdlc.workflows.run_host'`.

- [ ] **Step 3: Create `src/sdlc/workflows/run_host.py` (bodies moved verbatim)**

```python
"""RunHost -- what every pipeline-run workflow shares (E-74 spec §4.3).

A mixin, following GateHost (workflows/gates.py:54). FeatureWorkflow and
GraphWorkflow list it BEFORE GateHost so its gate hooks override GateHost's
no-ops. Bodies are moved verbatim from FeatureWorkflow; the run_state and
run_summary queries stay on each concrete class as one-line delegates
(workflows/AGENTS.md rule 4 -- the dashboard queries by name).

Owns: _cfg, _idea, _started_at, _run_id, _run_summary.
Consumes via the MRO: ReportHost (_emit, _trace, _status, _role_usage),
GateHost (_gate_decisions), RoleHost (_budget_crossings), MemoryHost
(_retain, _memory_watermark), TaskHost (_session_refs).
"""

from __future__ import annotations

from datetime import datetime

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..core.models import (
        GateDecision,
        GatePolicy,
        IdeaBrief,
        PipelineConfig,
        RunState,
        RunSummary,
    )
    from ..memory.models import MemoryKind
    from ..notify.contract import NotifyReason
    from ..observability.summary import build_run_summary
    from ..observability.trace import RunEventKind
    from ..stages import retro


class RunHost:
    """Mixin. Subclasses must call super().__init__()."""

    def __init__(self) -> None:
        super().__init__()
        # Stashed state for hooks/queries (E-42, E-10, ADR-14, E-84). _run_id: run_state()
        # is unit-tested on bare instances (no event loop); "" sentinels: no reader before setup.
        self._cfg: PipelineConfig | None = None
        self._idea: IdeaBrief | None = None
        self._started_at: datetime | None = None
        self._run_id: str = ""
        self._run_summary: RunSummary | None = None
```

Then move, byte for byte, these members from `feature.py` into `RunHost`, keeping their bodies and docstrings:
- `_on_gate_awaited` (`feature.py:230-231`)
- `_on_gate_decided` (`:233-264`)
- `_on_notified` (`:266-277`)
- `_retro` (`:425-450`)

Add the run-state body as a plain method. It is the body of `feature.py:293-314`, with the docstring kept:

```python
    def _snapshot_run_state(self) -> RunState | None:
        """Live run state for the dashboard fleet view (E-10).

        None until run() stashes the brief. Every field is read from state
        the run already holds -- this query adds no bookkeeping.
        """
        if self._idea is None or self._started_at is None:
            return None
        priced = [u.cost_usd for u in self._role_usage.values() if u.cost_usd is not None]  # type: ignore[attr-defined]
        budget = self._cfg.run_budget_usd if self._cfg and self._cfg.run_budget_usd > 0 else None
        stage = next(
            (e.stage for e in reversed(self._trace) if e.kind is RunEventKind.STAGE_STARTED),  # type: ignore[attr-defined]
            None,
        )
        return RunState(
            run_id=self._run_id,
            title=self._idea.title,
            repo_url=self._idea.repo_url,
            mode=self._idea.mode.value,
            status=self._status,  # type: ignore[attr-defined]
            current_stage=stage,
            started_at=self._started_at,
            decisions=list(self._gate_decisions.values()),  # type: ignore[attr-defined]
            roles=list(self._role_usage.values()),  # type: ignore[attr-defined]
            # None, not 0.0: a pricing miss must never read as a free run.
            cost_usd_total=sum(priced) if priced else None,
            budget_usd=budget,
            budget_crossings=self._budget_crossings,  # type: ignore[attr-defined]
        )
```

In the moved bodies, add `# type: ignore[attr-defined]` only where mypy reports a mixin attribute. Use the same idiom `role_host.py:153` already uses.

- [ ] **Step 4: Rewire `src/sdlc/workflows/feature.py`**

1. In the `imports_passed_through()` block add `from .run_host import RunHost`.
2. Class header becomes:

```python
@workflow.defn
class FeatureWorkflow(
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
```

3. In `__init__`, delete these five assignments; `RunHost.__init__` now makes them:
   - `self._cfg = None`
   - `self._idea = None`
   - `self._started_at = None`
   - `self._run_id = ""`
   - `self._run_summary = None`

   Keep the integration, `_base_sha`, `_integration_wt`, `_codebase_map` and `_ctx` lines, plus the leading comment line.
4. Delete the three hook methods and `_retro`.
5. Replace the `run_state` query body so the query reads:

```python
    @workflow.query
    def run_state(self) -> RunState | None:
        """Live run state for the dashboard fleet view (E-10)."""
        return self._snapshot_run_state()
```

6. Run `ruff check src/sdlc/workflows/feature.py`. Remove exactly the imports it reports as unused (F401) and nothing else.

- [ ] **Step 5: Update the ownership table in `src/sdlc/workflows/AGENTS.md`**

For the rows `_cfg`, `_idea`, `_started_at`, `_run_id`, `_run_summary`, set **Owning Host** to `RunHost`. Replace `FeatureWorkflow.run_state` / `FeatureWorkflow.run_summary` / `FeatureWorkflow (retro)` in the Readers column with `RunHost._snapshot_run_state` / `RunHost._retro` respectively. Leave every other row unchanged.

- [ ] **Step 6: Run the tests, the Replayer proof and the fast tier**

Run: `pytest tests/test_run_host.py -q`
Expected: PASS (4 passed).

Run: `pytest tests/replay/test_feature_replay.py -q`
Expected: PASS (17 passed). A red result here is SG-2.

Run: `pytest -q`
Expected: the fast tier is green. Any failure is SG-5.

- [ ] **Step 7: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t3-msg.txt`:

```text
refactor(workflows): E-74 extract RunHost from FeatureWorkflow

Gate hooks, the run-state snapshot and retro move verbatim into a RunHost
mixin listed before GateHost; queries stay on the concrete class as
delegates. Replayer proof green over every captured history.
```

```bash
git add src/sdlc/workflows/run_host.py
git add src/sdlc/workflows/feature.py
git add src/sdlc/workflows/AGENTS.md
git add tests/test_run_host.py
git commit -F .workspace/tmp/e74-t3-msg.txt
```

### Task 4: Extract `build.run_tasks` and `validate_task_graph`

**Files:**
- Create: `src/sdlc/workflows/build.py`
- Create: `src/sdlc/stages/plan/validation.py`
- Modify: `src/sdlc/workflows/feature.py` (`_validate_task_graph` `:149-189` → import alias; `_build_and_merge` `:635-716` → `run_tasks` call)
- Test: `tests/test_build_run_tasks.py`, `tests/plan/test_plan_validation_module.py`

**Interfaces:**
- Produces:
  - `async run_tasks(host, *, cfg: PipelineConfig, plan: ImplementationPlan, repo_path: str) -> tuple[dict[str, TaskResult], str | None]`
    - `(done, None)` on success, `done` in completion order.
    - `(done_so_far, failure)` where `failure` ∈ {`failed:dependency-cycle`, `failed:integration-conflict:<task>`, `failed:quarantined-tasks`}.
    - `_BudgetRejected` propagates.
  - `validate_task_graph(tasks: list[DevTask]) -> str | None`.
- The host must provide `_board_task_status`, `_dev_task`, `_board_evidence`, `_merge_task`, `_check_budget`, `_integration_head`.

- [ ] **Step 1: Write the failing tests**

`tests/plan/test_plan_validation_module.py`:

```python
from __future__ import annotations

from sdlc.stages.plan.models import DevTask
from sdlc.stages.plan.validation import validate_task_graph
from sdlc.workflows.feature import _validate_task_graph


def _task(tid: str, deps: list[str] | None = None) -> DevTask:
    return DevTask(id=tid, title=tid, description=tid, acceptance_criteria=["ok"], depends_on=deps or [])


def test_feature_alias_is_the_moved_function():
    assert _validate_task_graph is validate_task_graph


def test_cycle_and_dangling_reference_reasons_unchanged():
    assert validate_task_graph([_task("A", ["B"]), _task("B", ["A"])]) == "dependency cycle: A -> B -> A"
    assert validate_task_graph([_task("A", ["Z"])]) == "task 'A' depends on unknown task id(s) ['Z']"
```

`tests/test_build_run_tasks.py`:

```python
"""E-74 §4.3: the task scheduler moved verbatim into build.run_tasks."""

from __future__ import annotations

import asyncio

from sdlc.core.models import ExecutionMode, PipelineConfig
from sdlc.stages.plan.models import DevTask, ImplementationPlan
from sdlc.workflows.build import run_tasks
from sdlc.workflows.models import TaskResult


def _task(tid: str, deps: list[str] | None = None, overlaps: list[str] | None = None) -> DevTask:
    return DevTask(
        id=tid, title=tid, description=tid, acceptance_criteria=["ok"],
        depends_on=deps or [], overlaps=overlaps or [],
    )


class FakeHost:
    def __init__(self, statuses: dict[str, str] | None = None, conflict_on: str | None = None):
        self._integration_head = "h0"
        self.statuses = statuses or {}
        self.conflict_on = conflict_on
        self.calls: list[tuple[str, ...]] = []

    async def _board_task_status(self, cfg, tid, status, **kw):
        self.calls.append(("status", tid, status.value))

    async def _dev_task(self, task, repo_path, from_ref, cfg, handoffs):
        self.calls.append(("dev", task.id, from_ref))
        return TaskResult(task_id=task.id, status=self.statuses.get(task.id, "done"), attempts=1, branch=f"b/{task.id}")

    async def _board_evidence(self, cfg, tid, kind, report_json):
        self.calls.append(("evidence", tid, kind))

    async def _merge_task(self, tr, repo_path):
        self.calls.append(("merge", tr.task_id))
        if tr.task_id == self.conflict_on:
            return f"failed:integration-conflict:{tr.task_id}"
        self._integration_head = f"h-{tr.task_id}"
        return None

    async def _check_budget(self, cfg):
        self.calls.append(("budget",))


def _run(host: FakeHost, tasks: list[DevTask], mode: ExecutionMode = ExecutionMode.SERIAL):
    cfg = PipelineConfig(execution_mode=mode)
    return asyncio.run(run_tasks(host, cfg=cfg, plan=ImplementationPlan(tasks=tasks), repo_path="/r"))


def test_serial_success_branches_each_task_from_the_advanced_head():
    host = FakeHost()
    done, failure = _run(host, [_task("t1"), _task("t2", ["t1"])])
    assert failure is None
    assert list(done) == ["t1", "t2"]
    assert ("dev", "t2", "h-t1") in host.calls
    assert host.calls.count(("budget",)) == 2


def test_dependency_cycle_is_returned_not_raised():
    done, failure = _run(FakeHost(), [_task("a", ["b"]), _task("b", ["a"])])
    assert (done, failure) == ({}, "failed:dependency-cycle")


def test_integration_conflict_stops_the_loop():
    done, failure = _run(FakeHost(conflict_on="t1"), [_task("t1"), _task("t2")])
    assert failure == "failed:integration-conflict:t1"
    assert list(done) == ["t1"]


def test_quarantined_task_fails_the_run_after_its_wave():
    done, failure = _run(FakeHost(statuses={"t1": "quarantined"}), [_task("t1"), _task("t2")])
    assert failure == "failed:quarantined-tasks"
    assert list(done) == ["t1"]


def test_waves_serialize_tasks_that_share_an_overlap():
    host = FakeHost()
    done, failure = _run(
        host, [_task("t1", overlaps=["m"]), _task("t2", overlaps=["m"]), _task("t3")], ExecutionMode.WAVES
    )
    assert failure is None
    devs = [c[1] for c in host.calls if c[0] == "dev"]
    assert devs == ["t1", "t3", "t2"]
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_build_run_tasks.py tests/plan/test_plan_validation_module.py -q`
Expected: FAIL. `ModuleNotFoundError` for `sdlc.workflows.build` and `sdlc.stages.plan.validation`.

- [ ] **Step 3: Create `src/sdlc/stages/plan/validation.py`**

The module docstring is `"""Plan-graph validation: pure, workflow-safe (moved from workflows/feature.py by E-74)."""`. Then `from __future__ import annotations`, `from .models import DevTask`, and the function body of `feature.py:149-189` renamed `validate_task_graph`, docstring and body verbatim.

- [ ] **Step 4: Create `src/sdlc/workflows/build.py`**

```python
"""Stage 4 task scheduler, shared by FeatureWorkflow and the graph `code` node
(E-74 spec §4.3). Moved verbatim from feature.py's _build_and_merge; the host
supplies the TaskHost/BoardHost/RoleHost capabilities.

Determinism: task dicts are insertion-ordered and keyed by task id, and the
wave gather runs over the batch in plan order. Both orderings are replay-safe
and must never be "fixed" by sorting (that changes FeatureWorkflow's command
sequence and fails tests/replay/test_feature_replay.py).
"""

from __future__ import annotations

import asyncio
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..board.models import TaskStatus
    from ..core.models import ExecutionMode, PipelineConfig
    from ..stages.plan.models import DevTask, ImplementationPlan
    from .models import TaskResult


async def run_tasks(
    host: Any, *, cfg: PipelineConfig, plan: ImplementationPlan, repo_path: str
) -> tuple[dict[str, TaskResult], str | None]:
    """4. DEV / TEST / DEVOPS tasks -- ADR-13: serial by default; wave mode
    parallelizes, but tasks sharing declared overlaps serialize regardless.
    Handoffs flow task -> task (FR-805). Returns (done, None) or
    (done_so_far, terminal failure string)."""
    done: dict[str, TaskResult] = {}
    handoffs: list = []
    remaining = {t.id: t for t in plan.tasks}

    async def run_one(t: DevTask) -> TaskResult:
        """Execute the task only. Merging is a separate concern -- see
        _merge_task (Resolution B: merging inside run_one would race
        the integration worktree under wave mode's asyncio.gather)."""
        await host._board_task_status(cfg, t.id, TaskStatus.IN_PROGRESS)
        try:
            r = await host._dev_task(t, repo_path, host._integration_head, cfg, handoffs)
        except Exception as exc:
            # _dev_task's own fix loop is exhausted before it raises, so a
            # propagating exception means the run is aborting. Record a
            # terminal status so the board (which agents read for live
            # state) does not leave this task looking forever in_progress
            # -- indistinguishable from a task still running.
            await host._board_task_status(
                cfg, t.id, TaskStatus.FAILED, error=f"unhandled: {type(exc).__name__}: {exc}"
            )
            raise
        _BOARD_STATUS = {
            "done": TaskStatus.DONE,
            "failed": TaskStatus.FAILED,
            "quarantined": TaskStatus.QUARANTINED,
        }
        await host._board_task_status(
            cfg,
            t.id,
            _BOARD_STATUS[r.status],
            fix_attempts=r.attempts,
            branch=r.branch,
            error=(r.notes or None if r.status != "done" else None),
        )
        for kind, report in (
            ("qa", r.qa),
            ("review", r.review),
            ("deep_review", r.deep_review),
        ):
            if report is not None:
                await host._board_evidence(cfg, t.id, kind, report.model_dump_json())
        done[r.task_id] = r
        if r.handoff:
            handoffs.append(r.handoff)
        remaining.pop(r.task_id)
        return r

    while remaining:
        ready = [t for t in remaining.values() if all(d in done for d in t.depends_on)]  # determinism: insertion-ordered task dict
        if not ready:
            return done, "failed:dependency-cycle"

        if cfg.execution_mode == ExecutionMode.SERIAL:
            # SERIAL: execute + merge sequentially so the next task
            # branches from the updated integration head.
            tr = await run_one(ready[0])
            if tr.status == "done":
                conflict = await host._merge_task(tr, repo_path)
                if conflict:
                    return done, conflict
        else:
            # Wave mode: execute the batch in parallel (preserving the
            # gather), THEN merge results sequentially so integration
            # updates are ordered -- two tasks racing the integration
            # worktree would corrupt the merge (Resolution B).
            batch: list[DevTask] = []
            seen: set[str] = set()
            for t in ready:
                if seen.isdisjoint(t.overlaps):
                    batch.append(t)
                    seen.update(t.overlaps)
            results = await asyncio.gather(*[run_one(t) for t in batch])  # determinism: wave batch order
            for tr in results:
                if tr.status == "done":
                    conflict = await host._merge_task(tr, repo_path)
                    if conflict:
                        return done, conflict

        if any(r.status == "quarantined" for r in done.values()):  # determinism: insertion-ordered task dict
            return done, "failed:quarantined-tasks"

        await host._check_budget(cfg)  # E-33: serial boundary per task wave

    return done, None
```

- [ ] **Step 5: Rewire `feature.py`**

1. In the passthrough block add:
   - `from ..stages.plan.validation import validate_task_graph as _validate_task_graph`
   - `from .build import run_tasks`

   Then delete the `_validate_task_graph` function (`:149-189`).
2. In `_build_and_merge`, replace everything from `done: dict[str, TaskResult] = {}` through the end of the `while remaining:` loop (`:635-716`, ending at `await self._check_budget(cfg)  # E-33: serial boundary per task wave`) with:

```python
        done, failure = await run_tasks(self, cfg=cfg, plan=plan, repo_path=repo_path)
        if failure is not None:
            return failure
```

Keep the `# 4. DEV / TEST / DEVOPS` comment above it. The analyze section that follows reads `done` exactly as before.

3. Run `ruff check src/sdlc/workflows/feature.py` and remove only the imports it reports unused (F401).

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_build_run_tasks.py tests/plan/test_plan_validation_module.py tests/plan/test_plan_graph_validation.py -q`
Expected: PASS.

Run: `pytest tests/replay/test_feature_replay.py -q`
Expected: PASS (17). A red result is SG-2.

Run: `pytest -q`
Expected: green. A failure is SG-5.

- [ ] **Step 7: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t4-msg.txt`:

```text
refactor(workflows): E-74 extract task scheduler and plan-graph validation

build.run_tasks returns (done, failure) with today's three terminal strings;
validate_task_graph moves to stages/plan/validation.py behind the old alias.
Replayer proof green.
```

```bash
git add src/sdlc/workflows/build.py
git add src/sdlc/stages/plan/validation.py
git add src/sdlc/workflows/feature.py
git add tests/test_build_run_tasks.py
git add tests/plan/test_plan_validation_module.py
git commit -F .workspace/tmp/e74-t4-msg.txt
```

### Task 5: Split `architecture.step` into `prepare` / `produce` / `finish`

**Files:**
- Modify: `src/sdlc/stages/architecture/step.py:64-226`
- Modify: `src/sdlc/stages/architecture/architecture.md` (new clause ARCH-1.4)
- Test: `tests/architecture/test_architecture_step_split.py`

**Interfaces:**
- Produces:
  - `ArchitecturePrep` (dataclass): `started: datetime`, `resolved_model: str`, `spend: RoleUsage`, `mode_val: str`, `snapshot: Any`, `map_block: str`, `map_key: str`, `salt: str`.
  - `async prepare(ctx, *, cfg, codebase_map=None, idea=None, architect_model=None) -> ArchitecturePrep`
  - `async produce(ctx, prep, *, cfg, requirements, codebase_map=None, memory_watermark=None, repo_path="/var/sdlc/repo", architect_agent=None, guidance=None) -> ArchitectureSpec`
  - `async finish(ctx, prep, *, cfg, artifact: ArchitectureSpec, gate: GateDecision) -> None`
  - `step()` keeps its signature and return value.

- [ ] **Step 1: Write the failing characterization test**

```python
"""E-74 §4.3: architecture.step == prepare + revisable(produce) + finish, with the
same service-call sequence; once-per-stage work happens once across rounds."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sdlc.core.models import GateDecision, GateOutcome, PipelineConfig

# Import names from the SUBMODULE: the package's `step` attribute is the
# shadow-proofed step FUNCTION (_StageModule), never the module.
from sdlc.stages.architecture.step import finish, prepare, produce, step
from tests.fakes.canned import ARCH, CLARIFIED, greenfield_idea


class Ctx:
    def __init__(self, rounds: int = 2):
        self.calls: list[str] = []
        self.rounds = rounds

    def stage(self, status, trace=None):
        self.calls.append(f"stage:{trace}")

    def emit(self, *a, **k):
        self.calls.append("emit")

    async def recall(self, cfg, bank, query, filters):
        self.calls.append("recall")
        return SimpleNamespace(items=[])

    async def run_role(self, cfg, role, model, agent, prompt, **kw):
        self.calls.append(f"run_role:{'guided' if 'Revision guidance' in prompt else 'plain'}")
        return SimpleNamespace(output=ARCH)

    async def cached_stage(self, cfg, stage, input_json, output_type, run_fn, *, prompt_digest=""):
        self.calls.append(f"cached:{stage}")
        return await run_fn(), False

    async def revisable_stage(self, name, cfg, run_fn, *, author_model=""):
        guidance = None
        for _ in range(self.rounds):
            artifact = await run_fn(guidance)
            guidance = "again"
        self.calls.append(f"gate:{name}")
        return artifact, GateDecision(gate=name, outcome=GateOutcome.APPROVE, decided_by="human")

    async def judge(self, cfg, artifact_json, stage, author_model):
        self.calls.append("judge")
        return SimpleNamespace(score=None, judge="none")

    async def record(self, cfg, record):
        self.calls.append("record")

    async def retain(self, cfg, kind, bank, text, metadata):
        self.calls.append("retain")


EXPECTED = [
    "stage:architecture", "recall",
    "cached:architect", "run_role:plain",
    "cached:architect", "run_role:guided",
    "gate:architecture", "judge", "record", "retain",
]


def test_step_call_sequence_is_unchanged():
    ctx = Ctx()
    asyncio.run(step(
        ctx, cfg=PipelineConfig(), requirements=CLARIFIED, idea=greenfield_idea(),
        architect_agent=object(), architect_model="m-arch",
    ))
    assert ctx.calls == EXPECTED


def test_prepare_produce_finish_compose_to_the_same_sequence():
    ctx = Ctx()
    cfg = PipelineConfig()

    async def go():
        prep = await prepare(ctx, cfg=cfg, idea=greenfield_idea(), architect_model="m-arch")
        a1 = await produce(ctx, prep, cfg=cfg, requirements=CLARIFIED, architect_agent=object(), guidance=None)
        a2 = await produce(ctx, prep, cfg=cfg, requirements=CLARIFIED, architect_agent=object(), guidance="again")
        ctx.calls.append("gate:architecture")
        await finish(ctx, prep, cfg=cfg, artifact=a2,
                     gate=GateDecision(gate="architecture", outcome=GateOutcome.APPROVE, decided_by="human"))
        return prep, a1

    prep, _ = asyncio.run(go())
    assert ctx.calls == EXPECTED
    assert prep.resolved_model == "m-arch"
    assert prep.spend.role == "architect"
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/architecture/test_architecture_step_split.py -q`
Expected: FAIL. `ImportError: cannot import name 'finish'`.

- [ ] **Step 3: Rewrite `step()` as three functions plus a composer**

Keep the module header, imports, `_INTAKE_ACT`, `_now`, `_workflow_id` and `_requirements_for_downstream` unchanged. Add `from dataclasses import dataclass` to the stdlib imports. Replace `async def step(...)` (`:64-226`) with:

```python
@dataclass
class ArchitecturePrep:
    """The once-per-stage prefix of the architecture stage (E-74 §4.3)."""

    started: datetime
    resolved_model: str
    spend: RoleUsage
    mode_val: str
    snapshot: Any
    map_block: str
    map_key: str
    salt: str


async def prepare(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    codebase_map: CodebaseMap | None = None,
    idea: IdeaBrief | None = None,
    architect_model: str | None = None,
) -> ArchitecturePrep:
    ctx.stage("architecting", "architecture")
    started = _now()
    arch_role = cfg.roles.get("architect")
    resolved_model = (
        architect_model
        or (arch_role.model if arch_role and arch_role.model else None)
        or "claude-3-5-sonnet"
    )
    spend = RoleUsage(role="architect", model=resolved_model)

    title = idea.title if idea else "feature"
    mode_val = idea.mode.value if idea and idea.mode else "greenfield"

    snapshot = await ctx.recall(
        cfg,
        cfg.memory.project_bank,
        query=f"architect:{title}",
        filters={"stage": "architect"},
    )

    map_block = ""
    map_key = ""
    if codebase_map is not None:
        rendered_map = render_for_prompt(codebase_map)
        map_key = map_digest(codebase_map)
        map_block = f"\n\nCodebase map at commit {codebase_map.commit_sha[:12]}:\n{rendered_map}"

    return ArchitecturePrep(
        started=started,
        resolved_model=resolved_model,
        spend=spend,
        mode_val=mode_val,
        snapshot=snapshot,
        map_block=map_block,
        map_key=map_key,
        salt=prompt_digest(cfg),
    )


async def produce(
    ctx: StageContext,
    prep: ArchitecturePrep,
    *,
    cfg: PipelineConfig,
    requirements: ClarifiedRequirements,
    codebase_map: CodebaseMap | None = None,
    memory_watermark: str | None = None,
    repo_path: str = "/var/sdlc/repo",
    architect_agent: Any = None,
    guidance: str | None = None,
) -> ArchitectureSpec:
    """One architect round (delta retries included). Verbatim body of the
    former `_run_architect(guidance)` closure."""
    from ..research.deps import ResearchDeps

    research_role = cfg.roles.get("research") if cfg.research_enabled else None
    architect_deps = ResearchDeps(
        run_id=_workflow_id(),
        provider=(research_role.provider or "fake") if research_role else "fake",
        max_searches=cfg.research.max_searches,
        max_fetches=cfg.research.max_fetches,
        max_cost_usd=cfg.research.max_cost_usd,
        memory_backend=cfg.memory.backend,
        memory_base_url=cfg.memory.base_url,
        memory_bank=cfg.memory.project_bank,
        memory_watermark=memory_watermark,
        scope="architect",
    )

    delta_retries = cfg.max_delta_retries
    delta_guidance: str | None = None
    reqs_for_architect = _requirements_for_downstream(requirements)
    snapshot = prep.snapshot
    while True:
        prompt = (
            f"mode={prep.mode_val}\n{reqs_for_architect}"
            + (prep.map_block if codebase_map is not None else "")
            + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items) if snapshot.items else "")
            + (f"\nRevision guidance from reviewer:\n{guidance}" if guidance else "")
            + (f"\nDelta correction required:\n{delta_guidance}" if delta_guidance else "")
        )

        async def _produce(prompt: str = prompt) -> ArchitectureSpec:
            res = await ctx.run_role(
                cfg,
                "architect",
                prep.resolved_model,
                architect_agent,
                prompt,
                deps=architect_deps,
                into=prep.spend,
            )
            return res.output

        cache_key = (
            reqs_for_architect
            + (guidance or "")
            + (prep.map_key if codebase_map is not None else "")
            + (delta_guidance or "")
        )
        arch, _ = await ctx.cached_stage(
            cfg, "architect", cache_key, ArchitectureSpec, _produce, prompt_digest=prep.salt
        )

        if codebase_map is None:
            return arch

        delta_check = await workflow.execute_activity(
            check_brownfield_delta,
            DeltaCheckInput(
                repo_dir=repo_path,
                commit_sha=codebase_map.commit_sha,
                delta=arch.delta,
            ),
            **_INTAKE_ACT,
        )
        if delta_check.passed:
            return arch

        if delta_retries <= 0:
            raise ApplicationError(
                f"brownfield architecture delta failed grounding check "
                f"after retries: {delta_check.detail}",
                non_retryable=True,
            )
        delta_retries -= 1
        delta_guidance = (
            f"The proposed delta does not match the repository at "
            f"{codebase_map.commit_sha[:12]}: "
            f"{delta_check.detail}. Update delta.added, delta.modified, "
            f"and delta.removed so every path resolves."
        )


async def finish(
    ctx: StageContext,
    prep: ArchitecturePrep,
    *,
    cfg: PipelineConfig,
    artifact: ArchitectureSpec,
    gate: GateDecision,
) -> None:
    """Post-gate work: judge, record PASS|REVISED, retain."""
    from ...benchmarks.models import BenchmarkOutcome
    from ...benchmarks.record_builder import stage_record

    _ended = _now()
    _quality = await ctx.judge(
        cfg,
        artifact.model_dump_json(),
        "architect",
        author_model=prep.resolved_model,
    )
    await ctx.record(
        cfg,
        stage_record(
            cfg,
            stage="architecture",
            role="architect",
            started=prep.started,
            ended=_ended,
            quality_score=_quality.score,
            judge=_quality.judge,
            outcome=(BenchmarkOutcome.PASS if gate.approved else BenchmarkOutcome.REVISED),
            model=prep.resolved_model,
            spend=prep.spend,
        ),
    )
    await ctx.retain(
        cfg,
        MemoryKind.STAGE_SUMMARY,
        cfg.memory.project_bank,
        text=f"architect: {artifact.overview}",
        metadata={"stage": "architect", "run_id": _workflow_id()},
    )


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    requirements: ClarifiedRequirements,
    codebase_map: CodebaseMap | None = None,
    memory_watermark: str | None = None,
    idea: IdeaBrief | None = None,
    repo_path: str = "/var/sdlc/repo",
    architect_agent: Any = None,
    architect_model: str | None = None,
) -> tuple[ArchitectureSpec, GateDecision]:
    """Execute the architecture stage: prepare, the revisable produce loop,
    finish. Returns (ArchitectureSpec, GateDecision)."""
    prep = await prepare(
        ctx, cfg=cfg, codebase_map=codebase_map, idea=idea, architect_model=architect_model
    )

    async def _run_architect(guidance: str | None) -> ArchitectureSpec:
        return await produce(
            ctx,
            prep,
            cfg=cfg,
            requirements=requirements,
            codebase_map=codebase_map,
            memory_watermark=memory_watermark,
            repo_path=repo_path,
            architect_agent=architect_agent,
            guidance=guidance,
        )

    arch, gate = await ctx.revisable_stage(
        "architecture", cfg, _run_architect, author_model=prep.resolved_model
    )
    await finish(ctx, prep, cfg=cfg, artifact=arch, gate=gate)
    return arch, gate
```

- [ ] **Step 4: Add clause ARCH-1.4 to `architecture.md`**

Insert after the `### ARCH-1.3` paragraph:

```markdown
### ARCH-1.4
The step is composed of `prepare` (the once-per-stage prefix: stage event, start time, role usage, memory recall, map grounding, prompt salt), `produce` (one architect round including delta retries, keyed by the unchanged memo input) and `finish` (judge, benchmark record, memory retain). `step` composes them around `revisable_stage` for FeatureWorkflow; GraphWorkflow calls them across the `architect` and `gate.architecture` nodes. [E-74 spec §4.3, §6.1]
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/architecture -q`
Expected: PASS, including `test_architecture_step_split.py` (2 passed) and the existing slice-contract tests.

Run: `pytest tests/replay/test_feature_replay.py -q`
Expected: PASS (17). A red result is SG-2.

Run: `pytest -q`
Expected: green. A failure is SG-5.

- [ ] **Step 6: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t5-msg.txt`:

```text
refactor(architecture): E-74 split step into prepare, produce, finish

step() composes the three around revisable_stage with an unchanged call
sequence (characterization test) and unchanged commands (Replayer proof),
so the graph path can run them across the architect and gate nodes.
```

```bash
git add src/sdlc/stages/architecture/step.py
git add src/sdlc/stages/architecture/architecture.md
git add tests/architecture/test_architecture_step_split.py
git commit -F .workspace/tmp/e74-t5-msg.txt
```

### Task 6: Split `plan.step` into `prepare` / `produce` / `finish`

**Files:**
- Modify: `src/sdlc/stages/plan/step.py:51-144`
- Modify: `src/sdlc/stages/plan/plan.md` (new clause PLAN-1.4)
- Test: `tests/plan/test_plan_step_split.py`

**Interfaces:**
- Produces:
  - `PlanPrep` (dataclass): `started`, `resolved_model`, `spend`, `snapshot`, `salt`.
  - `async prepare(ctx, *, cfg, idea=None, planner_model=None) -> PlanPrep`
  - `async produce(ctx, prep, *, cfg, architecture, requirements=None, planner_agent=None, guidance=None) -> ImplementationPlan`
  - `async finish(ctx, prep, *, cfg, artifact: ImplementationPlan, gate: GateDecision) -> None`

- [ ] **Step 1: Write the failing characterization test `tests/plan/test_plan_step_split.py`**

```python
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sdlc.core.models import GateDecision, GateOutcome, PipelineConfig
from sdlc.stages.plan.step import finish, prepare, produce, step
from tests.fakes.canned import ARCH, PLAN, greenfield_idea


class Ctx:
    def __init__(self):
        self.calls: list[str] = []

    def stage(self, status, trace=None):
        self.calls.append(f"stage:{trace}")

    async def recall(self, cfg, bank, query, filters):
        self.calls.append("recall")
        return SimpleNamespace(items=[])

    async def run_role(self, cfg, role, model, agent, prompt, **kw):
        self.calls.append("run_role")
        return SimpleNamespace(output=PLAN)

    async def cached_stage(self, cfg, stage, input_json, output_type, run_fn, *, prompt_digest=""):
        self.calls.append(f"cached:{stage}:{'guided' if input_json.endswith('again') else 'plain'}")
        return await run_fn(), False

    async def revisable_stage(self, name, cfg, run_fn, *, author_model=""):
        await run_fn(None)
        artifact = await run_fn("again")
        self.calls.append(f"gate:{name}")
        return artifact, GateDecision(gate=name, outcome=GateOutcome.APPROVE, decided_by="human")

    async def judge(self, cfg, artifact_json, stage, author_model):
        self.calls.append("judge")
        return SimpleNamespace(score=None, judge="none")

    async def record(self, cfg, record):
        self.calls.append("record")

    async def retain(self, cfg, kind, bank, text, metadata):
        self.calls.append("retain")


EXPECTED = [
    "recall", "cached:plan:plain", "run_role", "cached:plan:guided", "run_role",
    "gate:plan", "judge", "record", "retain",
]


def test_step_call_sequence_is_unchanged():
    ctx = Ctx()
    asyncio.run(step(
        ctx, cfg=PipelineConfig(), architecture=ARCH, idea=greenfield_idea(),
        planner_agent=object(), planner_model="m-plan",
    ))
    assert ctx.calls == EXPECTED


def test_prepare_produce_finish_compose_to_the_same_sequence():
    ctx = Ctx()
    cfg = PipelineConfig()

    async def go():
        prep = await prepare(ctx, cfg=cfg, idea=greenfield_idea(), planner_model="m-plan")
        await produce(ctx, prep, cfg=cfg, architecture=ARCH, planner_agent=object(), guidance=None)
        p2 = await produce(ctx, prep, cfg=cfg, architecture=ARCH, planner_agent=object(), guidance="again")
        ctx.calls.append("gate:plan")
        await finish(ctx, prep, cfg=cfg, artifact=p2,
                     gate=GateDecision(gate="plan", outcome=GateOutcome.APPROVE, decided_by="human"))
        return prep

    prep = asyncio.run(go())
    assert ctx.calls == EXPECTED
    assert (prep.resolved_model, prep.spend.role) == ("m-plan", "planner")
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/plan/test_plan_step_split.py -q`
Expected: FAIL. `ImportError: cannot import name 'finish'`.

- [ ] **Step 3: Rewrite `step()`**

Add `from dataclasses import dataclass`. Replace `async def step(...)` with:

```python
@dataclass
class PlanPrep:
    """The once-per-stage prefix of the plan stage (E-74 §4.3)."""

    started: datetime
    resolved_model: str
    spend: RoleUsage
    snapshot: Any
    salt: str


async def prepare(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    idea: IdeaBrief | None = None,
    planner_model: str | None = None,
) -> PlanPrep:
    started = _now()
    plan_role = cfg.roles.get("plan")
    resolved_model = (
        planner_model
        or (plan_role.model if plan_role and plan_role.model else None)
        or "claude-3-5-sonnet"
    )
    spend = RoleUsage(role="planner", model=resolved_model)
    title = idea.title if idea else "feature"
    snapshot = await ctx.recall(
        cfg,
        cfg.memory.project_bank,
        query=f"plan:{title}",
        filters={"stage": "plan"},
    )
    return PlanPrep(
        started=started,
        resolved_model=resolved_model,
        spend=spend,
        snapshot=snapshot,
        salt=prompt_digest(cfg),
    )


async def produce(
    ctx: StageContext,
    prep: PlanPrep,
    *,
    cfg: PipelineConfig,
    architecture: ArchitectureSpec,
    requirements: ClarifiedRequirements | None = None,
    planner_agent: Any = None,
    guidance: str | None = None,
) -> ImplementationPlan:
    """One planner round. Verbatim body of the former `_run_plan(guidance)`."""
    prompt = planner_prompt(architecture.model_dump_json(), prep.snapshot.items, guidance)

    async def _produce() -> ImplementationPlan:
        res = await ctx.run_role(
            cfg,
            "planner",
            prep.resolved_model,
            planner_agent,
            prompt,
            into=prep.spend,
        )
        return res.output

    cache_key = architecture.model_dump_json() + (guidance or "")
    plan_obj, _ = await ctx.cached_stage(
        cfg,
        "plan",
        cache_key,
        ImplementationPlan,
        _produce,
        prompt_digest=prep.salt,
    )
    return plan_obj


async def finish(
    ctx: StageContext,
    prep: PlanPrep,
    *,
    cfg: PipelineConfig,
    artifact: ImplementationPlan,
    gate: GateDecision,
) -> None:
    from ...benchmarks.models import BenchmarkOutcome
    from ...benchmarks.record_builder import stage_record

    _ended = _now()
    _quality = await ctx.judge(
        cfg,
        artifact.model_dump_json(),
        "planner",
        author_model=prep.resolved_model,
    )
    await ctx.record(
        cfg,
        stage_record(
            cfg,
            stage="plan",
            role="planner",
            started=prep.started,
            ended=_ended,
            quality_score=_quality.score,
            judge=_quality.judge,
            outcome=(BenchmarkOutcome.PASS if gate.approved else BenchmarkOutcome.REVISED),
            model=prep.resolved_model,
            spend=prep.spend,
        ),
    )
    await ctx.retain(
        cfg,
        MemoryKind.STAGE_SUMMARY,
        cfg.memory.project_bank,
        text=f"plan: {len(artifact.tasks)} tasks",
        metadata={"stage": "plan", "run_id": _workflow_id()},
    )


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    architecture: ArchitectureSpec,
    requirements: ClarifiedRequirements | None = None,
    idea: IdeaBrief | None = None,
    planner_agent: Any = None,
    planner_model: str | None = None,
) -> tuple[ImplementationPlan, GateDecision]:
    """Execute the plan stage: prepare, the revisable produce loop, finish."""
    prep = await prepare(ctx, cfg=cfg, idea=idea, planner_model=planner_model)

    async def _run_plan(guidance: str | None) -> ImplementationPlan:
        return await produce(
            ctx,
            prep,
            cfg=cfg,
            architecture=architecture,
            requirements=requirements,
            planner_agent=planner_agent,
            guidance=guidance,
        )

    plan_obj, gate = await ctx.revisable_stage(
        "plan", cfg, _run_plan, author_model=prep.resolved_model
    )
    await finish(ctx, prep, cfg=cfg, artifact=plan_obj, gate=gate)
    return plan_obj, gate
```

`ArchitectureSpec` and `ClarifiedRequirements` are already under `if TYPE_CHECKING:` and `from __future__ import annotations` is active, so no runtime import is added.

- [ ] **Step 4: Add clause PLAN-1.4 to `plan.md`**

Insert after the `### PLAN-1.3` paragraph:

```markdown
### PLAN-1.4
The step is composed of `prepare` (start time, role usage, memory recall, prompt salt), `produce` (one planner round keyed by the unchanged memo input) and `finish` (judge, benchmark record, memory retain). `step` composes them around `revisable_stage` for FeatureWorkflow; GraphWorkflow calls them across the `plan` and `gate.plan` nodes. [E-74 spec §4.3, §6.1]
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/plan -q`
Expected: PASS.

Run: `pytest tests/replay/test_feature_replay.py -q`
Expected: PASS (17). A red result is SG-2.

Run: `pytest -q`
Expected: green. A failure is SG-5.

- [ ] **Step 6: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t6-msg.txt`:

```text
refactor(plan): E-74 split step into prepare, produce, finish

Same composition as the architecture split; call sequence pinned by a
characterization test, commands by the Replayer proof.
```

```bash
git add src/sdlc/stages/plan/step.py
git add src/sdlc/stages/plan/plan.md
git add tests/plan/test_plan_step_split.py
git commit -F .workspace/tmp/e74-t6-msg.txt
```

### Task 7: Terminal ports and the `failed` outcome in the router

**Files:**
- Modify: `src/sdlc/graph/model.py` (`NodePort`)
- Modify: `src/sdlc/graph/topology.py` (`Topology`)
- Modify: `src/sdlc/graph/validate.py` (`_build_topology`)
- Modify: `src/sdlc/graph/router.py` (`Outcome`, `_TERMINAL`, step 4)
- Modify: `src/sdlc/graph/node_types.py` (`_out`, `_gate`, `_gate_shape_problems`)
- Modify: `tests/graph/fixtures/registries.py` (`port_out`, `gate`)
- Modify: `tests/graph/test_graph_router_properties.py:167-168` (`_ends_run`)
- Test: `tests/graph/test_graph_router_terminal.py`, plus additions to `tests/graph/test_graph_node_types.py` and `tests/graph/test_graph_model.py`

**Interfaces:**
- Produces:
  - `NodePort.terminal: Literal["rejected", "failed"] | None = None` (out-ports only)
  - `Topology.terminal_ports: Mapping[str, Mapping[str, Literal["rejected", "failed"]]]` (node → port → kind; only terminal ports listed; sorted)
  - `router.Outcome` includes `"failed"`
  - test helper `port_out(name, payload, *, terminal=None)`

- [ ] **Step 1: Write the failing tests**

`tests/graph/test_graph_router_terminal.py`:

```python
"""E-74 §4.4 / D6: a terminal port with no edges ends the run; with edges it routes."""

from __future__ import annotations

from tests.graph.fixtures.registries import edge, graph, node, port_in, port_out, registry, stage
from tests.graph.fixtures.routing import Run

TERM = registry(
    stage("start", port_out("ok", None)),
    stage(
        "work",
        port_in("trigger", None),
        port_out("out", "P"),
        port_out("fail", "F", terminal="failed"),
    ),
    stage("handler", port_in("failure", "F"), port_out("done", None)),
    stage("sink", port_in("art", "P"), port_out("done", None)),
)


def _two_workers(*extra_edges):
    return graph(
        [node("start", "start"), node("a", "work"), node("b", "work"), node("s", "sink"), *(
            [node("h", "handler")] if extra_edges else []
        )],
        [edge("start.ok", "a.trigger"), edge("start.ok", "b.trigger"), edge("a.out", "s.art"), *extra_edges],
    )


def test_unrouted_failed_terminal_ends_the_run_and_cancels_live():
    run = Run(_two_workers(), TERM)
    run.emit("start#1", "ok")
    assert run.live() == ["a#1", "b#1"]
    step = run.emit("a#1", "fail")
    assert (step.outcome, step.reason) == ("failed", "a.fail")
    assert step.cancelled == ("b#1",)
    assert run.state.live == ()


def test_routed_failed_terminal_routes_like_any_port():
    run = Run(_two_workers(edge("a.fail", "h.failure")), TERM)
    run.emit("start#1", "ok")
    step = run.emit("a#1", "fail", "boom-ref")
    assert step.outcome == "running"
    assert run.activation("h#1").inputs == {"failure": "boom-ref"}


def test_emission_after_failed_is_dropped_post_terminal():
    run = Run(_two_workers(), TERM)
    run.emit("start#1", "ok")
    run.emit("a#1", "fail")
    step = run.emit("b#1", "out")
    assert step.outcome == "failed"
    assert [(d.activation_id, d.reason) for d in step.state.dropped] == [("b#1", "post_terminal")]


def test_topology_lists_only_terminal_ports():
    run = Run(_two_workers(), TERM)
    t = run.router.topology
    assert dict(t.terminal_ports["a"]) == {"fail": "failed"}
    assert dict(t.terminal_ports["start"]) == {}
```

Append to `tests/graph/test_graph_model.py`:

```python
def test_node_port_terminal_is_for_out_ports_only():
    import pytest
    from pydantic import ValidationError

    from sdlc.graph import NodePort

    assert NodePort(name="fail", direction="out", payload="F", terminal="failed").terminal == "failed"
    with pytest.raises(ValidationError, match="cannot be terminal"):
        NodePort(name="x", direction="in", payload=None, terminal="rejected")
```

Append to `tests/graph/test_graph_node_types.py`:

```python
def test_gate_reject_must_be_terminal_rejected():
    from sdlc.graph.node_types import NodeTypeSpec as Spec

    bad = Spec(
        type="gate.x", kind="gate", role=None, canonical_stage="architecture",
        ports=(
            NodePort(name="artifact", direction="in", payload="ArchitectureSpec"),
            NodePort(name="approve", direction="out", payload="ArchitectureSpec"),
            NodePort(name="reject", direction="out", payload=None),
        ),
    )
    problems = check_node_types(MappingProxyType({"gate.x": bad}))
    assert "gate.x: gate out-port 'reject' must be terminal='rejected'" in problems


def test_seed_gate_rejects_are_terminal():
    for gate in ("gate.research", "gate.architecture", "gate.plan"):
        reject = find_port(NODE_TYPES[gate], "reject", "out")
        assert reject is not None and reject.terminal == "rejected"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/graph/test_graph_router_terminal.py tests/graph/test_graph_model.py tests/graph/test_graph_node_types.py -q`
Expected: FAIL. `TypeError: port_out() got an unexpected keyword argument 'terminal'` (collection error), and the model test fails on the unknown field.

- [ ] **Step 3: Implement**

`src/sdlc/graph/model.py`: in `NodePort`, after `multiplicity`, add:

```python
    # E-74 (D6): an emission on this out-port with NO edges ends the run with
    # this outcome; with edges it routes like any port (error routing is topology).
    terminal: Literal["rejected", "failed"] | None = None
```

In `_out_ports_are_plain`, before `return self`, add:

```python
        if self.direction == "in" and self.terminal is not None:
            raise ValueError(
                f"in-port {self.name!r} cannot be terminal (terminal applies to out-ports only)"
            )
```

`src/sdlc/graph/topology.py`: append to `Topology` (after `regions`):

```python
    terminal_ports: Mapping[str, Mapping[str, Literal["rejected", "failed"]]]  # node -> terminal out-port -> outcome
```

`src/sdlc/graph/validate.py` `_build_topology`: inside the per-node loop, build `terms` next to `outs`:

```python
        terms: dict[str, Literal["rejected", "failed"]] = {}
        for port in sorted(spec.ports, key=lambda p: (p.direction, p.name)):
            if port.direction == "out":
                if port.terminal is not None:
                    terms[port.name] = port.terminal
                outs[port.name] = tuple(
```

The rest of that branch is unchanged. After `in_ports[node_id] = dict(sorted(ins.items()))` add `terminal_ports[node_id] = dict(sorted(terms.items()))`. Declare `terminal_ports: dict[str, dict[str, Literal["rejected", "failed"]]] = {}` beside `out_ports`, pass `terminal_ports=terminal_ports` to `Topology(...)`, and add `Literal` to the `typing` import.

Then run `rg "Topology\(" src tests` and add `terminal_ports=...` to any other construction site it reports.

`src/sdlc/graph/router.py`:

```python
Outcome = Literal["running", "completed", "rejected", "escalated", "failed"]
_TERMINAL: tuple[Outcome, ...] = ("rejected", "escalated", "failed")
```

Replace step 4 (`router.py:266-270`) with:

```python
        # 4. no edges: a terminal port ends the run (gate reject included, E-74 D6);
        #    any other edgeless port is a sink
        if not edges:
            kind = self._t.terminal_ports.get(node_id, {}).get(event.port)
            if kind is not None:
                return self._terminate(w, kind, f"{node_id}.{event.port}", emitter=None)
            return self._settle(w, cancelled=[])
```

`src/sdlc/graph/node_types.py`:

```python
def _out(name: str, payload: str | None, *, terminal: Literal["rejected", "failed"] | None = None) -> NodePort:
    return NodePort(name=name, direction="out", payload=payload, terminal=terminal)
```

In `_gate`, use `_out("reject", None, terminal="rejected")`. In `_gate_shape_problems`, replace the reject check with:

```python
    if reject is None or reject.payload is not None:
        problems.append("gate out-port 'reject' must be a signal port")
    elif reject.terminal != "rejected":
        problems.append("gate out-port 'reject' must be terminal='rejected'")
```

`tests/graph/fixtures/registries.py`:

```python
def port_out(name: str, payload: str | None, *, terminal: str | None = None) -> NodePort:
    return NodePort(name=name, direction="out", payload=payload, terminal=terminal)  # type: ignore[arg-type]
```

In `gate()`, use `port_out("reject", None, terminal="rejected")`.

In `tests/graph/test_graph_router_properties.py`, replace `_ends_run`:

```python
def _ends_run(t, live: LiveActivation, port: str) -> bool:
    return port in t.terminal_ports.get(live.node_id, {})
```

In `tests/graph/test_graph_node_types.py`, the local `_out(name, payload)` helper gains `*, terminal=None` and passes it through. Any expected-problems list in that file whose broken registry has a gate with a non-terminal `reject` now also expects `"<type>: gate out-port 'reject' must be terminal='rejected'"`. Build those gates' `reject` with `terminal="rejected"` unless the row is about the reject port itself.

- [ ] **Step 4: Run the graph suite**

Run: `pytest tests/graph -q`
Expected: PASS. That covers the E-73 router tables, loops, properties, determinism goldens and purity. A `test_graph_determinism.py` golden JSON that serializes a `RouterState` does not include `Topology`, so it stays byte-identical. If it changes, that is SG-5.

Run: `pytest tests/test_dashboard_graph_wire.py tests/test_graph_fixtures_fresh.py -q`
Expected: PASS. Wire DTOs do not expose `terminal`.

- [ ] **Step 5: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t7-msg.txt`:

```text
feat(graph): E-74 terminal ports and the failed outcome

NodePort.terminal marks out-ports whose edgeless emission ends the run;
router step 4 generalises the gate-reject special case to data, gate
rejects declare terminal=rejected, and Outcome gains failed. E-73
properties re-run with terminal ports.
```

```bash
git add src/sdlc/graph/model.py
git add src/sdlc/graph/topology.py
git add src/sdlc/graph/validate.py
git add src/sdlc/graph/router.py
git add src/sdlc/graph/node_types.py
git add tests/graph/fixtures/registries.py
git add tests/graph/test_graph_router_properties.py
git add tests/graph/test_graph_router_terminal.py
git add tests/graph/test_graph_model.py
git add tests/graph/test_graph_node_types.py
git commit -F .workspace/tmp/e74-t7-msg.txt
```

### Task 8: The `Halt` router event

**Files:**
- Modify: `src/sdlc/graph/router.py`
- Modify: `src/sdlc/graph/__init__.py` (export `Halt`)
- Test: `tests/graph/test_graph_router_terminal.py` (append)

**Interfaces:**
- Produces:
  - `class Halt(BaseModel)`: `kind: Literal["halt"] = "halt"`, `outcome: Literal["rejected", "failed"]`, `reason: str`
  - `GraphRouter.advance(state, event: Emitted | Halt) -> Step`. `Halt` on a RUNNING state terminates it, with every live activation cancelled and retired. `Halt` on a terminal state raises `RouterError`.

- [ ] **Step 1: Append failing tests**

```python
import pytest

from sdlc.graph import Halt, RouterError


def test_halt_terminates_a_running_state_and_cancels_every_live_activation():
    run = Run(_two_workers(), TERM)
    run.emit("start#1", "ok")
    step = run.router.advance(run.state, Halt(outcome="rejected", reason="budget"))
    assert (step.outcome, step.reason) == ("rejected", "budget")
    assert step.cancelled == ("a#1", "b#1")
    assert step.state.retired == ("a#1", "b#1")
    assert step.activations == ()


def test_halt_after_a_terminal_outcome_is_an_interpreter_bug():
    run = Run(_two_workers(), TERM)
    run.emit("start#1", "ok")
    run.emit("a#1", "fail")
    with pytest.raises(RouterError, match="halt after terminal outcome"):
        run.router.advance(run.state, Halt(outcome="rejected", reason="budget"))
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/graph/test_graph_router_terminal.py -q`
Expected: FAIL. `ImportError: cannot import name 'Halt' from 'sdlc.graph'`.

- [ ] **Step 3: Implement**

In `router.py`, after `class Emitted`:

```python
class Halt(BaseModel):
    """A dispatcher-level stop (E-74 D7): budget rejection and the like. Keeps
    router state the post-mortem truth when the run ends outside a port."""

    model_config = _FROZEN

    kind: Literal["halt"] = "halt"
    outcome: Literal["rejected", "failed"]
    reason: str
```

Replace the head of `advance`:

```python
    def advance(self, state: RouterState, event: Emitted | Halt) -> Step:
        """Apply one emission (spec §6.2) or a Halt (E-74 D7)."""
        if isinstance(event, Halt):
            if state.outcome != "running":
                raise RouterError(
                    f"halt after terminal outcome {state.outcome!r} ({event.reason!r})"
                )
            return self._terminate(_Work.of(state), event.outcome, event.reason, emitter=None)
        if not isinstance(event, Emitted):
            raise RouterError(f"unsupported event {type(event).__name__}")
```

In `src/sdlc/graph/__init__.py`, add `Halt` to the `.router` import list and to `__all__` in sorted position.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/graph -q`
Expected: PASS.

- [ ] **Step 5: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t8-msg.txt`:

```text
feat(graph): E-74 Halt event

A dispatcher-level stop terminates a running router state, cancelling and
retiring every live activation; Halt after a terminal outcome is a
RouterError.
```

```bash
git add src/sdlc/graph/router.py
git add src/sdlc/graph/__init__.py
git add tests/graph/test_graph_router_terminal.py
git commit -F .workspace/tmp/e74-t8-msg.txt
```

### Task 9: Payload models, `budget_after`, payload allowlist

**Files:**
- Modify: `src/sdlc/core/models.py` (add `NodeFailure`)
- Modify: `src/sdlc/workflows/models.py` (add `BuildResult`, `AnalyzeResult`, `PullRequest`)
- Modify: `src/sdlc/graph/payloads.py`
- Modify: `src/sdlc/graph/node_types.py` (`NodeTypeSpec.budget_after`)
- Test: `tests/graph/test_graph_node_types.py` (update `test_payload_allowlist_seed`, add rows), `tests/test_workflow_payload_models.py`

**Interfaces:**
- Produces:
  - `NodeFailure(activation_id: str, error_type: str, message: str)`
  - `BuildResult(task_results: list[TaskResult])`
  - `AnalyzeResult(report: AnalysisReport, untraced: list[str], integration_diff: dict[str, Any])`
  - `PullRequest(url: str)`
  - `NodeTypeSpec.budget_after: Literal["none", "continuing", "exiting"] = "none"`
  - `PAYLOAD_TYPES` gains `"AnalyzeResult"`, `"BuildResult"`, `"NodeFailure"` and `"PullRequest"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_workflow_payload_models.py`:

```python
"""E-74 §4.4: graph payload models accept the real activity output shapes."""

from __future__ import annotations

from sdlc.core.models import NodeFailure
from sdlc.stages.analyze.models import AnalysisReport
from sdlc.workflows.models import AnalyzeResult, BuildResult, PullRequest, TaskResult


def test_analyze_result_accepts_get_task_diff_shape():
    diff = {"stat": " a | 1 +", "patch": "diff", "files": ["a.py"], "renames": [["b.py", "c.py"]]}
    r = AnalyzeResult(report=AnalysisReport(traceability=[], summary="s", confidence=0.5), untraced=[], integration_diff=diff)
    assert r.integration_diff["renames"] == [["b.py", "c.py"]]


def test_build_result_keeps_task_result_instances():
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b")
    assert BuildResult(task_results=[tr]).task_results[0] is tr


def test_node_failure_and_pull_request_shapes():
    assert NodeFailure(activation_id="a#1", error_type="ApplicationError", message="boom").message == "boom"
    assert PullRequest(url="https://example.test/pr/1").url.endswith("/1")
```

In `tests/graph/test_graph_node_types.py`, extend the expected dict in `test_payload_allowlist_seed` with:

```python
        "AnalyzeResult": "sdlc.workflows.models:AnalyzeResult",
        "BuildResult": "sdlc.workflows.models:BuildResult",
        "NodeFailure": "sdlc.core.models:NodeFailure",
        "PullRequest": "sdlc.workflows.models:PullRequest",
```

and append:

```python
def test_new_payloads_resolve():
    for name in ("AnalyzeResult", "BuildResult", "NodeFailure", "PullRequest"):
        assert node_types_module._resolve_payload(name) is None, name


def test_budget_after_defaults_to_none():
    assert _stage("x.y", _out("o", None)).budget_after == "none"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_workflow_payload_models.py tests/graph/test_graph_node_types.py -q`
Expected: FAIL. `ImportError: cannot import name 'NodeFailure'`.

- [ ] **Step 3: Implement**

`src/sdlc/core/models.py`, after `GateDecision`:

```python
class NodeFailure(BaseModel):
    """E-74 D8: a handler exception converted into a routable `fail` emission.
    An envelope no stage produces, hence core/."""

    activation_id: str
    error_type: str
    message: str
```

`src/sdlc/workflows/models.py`: add `from typing import Any, Literal` (extend the existing `Literal` import) and `from ..stages.analyze.models import AnalysisReport`. Then append:

```python
class BuildResult(BaseModel):
    """E-74: the `code` node's output -- every task result, in completion order."""

    task_results: list[TaskResult]


class AnalyzeResult(BaseModel):
    """E-74: the `analyze` node's output. The integration diff is fetched once and
    shared with merge (feature.py's analyze section), so it rides the payload.
    `integration_diff` is get_task_diff's dict (files/renames are lists)."""

    report: AnalysisReport
    untraced: list[str]
    integration_diff: dict[str, Any]


class PullRequest(BaseModel):
    """E-74: the `merge` node's output -- the PR url (or the benchmark skip string)."""

    url: str
```

`src/sdlc/graph/payloads.py`: add the four entries to `PAYLOAD_TYPES`, keeping the mapping's existing key order convention (sorted).

`src/sdlc/graph/node_types.py`, in `NodeTypeSpec`, after `ports`:

```python
    # E-74 D12: whether the dispatcher runs the run-budget check after this
    # type's emission -- "continuing": on a port carrying forward edges;
    # "exiting": on any port carrying no back edge; "none": never.
    budget_after: Literal["none", "continuing", "exiting"] = "none"
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_workflow_payload_models.py tests/graph -q`
Expected: PASS.

- [ ] **Step 5: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t9-msg.txt`:

```text
feat(graph): E-74 payload models and budget_after

NodeFailure (core), BuildResult/AnalyzeResult/PullRequest (workflow
envelopes) join PAYLOAD_TYPES; NodeTypeSpec gains budget_after.
```

```bash
git add src/sdlc/core/models.py
git add src/sdlc/workflows/models.py
git add src/sdlc/graph/payloads.py
git add src/sdlc/graph/node_types.py
git add tests/test_workflow_payload_models.py
git add tests/graph/test_graph_node_types.py
git commit -F .workspace/tmp/e74-t9-msg.txt
```

### Task 10: The post-plan catalog and pre-code port additions

**Files:**
- Modify: `src/sdlc/graph/node_types.py` (`_SEED` → full catalog)
- Modify: `tests/graph/test_graph_node_types.py` (catalog tables)
- Regenerate: `interfaces/dashboard/frontend/src/api/__fixtures__/graph/` via `python scripts/dump_graph_fixtures.py`
- Test: `tests/graph/test_graph_catalog_e74.py`

**Interfaces:**
- Produces the registry the M2 handlers and graphs rely on. Exact port tables are in Step 3. Type names:
  - pre-code: `intake`, `context`, `research`, `clarify`, `architect`, `plan`, `gate.research`, `gate.architecture`, `gate.plan`
  - post-plan: `plan_check`, `seed.spec`, `seed.plan`, `code`, `analyze`, `merge`, `deploy`

- [ ] **Step 1: Write the failing test `tests/graph/test_graph_catalog_e74.py`**

```python
"""E-74 §6: the registry after M1 -- additive to E-72, plus the post-plan half."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.graph import NODE_TYPES, check_node_types, from_yaml, validate
from tests.graph.fixtures.registries import roles

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


def _table(type_):
    return {
        (p.direction, p.name): (p.payload, p.required, p.terminal)
        for p in NODE_TYPES[type_].ports
    }


def test_registry_is_healthy():
    assert check_node_types() == []


def test_catalog_types():
    assert sorted(NODE_TYPES) == [
        "analyze", "architect", "clarify", "code", "context", "deploy",
        "gate.architecture", "gate.plan", "gate.research", "intake", "merge",
        "plan", "plan_check", "research", "seed.plan", "seed.spec",
    ]


FAIL = ("NodeFailure", True, "failed")


@pytest.mark.parametrize(
    ("type_", "expected"),
    [
        ("intake", {("out", "ok"): (None, True, None), ("out", "brownfield"): (None, True, None),
                    ("out", "reject"): (None, True, "rejected"), ("out", "fail"): FAIL}),
        ("context", {("in", "trigger"): (None, True, None), ("out", "map"): ("CodebaseMap", True, None),
                     ("out", "reject"): (None, True, "rejected"), ("out", "fail"): FAIL}),
        ("research", {("in", "trigger"): (None, False, None), ("in", "guidance"): ("GateDecision", False, None),
                      ("in", "codebase_map"): ("CodebaseMap", False, None),
                      ("out", "brief"): ("ResearchBrief", True, None),
                      ("out", "reject"): (None, True, "rejected"), ("out", "fail"): FAIL}),
        ("plan_check", {("in", "plan"): ("ImplementationPlan", True, None),
                        ("out", "ok"): ("ImplementationPlan", True, None),
                        ("out", "halt"): (None, True, "failed"), ("out", "fail"): FAIL}),
        ("seed.spec", {("in", "trigger"): (None, False, None), ("out", "spec"): ("ArchitectureSpec", True, None),
                       ("out", "fail"): FAIL}),
        ("seed.plan", {("in", "trigger"): (None, False, None), ("out", "plan"): ("ImplementationPlan", True, None),
                       ("out", "fail"): FAIL}),
        ("code", {("in", "plan"): ("ImplementationPlan", True, None), ("out", "results"): ("BuildResult", True, None),
                  ("out", "halt"): (None, True, "failed"), ("out", "fail"): FAIL}),
        ("analyze", {("in", "results"): ("BuildResult", True, None), ("in", "plan"): ("ImplementationPlan", True, None),
                     ("out", "analysis"): ("AnalyzeResult", True, None), ("out", "fail"): FAIL}),
        ("merge", {("in", "results"): ("BuildResult", True, None), ("in", "plan"): ("ImplementationPlan", True, None),
                   ("in", "spec"): ("ArchitectureSpec", True, None), ("in", "analysis"): ("AnalyzeResult", True, None),
                   ("out", "pr"): ("PullRequest", True, None),
                   ("out", "reject"): (None, True, "rejected"), ("out", "fail"): FAIL}),
        ("deploy", {("in", "pr"): ("PullRequest", True, None), ("out", "done"): (None, True, None),
                    ("out", "fail"): FAIL}),
    ],
)
def test_catalog_ports(type_, expected):
    assert _table(type_) == expected


@pytest.mark.parametrize(
    ("type_", "canonical", "budget"),
    [
        ("intake", "intake", "none"), ("context", "context", "none"),
        ("research", "research", "continuing"), ("clarify", "clarify", "continuing"),
        ("architect", "architecture", "none"), ("plan", "planning", "none"),
        ("gate.research", "research", "none"), ("gate.architecture", "architecture", "exiting"),
        ("gate.plan", "planning", "exiting"), ("plan_check", "planning", "none"),
        ("seed.spec", "architecture", "none"), ("seed.plan", "planning", "none"),
        ("code", "code", "none"), ("analyze", "analyze", "continuing"),
        ("merge", "quality_gate", "none"), ("deploy", "deploy", "none"),
    ],
)
def test_catalog_metadata(type_, canonical, budget):
    spec = NODE_TYPES[type_]
    assert (spec.canonical_stage, spec.budget_after) == (canonical, budget)


def test_stage_types_carry_fail_and_gates_do_not():
    for name, spec in sorted(NODE_TYPES.items()):
        ports = {p.name for p in spec.ports}
        assert ("fail" in ports) == (spec.kind == "stage"), name


def test_e72_fixture_still_validates_clean():
    graph = from_yaml(FIXTURE.read_text(encoding="utf-8"))
    assert validate(graph, roles=roles()).problems == ()
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/graph/test_graph_catalog_e74.py -q`
Expected: FAIL on `test_catalog_types` and the port tables.

- [ ] **Step 3: Replace the catalog in `src/sdlc/graph/node_types.py`**

Add helpers below `_out`:

```python
def _fail() -> NodePort:
    return _out("fail", "NodeFailure", terminal="failed")  # E-74 D8: every stage type


def _reject() -> NodePort:
    return _out("reject", None, terminal="rejected")


def _halt() -> NodePort:
    return _out("halt", None, terminal="failed")  # domain failure carrying a result string
```

Change `_gate` to take `budget_after` and pass it through:

```python
def _gate(
    type_: str, payload: str, canonical_stage: str, budget_after: Literal["none", "continuing", "exiting"]
) -> NodeTypeSpec:
    """A revise-loop gate: artifact:T -> approve:T | revise:GateDecision | reject (terminal)."""
    return NodeTypeSpec(
        type=type_,
        kind="gate",
        role=None,
        canonical_stage=canonical_stage,
        budget_after=budget_after,
        ports=(
            _in("artifact", payload),
            _out("approve", payload),
            _out("revise", "GateDecision"),
            _out("reject", None, terminal="rejected"),
        ),
    )
```

Replace `_SEED` and `NODE_TYPES` with:

```python
_CATALOG: tuple[NodeTypeSpec, ...] = (
    # ---- pre-code (E-72 seed; E-74 adds reject/fail/brownfield ports) ----
    NodeTypeSpec(
        type="intake",
        kind="stage",
        role=None,
        canonical_stage="intake",
        # `ok` is the greenfield path (name kept from E-72 so stored graphs keep their sha).
        ports=(_out("ok", None), _out("brownfield", None), _reject(), _fail()),
    ),
    NodeTypeSpec(
        type="context",
        kind="stage",
        role=None,
        canonical_stage="context",
        ports=(_in("trigger", None), _out("map", "CodebaseMap"), _reject(), _fail()),
    ),
    NodeTypeSpec(
        type="research",
        kind="stage",
        role="research",
        canonical_stage="research",
        budget_after="continuing",
        ports=(
            _in("trigger", None, required=False),
            _in("guidance", "GateDecision", required=False),
            # Ordering only (brownfield runs map context before research, feature.py:524-535).
            _in("codebase_map", "CodebaseMap", required=False),
            _out("brief", "ResearchBrief"),
            _reject(),
            _fail(),
        ),
    ),
    NodeTypeSpec(
        type="clarify",
        kind="stage",
        role="clarify",
        canonical_stage="clarify",
        budget_after="continuing",
        ports=(
            _in("trigger", None, required=False),
            _in("codebase_map", "CodebaseMap", required=False),
            _in("research", "ResearchBrief", required=False),
            _out("requirements", "ClarifiedRequirements"),
            _fail(),
        ),
    ),
    NodeTypeSpec(
        type="architect",
        kind="stage",
        role="architect",
        canonical_stage="architecture",
        ports=(
            _in("requirements", "ClarifiedRequirements"),
            _in("codebase_map", "CodebaseMap", required=False),
            _in("guidance", "GateDecision", required=False),
            _out("spec", "ArchitectureSpec"),
            _fail(),
        ),
    ),
    NodeTypeSpec(
        type="plan",
        kind="stage",
        role="planner",
        canonical_stage="planning",
        ports=(
            _in("spec", "ArchitectureSpec"),
            _in("requirements", "ClarifiedRequirements", required=False),
            _in("guidance", "GateDecision", required=False),
            _out("plan", "ImplementationPlan"),
            _fail(),
        ),
    ),
    _gate("gate.research", "ResearchBrief", "research", "none"),
    _gate("gate.architecture", "ArchitectureSpec", "architecture", "exiting"),
    _gate("gate.plan", "ImplementationPlan", "planning", "exiting"),
    # ---- post-plan (E-74 §6; coarse `code` per U1) ----
    NodeTypeSpec(
        type="plan_check",
        kind="stage",
        role=None,
        canonical_stage="planning",
        ports=(_in("plan", "ImplementationPlan"), _out("ok", "ImplementationPlan"), _halt(), _fail()),
    ),
    NodeTypeSpec(
        type="seed.spec",
        kind="stage",
        role=None,
        canonical_stage="architecture",
        ports=(_in("trigger", None, required=False), _out("spec", "ArchitectureSpec"), _fail()),
    ),
    NodeTypeSpec(
        type="seed.plan",
        kind="stage",
        role=None,
        canonical_stage="planning",
        ports=(_in("trigger", None, required=False), _out("plan", "ImplementationPlan"), _fail()),
    ),
    NodeTypeSpec(
        type="code",
        kind="stage",
        role=None,
        canonical_stage="code",
        ports=(_in("plan", "ImplementationPlan"), _out("results", "BuildResult"), _halt(), _fail()),
    ),
    NodeTypeSpec(
        type="analyze",
        kind="stage",
        role=None,
        canonical_stage="analyze",
        budget_after="continuing",
        ports=(
            _in("results", "BuildResult"),
            _in("plan", "ImplementationPlan"),
            _out("analysis", "AnalyzeResult"),
            _fail(),
        ),
    ),
    NodeTypeSpec(
        type="merge",
        kind="stage",
        role=None,
        canonical_stage="quality_gate",
        ports=(
            _in("results", "BuildResult"),
            _in("plan", "ImplementationPlan"),
            _in("spec", "ArchitectureSpec"),
            _in("analysis", "AnalyzeResult"),
            _out("pr", "PullRequest"),
            _reject(),
            _fail(),
        ),
    ),
    NodeTypeSpec(
        type="deploy",
        kind="stage",
        role=None,
        canonical_stage="deploy",
        ports=(_in("pr", "PullRequest"), _out("done", None), _fail()),
    ),
)

NODE_TYPES: Mapping[str, NodeTypeSpec] = MappingProxyType({s.type: s for s in _CATALOG})
```

Update the comment above the catalog to name E-74 §6 as the authority for the post-plan half. Keep the E-72 sentence about STAGE_ROLES type names.

- [ ] **Step 4: Update the E-72 catalog tests**

In `tests/graph/test_graph_node_types.py`:
- Delete `test_seed_catalog_types`, `test_seed_catalog_metadata` and `test_seed_catalog_ports`; `test_graph_catalog_e74.py` supersedes them.
- Keep `test_seed_registry_is_healthy`.
- Keep every compatibility, broken-registry and permutation test.

- [ ] **Step 5: Regenerate the dashboard catalog fixture**

Run: `python scripts/dump_graph_fixtures.py`
Expected: the files under `interfaces/dashboard/frontend/src/api/__fixtures__/graph/` are rewritten; `catalog.json` gains the new types and ports.

- [ ] **Step 6: Run the tests**

Run: `pytest tests/graph -q`
Expected: PASS.

Run: `pytest tests/test_graph_fixtures_fresh.py tests/test_dashboard_graph_wire.py -q`
Expected: PASS.

Run: `python scripts/check_ui.py`
Expected: PASS. This wrapper is the only JS entry point (`interfaces/AGENTS.md`). A frontend failure caused by the new types is SG-5: STOP and report. The canvas is E-76's surface.

- [ ] **Step 7: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t10-msg.txt`:

```text
feat(graph): E-74 post-plan catalog and pre-code terminal ports

Adds plan_check, seed.spec, seed.plan, code, analyze, merge and deploy;
every stage type gains a failed-terminal fail port, intake a brownfield
path, research an ordering-only codebase_map input with an optional
trigger. E-72 ports are unchanged otherwise, so stored graph shas hold.
Dashboard catalog fixture regenerated.
```

Stage each changed fixture file under `interfaces/dashboard/frontend/src/api/__fixtures__/graph/` with its own `git add <path>`; list them with `git status --short`.

```bash
git add src/sdlc/graph/node_types.py
git add tests/graph/test_graph_node_types.py
git add tests/graph/test_graph_catalog_e74.py
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/catalog.json
git commit -F .workspace/tmp/e74-t10-msg.txt
```

### Task 11: Boot-safe payload resolution + E-72/E-73 errata

**Files:**
- Modify: `src/sdlc/graph/node_types.py` (`_resolve_payload`)
- Create: `tests/graph/fixtures/boom_payload.py`
- Modify: `tests/graph/test_graph_node_types.py` (append)
- Modify: `docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md` (append erratum)
- Modify: `docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md` (append erratum)

- [ ] **Step 1: Write the failing test**

`tests/graph/fixtures/boom_payload.py`:

```python
"""A payload module whose import crashes (E-74: check_node_types runs at worker boot)."""

raise RuntimeError("import-time crash")
```

Append to `tests/graph/test_graph_node_types.py`:

```python
def test_resolve_payload_reports_an_import_time_crash(monkeypatch):
    monkeypatch.setattr(
        node_types_module,
        "PAYLOAD_TYPES",
        {**node_types_module.PAYLOAD_TYPES, "Boom": "tests.graph.fixtures.boom_payload:Boom"},
    )
    problem = node_types_module._resolve_payload("Boom")
    assert problem is not None and "does not resolve" in problem and "RuntimeError" in problem
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/graph/test_graph_node_types.py -q -k import_time`
Expected: FAIL. `RuntimeError: import-time crash` propagates.

- [ ] **Step 3: Implement**

In `_resolve_payload`, change the except clause to:

```python
    except Exception as exc:  # noqa: BLE001 -- E-74: boot must report, never crash (inbox E-72 minor 2)
        return f"payload {name!r} does not resolve ({target}): {type(exc).__name__}: {exc}"
```

- [ ] **Step 4: Append the errata to the two specs**

Append to the end of the E-72 spec:

```markdown

**Erratum (2026-09-15, E-74 M1 — spec `2026-09-15-graph-workflow-cutover-design.md`):**
- **§5 role precedence (E72-OQ-6 resolved, E-74 U5):** a non-None `node.role` fills the `PipelineConfig.roles[NodeTypeSpec.role]` entry **only when the run does not already override that role**; a key present in `cfg.roles` (CLI `--role-model`, benchmark arm) wins.
- **§6.1 registry fields:** `NodePort.terminal: Literal["rejected","failed"] | None` (out-ports only) and `NodeTypeSpec.budget_after: Literal["none","continuing","exiting"]` are added; gate rule 6 additionally requires `reject.terminal == "rejected"`.
- **§6.2/§6.4 catalog:** `PAYLOAD_TYPES` gains `NodeFailure`, `BuildResult`, `AnalyzeResult`, `PullRequest`. Every stage type gains `fail: NodeFailure` (terminal failed); `intake` gains `brownfield` and a terminal `reject`; `context` gains a terminal `reject`; `research.trigger` becomes optional and `research` gains an ordering-only optional `codebase_map: CodebaseMap` and a terminal `reject`. The post-plan types are catalogued by E-74 §6 (E72-OQ-3 closed). E72-OQ-4 closed by `fail`/`NodeFailure`.
- **§6.3:** `_resolve_payload` reports any import-time exception as a problem string (boot-safe).
```

Append to the end of the E-73 spec:

```markdown

**Erratum (2026-09-15, E-74 M1 — spec `2026-09-15-graph-workflow-cutover-design.md` D6/D7):**
- **§6.2 step 4:** "gate-kind node and `port == "reject"` with no edges → REJECTED" is generalised: an emission on a port listed in `Topology.terminal_ports` with no edges terminates with that port's outcome (`rejected` | `failed`), reason `"<node>.<port>"`. Gate `reject` ports declare `terminal="rejected"`, so REJECTED behaviour is unchanged. A terminal port with edges routes normally. E73-OQ-5 closed.
- **§4 / §6.6:** `Outcome` gains `failed`; REJECTED, ESCALATED and FAILED are terminal (post-terminal drops apply to all three).
- **§4 events:** `Halt{outcome: rejected|failed, reason}` joins `Emitted`; on a RUNNING state it terminates like step 2 with `emitter=None` (every live activation cancelled and retired); on a terminal state it raises `RouterError`.
- **§8:** `tests/graph/test_graph_router_terminal.py` pins the new rows; the property suite's run-ending predicate reads `Topology.terminal_ports`.
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/graph -q`
Expected: PASS.

- [ ] **Step 6: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t11-msg.txt`:

```text
fix(graph): E-74 boot-safe payload resolution; E-72/E-73 errata

_resolve_payload reports import-time crashes as problems now that worker
boot runs check_node_types. Errata record terminal ports, failed, Halt,
budget_after, the catalog additions and the U5 role precedence.
```

```bash
git add src/sdlc/graph/node_types.py
git add tests/graph/fixtures/boom_payload.py
git add tests/graph/test_graph_node_types.py
git add docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md
git add docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md
git commit -F .workspace/tmp/e74-t11-msg.txt
```

### Task 12: CHECKPOINT M1 — verify, then STOP for the orchestrator's fast-forward

No code. This task is the plan-structural M1 boundary.

- [ ] **Step 1: Confirm M1 is behaviour-neutral**

Run: `git diff --stat main...HEAD -- src/sdlc/cli.py src/sdlc/worker.py interfaces/dashboard/api/main.py src/sdlc/workflows/tidyup.py src/sdlc/benchmarks/workflow.py src/sdlc/channels/inbox.py src/sdlc/dashboard/fleet.py`
Expected: empty. No start site, parent, worker registration or query changed in M1.

- [ ] **Step 2: Full gates (separate invocations)**

Run, one per invocation:
- `pytest -q`
- `pytest tests/replay/test_feature_replay.py -q`
- `pytest tests/test_e2e_greenfield.py -m temporal -q --timeout=300 --timeout-method=thread`
- `ruff check .`
- `ruff format --check .`
- `mypy`
- `python scripts/check_file_size.py`

Expected: all green. The e2e run is the live cross-check that FeatureWorkflow still ships end to end.

- [ ] **Step 3: STOP**

Report to the orchestrator:
- the commit list `git log --oneline main..HEAD`;
- each gate's result;
- the line count of `src/sdlc/workflows/feature.py`, which must be below 775.

Do not start Task 13 until the orchestrator confirms `main` has been fast-forwarded to this branch.

---

## MILESTONE M2 — interpreter and cutover (one change)

M2 starts from `main` fast-forwarded to CHECKPOINT M1. New M2 tests live under `tests/graph_workflow/` unless a task names another path.

### Task 13: Handler contract (`graph_nodes/base.py`) and `GraphRunInput`

**Files:**
- Create: `src/sdlc/workflows/graph_nodes/__init__.py` (docstring only in this task)
- Create: `src/sdlc/workflows/graph_nodes/base.py`
- Modify: `src/sdlc/workflows/models.py` (add `GraphRunInput`)
- Test: `tests/graph_workflow/test_graph_node_base.py`

**Interfaces:**
- Produces (`sdlc.workflows.graph_nodes.base`):
  - `StoredPayload(model: BaseModel | None, producer: str, author_model: str | None = None, meta: Mapping[str, str] = {})` (frozen dataclass)
  - `NodeResult(port: str, payload: BaseModel | None = None, author_model: str | None = None, meta: Mapping[str, str] = {}, result: str | None = None, finalize: Callable[[], Awaitable[None]] | None = None)` (frozen dataclass)
  - `RunFacts(*, idea, repo_path, run_id, seeded, memory_watermark)`: read-only properties; `.integration` and `.base_sha` are `None` until `set_integration(handle)`, which is write-once (`RuntimeError` on a second call).
  - `NodeContext(ctx, host, facts, node, spec, topology, payloads, carries)` (frozen dataclass): `.payload(ref) -> StoredPayload`, `.carry(node_id) -> dict[str, Any]`, `.connected(port) -> bool`.
  - `Handler = Callable[[NodeContext, Activation, PipelineConfig], Awaitable[NodeResult]]`
  - `input_model(nc, act, port) -> Any | None`
  - `guidance_text(nc, act) -> str | None`
  - `graph_has_research(graph) -> bool`
  - `project_cfg(cfg, node, spec, *, research_in_graph: bool) -> PipelineConfig`
- Produces (`sdlc.workflows.models`): `GraphRunInput(idea: IdeaBrief, cfg: PipelineConfig, graph: PipelineGraph, roles: dict[str, RoleConfig], seeded: SeededWork | None = None)`

- [ ] **Step 1: Write the failing test**

```python
"""E-74 §5.2/§5.3/§7.2: the handler contract."""

from __future__ import annotations

import pytest

from sdlc.core.models import GateConfig, GateDecision, GateOutcome, GatePolicy, PipelineConfig, RoleConfig
from sdlc.graph import NODE_TYPES, GraphNode
from sdlc.graph.router import Activation
from sdlc.vcs import IntegrationHandle
from sdlc.workflows.graph_nodes.base import (
    NodeContext,
    NodeResult,
    RunFacts,
    StoredPayload,
    guidance_text,
    input_model,
    project_cfg,
)
from sdlc.workflows.models import GraphRunInput
from tests.fakes.canned import ARCH, greenfield_idea


def _facts() -> RunFacts:
    return RunFacts(idea=greenfield_idea(), repo_path="/fake/repo", run_id="wf", seeded=None, memory_watermark=None)


def test_run_facts_integration_is_write_once():
    facts = _facts()
    assert facts.integration is None and facts.base_sha is None
    facts.set_integration(IntegrationHandle(head_sha="h1", worktree_path="/wt"))
    assert (facts.integration.worktree_path, facts.base_sha) == ("/wt", "h1")
    with pytest.raises(RuntimeError, match="write-once"):
        facts.set_integration(IntegrationHandle(head_sha="h2", worktree_path="/wt2"))


def test_node_result_defaults():
    r = NodeResult(port="ok")
    assert (r.payload, r.author_model, dict(r.meta), r.result, r.finalize) == (None, None, {}, None, None)


def _nc(payloads) -> NodeContext:
    return NodeContext(
        ctx=None, host=None, facts=_facts(), node=GraphNode(id="architect", type="architect"),
        spec=NODE_TYPES["architect"], topology=None, payloads=payloads, carries={},
    )


def test_input_model_and_guidance_text():
    decision = GateDecision(gate="architecture", outcome=GateOutcome.REVISE, decided_by="human", comments="c1")
    payloads = {"a#1.spec": StoredPayload(model=ARCH, producer="a#1"), "g#1.revise": StoredPayload(model=decision, producer="g#1")}
    act = Activation(activation_id="architect#2", node_id="architect", round=2,
                     inputs={"requirements": "a#1.spec", "guidance": "g#1.revise"}, unavailable_ports={})
    nc = _nc(payloads)
    assert input_model(nc, act, "requirements") is ARCH
    assert input_model(nc, act, "codebase_map") is None
    assert guidance_text(nc, act) == "c1"
    no_guidance = act.model_copy(update={"inputs": {"requirements": "a#1.spec"}})
    assert guidance_text(nc, no_guidance) is None


def test_carry_is_per_node_and_persistent():
    nc = _nc({})
    nc.carry("architect")["prep"] = 1
    assert nc.carry("architect") == {"prep": 1}
    assert nc.carry("planner") == {}


def test_project_cfg_is_identity_without_node_config():
    cfg = PipelineConfig()
    out = project_cfg(cfg, GraphNode(id="architect", type="architect"), NODE_TYPES["architect"], research_in_graph=False)
    assert out == cfg


def test_project_cfg_node_role_fills_only_an_unoverridden_role():
    node = GraphNode(id="architect", type="architect", role=RoleConfig(kind="proposer", model="node-model"))
    filled = project_cfg(PipelineConfig(), node, NODE_TYPES["architect"], research_in_graph=False)
    assert filled.roles["architect"].model == "node-model"
    run = PipelineConfig()
    run.roles["architect"] = RoleConfig(kind="proposer", model="run-model")
    kept = project_cfg(run, node, NODE_TYPES["architect"], research_in_graph=False)
    assert kept.roles["architect"].model == "run-model"  # U5: run-level override wins


def test_project_cfg_gate_and_research():
    node = GraphNode(id="plan", type="gate.plan", gate=GateConfig(policy=GatePolicy.OFF))
    out = project_cfg(PipelineConfig(research_enabled=True), node, NODE_TYPES["gate.plan"], research_in_graph=False)
    assert out.gates["plan"].policy is GatePolicy.OFF
    assert out.research_enabled is False


def test_graph_run_input_round_trips():
    from sdlc.graph import PipelineGraph

    inp = GraphRunInput(idea=greenfield_idea(), cfg=PipelineConfig(), graph=PipelineGraph(schema_version=1, nodes=[], edges=[]), roles={})
    assert GraphRunInput.model_validate_json(inp.model_dump_json()) == inp
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/graph_workflow/test_graph_node_base.py -q`
Expected: FAIL. `ModuleNotFoundError: No module named 'sdlc.workflows.graph_nodes'`.

- [ ] **Step 3: Implement**

`src/sdlc/workflows/graph_nodes/__init__.py`:

```python
"""Graph node handlers (E-74 spec §6). HANDLERS is assembled in Task 18."""
```

`src/sdlc/workflows/graph_nodes/base.py`:

```python
"""The graph node handler contract (E-74 spec §5.2, §5.3, §7.2; D2-D5).

A handler is `async (NodeContext, Activation, PipelineConfig) -> NodeResult`
(user ruling U10). Inputs arrive only through the Activation's payload refs;
run facts, stage services and the payload store ride NodeContext. Handlers
never mint refs and never touch router state (the dispatcher owns both).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from pydantic import BaseModel

    from ...core.models import IdeaBrief, PipelineConfig
    from ...graph.model import GraphNode, PipelineGraph
    from ...graph.node_types import NodeTypeSpec
    from ...graph.router import Activation
    from ...graph.topology import Topology
    from ...vcs import IntegrationHandle
    from ..models import SeededWork


@dataclass(frozen=True)
class StoredPayload:
    model: BaseModel | None
    producer: str  # activation id
    author_model: str | None = None
    meta: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class NodeResult:
    port: str
    payload: BaseModel | None = None
    author_model: str | None = None
    meta: Mapping[str, str] = field(default_factory=dict)
    result: str | None = None  # only on a terminal port or a sink (§5.6)
    finalize: Callable[[], Awaitable[None]] | None = None  # runs after the budget boundary


class RunFacts:
    """Run context. Written once by the entry node (integration, base_sha); never a port (E-72 D8)."""

    def __init__(
        self,
        *,
        idea: IdeaBrief,
        repo_path: str,
        run_id: str,
        seeded: SeededWork | None,
        memory_watermark: str | None,
    ) -> None:
        self._idea = idea
        self._repo_path = repo_path
        self._run_id = run_id
        self._seeded = seeded
        self._memory_watermark = memory_watermark
        self._integration: IntegrationHandle | None = None

    idea = property(lambda self: self._idea)
    repo_path = property(lambda self: self._repo_path)
    run_id = property(lambda self: self._run_id)
    seeded = property(lambda self: self._seeded)
    memory_watermark = property(lambda self: self._memory_watermark)

    @property
    def integration(self) -> IntegrationHandle | None:
        return self._integration

    @property
    def base_sha(self) -> str | None:
        return self._integration.head_sha if self._integration is not None else None

    def set_integration(self, handle: IntegrationHandle) -> None:
        if self._integration is not None:
            raise RuntimeError("RunFacts.integration is write-once")
        self._integration = handle


@dataclass(frozen=True)
class NodeContext:
    ctx: Any  # the StageContext services (core/context.py)
    host: Any  # the workflow instance: observability writes + TaskHost capabilities (D5)
    facts: RunFacts
    node: GraphNode
    spec: NodeTypeSpec
    topology: Topology | None
    payloads: Mapping[str, StoredPayload]
    carries: dict[str, dict[str, Any]]

    def payload(self, ref: str) -> StoredPayload:
        return self.payloads[ref]

    def carry(self, node_id: str) -> dict[str, Any]:
        """Cross-activation, per-node state; never reset by region invalidation (D4)."""
        return self.carries.setdefault(node_id, {})

    def connected(self, port: str) -> bool:
        assert self.topology is not None
        return bool(self.topology.out_ports[self.node.id].get(port))


Handler = Callable[[NodeContext, Activation, PipelineConfig], Awaitable[NodeResult]]


def input_model(nc: NodeContext, act: Activation, port: str) -> Any | None:
    ref = act.inputs.get(port)
    return nc.payload(ref).model if isinstance(ref, str) else None


def guidance_text(nc: NodeContext, act: Activation) -> str | None:
    decision = input_model(nc, act, "guidance")
    if decision is None:
        return None
    return decision.guidance or decision.comments  # role_host.py:261


def graph_has_research(graph: PipelineGraph) -> bool:
    return any(n.type == "research" for n in graph.nodes)


def project_cfg(
    cfg: PipelineConfig, node: GraphNode, spec: NodeTypeSpec, *, research_in_graph: bool
) -> PipelineConfig:
    """The per-activation cfg (spec §5.2): a node role fills an unoverridden
    role (U5), a node gate overlays cfg.gates[node.id], research_enabled
    follows the graph. Equal to `cfg` for every shipped graph (pinned in Task 14)."""
    roles = dict(cfg.roles)
    if node.role is not None and spec.role is not None and spec.role not in cfg.roles:
        roles[spec.role] = node.role
    gates = dict(cfg.gates)
    if node.gate is not None:
        gates[node.id] = node.gate
    return cfg.model_copy(update={"roles": roles, "gates": gates, "research_enabled": research_in_graph})
```

`src/sdlc/workflows/models.py`:
- Add `from ..core.models import IdeaBrief, PipelineConfig, RoleConfig` and `from ..graph.model import PipelineGraph`.
- Append:

```python
class GraphRunInput(BaseModel):
    """E-74 §5.1: GraphWorkflow's single, pinned input."""

    idea: IdeaBrief
    cfg: PipelineConfig
    graph: PipelineGraph
    roles: dict[str, RoleConfig]  # registry roles overlaid with cfg.roles, loader fields stripped
    seeded: SeededWork | None = None
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/graph_workflow/test_graph_node_base.py -q`
Expected: PASS (9 passed).

- [ ] **Step 5: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t13-msg.txt`:

```text
feat(workflows): E-74 graph node handler contract and GraphRunInput

NodeContext, NodeResult, StoredPayload, write-once RunFacts, input helpers
and the per-activation cfg projection (U5: run-level role override wins).
```

```bash
git add src/sdlc/workflows/graph_nodes/__init__.py
git add src/sdlc/workflows/graph_nodes/base.py
git add src/sdlc/workflows/models.py
git add tests/graph_workflow/test_graph_node_base.py
git commit -F .workspace/tmp/e74-t13-msg.txt
```

### Task 14: Shipped graphs and `graph_catalog`

**Files:**
- Create: `src/sdlc/workflows/graphs/default.graph.yaml`
- Create: `src/sdlc/workflows/graphs/default-research.graph.yaml`
- Create: `src/sdlc/workflows/graphs/seeded.graph.yaml`
- Create: `src/sdlc/workflows/graph_catalog.py`
- Modify: `pyproject.toml` (package data for `*.graph.yaml`, only if the wheel config lists package data explicitly; see Step 3)
- Test: `tests/graph_workflow/test_graph_catalog.py`, `tests/graph_workflow/test_shipped_graph_routing.py`

**Interfaces:**
- Consumes: `project_cfg`, `graph_has_research` (Task 13); `NODE_TYPES` (Task 10).
- Produces:
  - `SHIPPED: Mapping[str, PipelineGraph]` with keys `default`, `default-research`, `seeded`
  - `NOT_EXECUTABLE: Mapping[str, str]`
  - `ExecutableProblem(code, node, message)`
  - `executable(graph, handler_types: Iterable[str] | None = None) -> tuple[ExecutableProblem, ...]`
  - `select_graph(cfg, seeded, registry_roles=None) -> PipelineGraph`
  - `template_revise_bounds(graph, bound: int) -> PipelineGraph`
  - `resolved_roles(cfg, registry_roles=None) -> dict[str, RoleConfig]`
  - `GraphStartError(ValueError)` with `.problems: list[str]`
  - `build_run_input(idea, cfg, seeded=None, *, registry_roles=None, handler_types=None) -> GraphRunInput`

- [ ] **Step 1: Write the failing tests**

`tests/graph_workflow/test_graph_catalog.py`:

```python
"""E-74 §5.8, §7.1: shipped graphs, selection, templating, executable."""

from __future__ import annotations

import pytest

from sdlc.core.models import PipelineConfig, RoleConfig
from sdlc.graph import NODE_TYPES, PipelineGraph, validate
from sdlc.workflows.graph_catalog import (
    NOT_EXECUTABLE,
    SHIPPED,
    GraphStartError,
    build_run_input,
    executable,
    resolved_roles,
    select_graph,
    template_revise_bounds,
)
from sdlc.workflows.graph_nodes.base import graph_has_research, project_cfg
from sdlc.workflows.models import SeededWork
from tests.fakes.canned import ARCH, PLAN, e2e_config, greenfield_idea
from tests.graph.fixtures.registries import roles

ALL_TYPES = [t for t in NODE_TYPES if t not in NOT_EXECUTABLE]


@pytest.mark.parametrize("name", sorted(SHIPPED))
def test_shipped_graphs_are_legal_and_executable(name):
    graph = SHIPPED[name]
    assert validate(graph, roles=roles()).problems == ()
    assert executable(graph, ALL_TYPES) == ()


def test_research_graph_is_the_only_one_with_research():
    assert [n for n in sorted(SHIPPED) if graph_has_research(SHIPPED[n])] == ["default-research"]


def test_select_graph():
    reg = roles()
    assert select_graph(PipelineConfig(), None, reg) is SHIPPED["default"]
    assert select_graph(PipelineConfig(research_enabled=True), None, reg) is SHIPPED["default-research"]
    no_research = roles(research=None)
    assert select_graph(PipelineConfig(research_enabled=True), None, no_research) is SHIPPED["default"]
    seeded = SeededWork(arch=ARCH, plan=PLAN)
    assert select_graph(PipelineConfig(research_enabled=True), seeded, reg) is SHIPPED["seeded"]


def test_template_revise_bounds_sets_only_pre_code_revise_edges():
    graph = template_revise_bounds(SHIPPED["default"], 4)
    bounded = {(e.source, e.source_port): e.max_traversals for e in graph.edges if e.max_traversals}
    assert bounded == {("architecture", "revise"): 4, ("plan", "revise"): 4}
    assert template_revise_bounds(SHIPPED["seeded"], 4) == SHIPPED["seeded"]


def test_resolved_roles_run_override_wins_and_loader_fields_are_stripped():
    reg = {"architect": RoleConfig(kind="proposer", model="reg", instructions="prompt text")}
    cfg = PipelineConfig()
    cfg.roles["architect"] = RoleConfig(kind="proposer", model="run")
    out = resolved_roles(cfg, reg)
    assert out["architect"].model == "run"
    assert all(rc.instructions is None and rc.tool_files == [] for rc in out.values())
    assert list(out) == sorted(out)


def test_executable_rows():
    from tests.graph.fixtures.registries import node

    base = SHIPPED["default"]
    no_handler = executable(base, [t for t in ALL_TYPES if t != "deploy"])
    assert [(p.code, p.node) for p in no_handler] == [("no_handler", "deploy")]
    with_research_gate = PipelineGraph(
        schema_version=1,
        nodes=[*base.nodes, node("research", "gate.research")],
        edges=list(base.edges),
    )
    codes = {(p.code, p.node) for p in executable(with_research_gate, ALL_TYPES)}
    assert ("not_executable", "research") in codes


def test_executable_flags_a_gate_named_like_a_handler_internal_gate():
    from tests.graph.fixtures.registries import node

    # A gate-kind node with id "research" beside a composite research node:
    # both would mint gate_key("research", k) (advisor Q1 P7).
    clash = PipelineGraph(
        schema_version=1,
        nodes=[node("researcher", "research"), node("research", "gate.architecture")],
        edges=[],
    )
    codes = {(p.code, p.node) for p in executable(clash, ALL_TYPES)}
    assert ("gate_name_collision", "research") in codes


def test_build_run_input_templates_validates_and_strips():
    cfg = e2e_config()
    cfg.max_gate_rounds = 3
    inp = build_run_input(greenfield_idea(), cfg, registry_roles=roles(), handler_types=ALL_TYPES)
    assert {e.max_traversals for e in inp.graph.edges if e.max_traversals} == {3}
    assert inp.seeded is None and inp.cfg is cfg


def test_build_run_input_rejects_zero_gate_rounds():
    cfg = PipelineConfig(max_gate_rounds=0)
    with pytest.raises(GraphStartError, match="max_gate_rounds"):
        build_run_input(greenfield_idea(), cfg, registry_roles=roles(), handler_types=ALL_TYPES)


@pytest.mark.parametrize(("name", "research"), [("default", False), ("default-research", True), ("seeded", False)])
def test_projection_over_shipped_graphs_is_identity(name, research):
    cfg = e2e_config()
    cfg.research_enabled = research
    graph = SHIPPED[name]
    for n in graph.nodes:
        assert project_cfg(cfg, n, NODE_TYPES[n.type], research_in_graph=graph_has_research(graph)) == cfg, n.id
```

`tests/graph_workflow/test_shipped_graph_routing.py`:

```python
"""E-74 §7.1: the shipped graphs route today's stage order under E-73 readiness."""

from __future__ import annotations

from sdlc.graph import NODE_TYPES
from sdlc.workflows.graph_catalog import SHIPPED
from tests.graph.fixtures.registries import roles
from tests.graph.fixtures.routing import Run


def _run(name: str) -> Run:
    return Run(SHIPPED[name], NODE_TYPES, roles())


def _tail(run: Run) -> None:
    run.emit("plan_check#1", "ok")
    assert run.live() == ["code#1"]
    run.emit("code#1", "results")
    assert run.live() == ["analyze#1"]
    run.emit("analyze#1", "analysis")
    assert run.live() == ["merge#1"]
    run.emit("merge#1", "pr")
    assert run.live() == ["deploy#1"]
    assert run.emit("deploy#1", "done").outcome == "completed"


def test_default_greenfield_with_architecture_revise_to_final_gate():
    run = _run("default")
    run.emit("intake#1", "ok")
    assert run.live() == ["clarify#1"]
    run.emit("clarify#1", "requirements")
    assert run.live() == ["architect#1"]
    run.emit("architect#1", "spec")
    run.emit("architecture#1", "revise")
    run.emit("architect#2", "spec")
    run.emit("architecture#2", "revise")
    run.emit("architect#3", "spec")
    assert run.activation("architecture#3").unavailable_ports == {"revise": "exhausted"}
    run.emit("architecture#3", "approve")
    assert run.live() == ["planner#1"]
    run.emit("planner#1", "plan")
    run.emit("plan#1", "approve")
    assert run.live() == ["plan_check#1"]
    _tail(run)


def test_default_brownfield_maps_context_first():
    run = _run("default")
    run.emit("intake#1", "brownfield")
    assert run.live() == ["context#1"]
    run.emit("context#1", "map")
    assert run.live() == ["clarify#1"]
    run.emit("clarify#1", "requirements")
    assert run.activation("architect#1").inputs["codebase_map"] == "context#1:map"


def test_default_architecture_reject_ends_rejected():
    run = _run("default")
    run.emit("intake#1", "ok")
    run.emit("clarify#1", "requirements")
    run.emit("architect#1", "spec")
    step = run.emit("architecture#1", "reject")
    assert (step.outcome, step.reason) == ("rejected", "architecture.reject")


def test_research_brownfield_orders_context_research_clarify():
    run = _run("default-research")
    run.emit("intake#1", "brownfield")
    assert run.live() == ["context#1"]
    run.emit("context#1", "map")
    assert run.live() == ["research#1"]
    run.emit("research#1", "brief")
    assert run.live() == ["clarify#1"]


def test_research_greenfield_runs_research_first():
    run = _run("default-research")
    run.emit("intake#1", "ok")
    assert run.live() == ["research#1"]


def test_seeded_skips_pre_code_and_joins_at_merge():
    run = _run("seeded")
    run.emit("intake#1", "ok")
    assert run.live() == ["seed_plan#1", "seed_spec#1"]
    run.emit("seed_plan#1", "plan")
    assert run.live() == ["code#1", "seed_spec#1"]
    run.emit("seed_spec#1", "spec")
    run.emit("code#1", "results")
    run.emit("analyze#1", "analysis")
    run.emit("merge#1", "pr")
    assert run.emit("deploy#1", "done").outcome == "completed"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/graph_workflow/test_graph_catalog.py tests/graph_workflow/test_shipped_graph_routing.py -q`
Expected: FAIL. `ModuleNotFoundError: No module named 'sdlc.workflows.graph_catalog'`.

- [ ] **Step 3: Write the three graphs**

`src/sdlc/workflows/graphs/default.graph.yaml`:

```yaml
schema_version: 1
nodes:
- {id: intake, type: intake}
- {id: context, type: context}
- {id: clarify, type: clarify}
- {id: architect, type: architect}
- {id: architecture, type: gate.architecture}
- {id: planner, type: plan}
- {id: plan, type: gate.plan}
- {id: plan_check, type: plan_check}
- {id: code, type: code}
- {id: analyze, type: analyze}
- {id: merge, type: merge}
- {id: deploy, type: deploy}
edges:
- {source: intake, source_port: ok, target: clarify, target_port: trigger}
- {source: intake, source_port: brownfield, target: context, target_port: trigger}
- {source: context, source_port: map, target: clarify, target_port: codebase_map}
- {source: context, source_port: map, target: architect, target_port: codebase_map}
- {source: clarify, source_port: requirements, target: architect, target_port: requirements}
- {source: clarify, source_port: requirements, target: planner, target_port: requirements}
- {source: architect, source_port: spec, target: architecture, target_port: artifact}
- {source: architecture, source_port: revise, target: architect, target_port: guidance, max_traversals: 2}
- {source: architecture, source_port: approve, target: planner, target_port: spec}
- {source: architecture, source_port: approve, target: merge, target_port: spec}
- {source: planner, source_port: plan, target: plan, target_port: artifact}
- {source: plan, source_port: revise, target: planner, target_port: guidance, max_traversals: 2}
- {source: plan, source_port: approve, target: plan_check, target_port: plan}
- {source: plan_check, source_port: ok, target: code, target_port: plan}
- {source: plan_check, source_port: ok, target: analyze, target_port: plan}
- {source: plan_check, source_port: ok, target: merge, target_port: plan}
- {source: code, source_port: results, target: analyze, target_port: results}
- {source: code, source_port: results, target: merge, target_port: results}
- {source: analyze, source_port: analysis, target: merge, target_port: analysis}
- {source: merge, source_port: pr, target: deploy, target_port: pr}
```

`src/sdlc/workflows/graphs/default-research.graph.yaml` is `default.graph.yaml` with these changes:
- add the node `- {id: research, type: research}` after `context`;
- replace the edge `intake.ok -> clarify.trigger` with the three edges below.

```yaml
- {source: intake, source_port: ok, target: research, target_port: trigger}
- {source: context, source_port: map, target: research, target_port: codebase_map}
- {source: research, source_port: brief, target: clarify, target_port: research}
```

Write the file in full; do not generate it by script.

`src/sdlc/workflows/graphs/seeded.graph.yaml`:

```yaml
schema_version: 1
nodes:
- {id: intake, type: intake}
- {id: seed_spec, type: seed.spec}
- {id: seed_plan, type: seed.plan}
- {id: code, type: code}
- {id: analyze, type: analyze}
- {id: merge, type: merge}
- {id: deploy, type: deploy}
edges:
- {source: intake, source_port: ok, target: seed_spec, target_port: trigger}
- {source: intake, source_port: brownfield, target: seed_spec, target_port: trigger}
- {source: intake, source_port: ok, target: seed_plan, target_port: trigger}
- {source: intake, source_port: brownfield, target: seed_plan, target_port: trigger}
- {source: seed_plan, source_port: plan, target: code, target_port: plan}
- {source: seed_plan, source_port: plan, target: analyze, target_port: plan}
- {source: seed_plan, source_port: plan, target: merge, target_port: plan}
- {source: seed_spec, source_port: spec, target: merge, target_port: spec}
- {source: code, source_port: results, target: analyze, target_port: results}
- {source: code, source_port: results, target: merge, target_port: results}
- {source: analyze, source_port: analysis, target: merge, target_port: analysis}
- {source: merge, source_port: pr, target: deploy, target_port: pr}
```

Packaging: run `rg "package-data|package_data|include" pyproject.toml`. If `[tool.setuptools.package-data]` (or equivalent) lists data globs, add `"sdlc.workflows" = ["graphs/*.graph.yaml"]` beside the existing entries. If the project ships no explicit package-data table, add nothing: the editable install reads files from the source tree.

- [ ] **Step 4: Implement `src/sdlc/workflows/graph_catalog.py`**

```python
"""Shipped graphs, graph selection and the executable check (E-74 spec §5.8, §7.1).

Graphs are read at import (a passthrough module -- the agents.roles REGISTRY
precedent), so parent workflows that start a GraphWorkflow child do no I/O.
`validate` answers "is this graph legal" for every consumer; `executable`
answers "can this worker run it today" and is applied by start sites and
GraphWorkflow.run only (skeptic F12).

WORKFLOW CALLERS must pass `registry_roles=` and `handler_types=` explicitly:
the defaults lazily import sdlc.agents.roles / graph_nodes, which is only safe
in client code, never inside the workflow sandbox (plan skeptic F8).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..core.models import IdeaBrief, PipelineConfig, RoleConfig
    from ..graph.io import from_yaml
    from ..graph.model import PipelineGraph
    from ..graph.node_types import NODE_TYPES
    from ..graph.validate import validate
    from .models import GraphRunInput, SeededWork

GRAPHS_DIR = Path(__file__).parent / "graphs"
SHIPPED_NAMES: tuple[str, ...] = ("default", "default-research", "seeded")


def _load(name: str) -> PipelineGraph:
    return from_yaml((GRAPHS_DIR / f"{name}.graph.yaml").read_text(encoding="utf-8"))


SHIPPED: Mapping[str, PipelineGraph] = MappingProxyType({n: _load(n) for n in SHIPPED_NAMES})

# The pre-code revise edges templated from cfg.max_gate_rounds (user ruling U4).
PRE_CODE_REVISE: tuple[tuple[str, str], ...] = (("architecture", "revise"), ("plan", "revise"))

NOT_EXECUTABLE: Mapping[str, str] = MappingProxyType(
    {"gate.research": "the research refine loop is handler-internal until research-as-topology (E74-OQ-2)"}
)
# node type -> the gate name its handler opens internally
HANDLER_INTERNAL_GATES: Mapping[str, str] = MappingProxyType({"research": "research"})


class ExecutableProblem(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: Literal["gate_name_collision", "no_handler", "not_executable"]
    node: str
    message: str


class GraphStartError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


def executable(
    graph: PipelineGraph, handler_types: Iterable[str] | None = None
) -> tuple[ExecutableProblem, ...]:
    if handler_types is None:
        from .graph_nodes import HANDLERS

        handler_types = HANDLERS
    known = frozenset(handler_types)
    internal = frozenset(HANDLER_INTERNAL_GATES[n.type] for n in graph.nodes if n.type in HANDLER_INTERNAL_GATES)
    problems: list[ExecutableProblem] = []
    for n in graph.nodes:  # sorted by PipelineGraph's validator
        if n.type in NOT_EXECUTABLE:
            problems.append(ExecutableProblem(code="not_executable", node=n.id, message=NOT_EXECUTABLE[n.type]))
        elif n.type not in known:
            problems.append(ExecutableProblem(code="no_handler", node=n.id, message=f"no handler for node type {n.type!r}"))
        spec = NODE_TYPES.get(n.type)
        if spec is not None and spec.kind == "gate" and n.id in internal:
            problems.append(
                ExecutableProblem(
                    code="gate_name_collision",
                    node=n.id,
                    message=f"gate node id {n.id!r} collides with a handler-internal gate of the same name",
                )
            )
    return tuple(sorted(problems, key=lambda p: (p.code, p.node)))


def resolved_roles(
    cfg: PipelineConfig, registry_roles: Mapping[str, RoleConfig] | None = None
) -> dict[str, RoleConfig]:
    if registry_roles is None:
        from ..agents.roles import REGISTRY as registry_roles
    merged = {**registry_roles, **cfg.roles}
    return {
        name: rc.model_copy(update={"instructions": None, "tool_files": []})
        for name, rc in sorted(merged.items())
    }


def select_graph(
    cfg: PipelineConfig,
    seeded: SeededWork | None,
    registry_roles: Mapping[str, RoleConfig] | None = None,
) -> PipelineGraph:
    if registry_roles is None:
        from ..agents.roles import REGISTRY as registry_roles
    if seeded is not None:
        return SHIPPED["seeded"]
    if cfg.research_enabled and "research" in registry_roles:  # feature.py:535 guard
        return SHIPPED["default-research"]
    return SHIPPED["default"]


def template_revise_bounds(graph: PipelineGraph, bound: int) -> PipelineGraph:
    edges = [
        e.model_copy(update={"max_traversals": bound})
        if (e.source, e.source_port) in PRE_CODE_REVISE and e.max_traversals is not None
        else e
        for e in graph.edges
    ]
    return PipelineGraph(schema_version=graph.schema_version, nodes=list(graph.nodes), edges=edges)


def build_run_input(
    idea: IdeaBrief,
    cfg: PipelineConfig,
    seeded: SeededWork | None = None,
    *,
    registry_roles: Mapping[str, RoleConfig] | None = None,
    handler_types: Iterable[str] | None = None,
) -> GraphRunInput:
    if cfg.max_gate_rounds < 1:
        raise GraphStartError(
            [f"max_gate_rounds must be >= 1 on the graph path (got {cfg.max_gate_rounds})"]
        )
    graph = template_revise_bounds(select_graph(cfg, seeded, registry_roles), cfg.max_gate_rounds)
    roles = resolved_roles(cfg, registry_roles)
    report = validate(graph, NODE_TYPES, roles=roles)
    problems = [f"{p.code}: {p.message}" for p in report.problems]
    problems += [f"{p.code}: {p.message}" for p in executable(graph, handler_types)]
    if problems:
        raise GraphStartError(problems)
    return GraphRunInput(idea=idea, cfg=cfg, graph=graph, roles=roles, seeded=seeded)
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/graph_workflow/test_graph_catalog.py tests/graph_workflow/test_shipped_graph_routing.py -q`
Expected: PASS.

- [ ] **Step 6: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t14-msg.txt`:

```text
feat(workflows): E-74 shipped graphs and graph catalog

default, default-research and seeded graphs route today's stage order
under E-73 readiness (routing tables); select_graph mirrors the research
guard, revise bounds template from max_gate_rounds (U4), executable()
refuses gate.research and handler-less types, projection is identity on
every shipped graph.
```

```bash
git add src/sdlc/workflows/graphs/default.graph.yaml
git add src/sdlc/workflows/graphs/default-research.graph.yaml
git add src/sdlc/workflows/graphs/seeded.graph.yaml
git add src/sdlc/workflows/graph_catalog.py
git add tests/graph_workflow/test_graph_catalog.py
git add tests/graph_workflow/test_shipped_graph_routing.py
git commit -F .workspace/tmp/e74-t14-msg.txt
```

If Step 3 changed `pyproject.toml`, also run `git add pyproject.toml` before the commit.

### Task 15: `GraphDispatcher` — the dispatch loop

**Files:**
- Create: `src/sdlc/workflows/graph_dispatch.py`
- Test: `tests/graph_workflow/test_graph_dispatch.py` (temporal tier), `tests/graph_workflow/test_outcome_string.py` (fast tier)

**Interfaces:**
- Consumes: `NodeContext`, `NodeResult`, `StoredPayload`, `RunFacts`, `project_cfg`, `graph_has_research` (Task 13); `Halt`, `Emitted`, `GraphRouter` (Tasks 7–8).
- Produces:
  - `FAILURE_TYPES: tuple[type[BaseException], ...]`
  - `DispatchOutcome(state: RouterState, terminal_result: str | None, last_sink_result: str | None, budget_halted: bool, stored_failure: BaseException | None)`
  - `GraphDispatcher(*, host, services, router, graph, registry, handlers, facts, cfg)` with `async run() -> DispatchOutcome`
  - `outcome_string(outcome: DispatchOutcome, topology: Topology) -> str`
- Host contract: `async _check_budget(cfg)` (raises `_BudgetRejected`).

- [ ] **Step 1: Write the failing temporal test `tests/graph_workflow/test_graph_dispatch.py`**

```python
"""E-74 §5.4-§5.6: dispatch loop semantics on a probe workflow over test types."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import pytest
from temporalio import activity, workflow
from temporalio.api.enums.v1 import EventType
from temporalio.client import WorkflowFailureError
from temporalio.common import RetryPolicy
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError, CancelledError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.core.models import PipelineConfig
from sdlc.graph import GraphRouter, validate
from sdlc.workflows.graph_dispatch import GraphDispatcher, outcome_string
from sdlc.workflows.graph_nodes.base import NodeResult, RunFacts
from sdlc.workflows.role_host import _BudgetRejected
from tests.fakes.canned import greenfield_idea
from tests.graph.fixtures.registries import edge, graph, node, port_in, port_out, registry, roles, stage

pytestmark = pytest.mark.temporal
TQ = "e74-dispatch"

REG = registry(
    stage("start", port_out("ok", None)),
    stage("work", port_in("trigger", None), port_out("out", "P"), port_out("fail", "NodeFailure", terminal="failed")),
    stage("work.exiting", port_in("trigger", None), port_out("out", "P"), port_out("fail", "NodeFailure", terminal="failed")).model_copy(
        update={"budget_after": "exiting"}
    ),
    stage("handler", port_in("failure", "NodeFailure"), port_out("done", None)),
    stage("sink", port_in("art", "P"), port_out("done", None)),
    # back-edge probe: v -> (u, x); u.fix -> v.guidance retires x while x is live
    stage("loop", port_in("trigger", None), port_in("guidance", "GD", required=False), port_out("out", "P")),
    stage("fixer", port_in("trigger", "P"), port_out("fix", "GD"), port_out("done", None)),
    stage("waiter", port_in("trigger", "P"), port_out("done", None)),
)


@activity.defn
async def block_forever() -> None:
    while True:
        activity.heartbeat()
        await asyncio.sleep(0.1)


def _linear():
    return graph([node("start", "start"), node("w", "work"), node("s", "sink")],
                 [edge("start.ok", "w.trigger"), edge("w.out", "s.art")])


def _parallel(first_type: str = "work"):
    return graph(
        [node("start", "start"), node("a", first_type), node("b", "work"), node("sa", "sink"), node("sb", "sink")],
        [edge("start.ok", "a.trigger"), edge("start.ok", "b.trigger"), edge("a.out", "sa.art"), edge("b.out", "sb.art")],
    )


@workflow.defn(sandboxed=False)
class DispatchProbe:
    def __init__(self) -> None:
        self.log: list[str] = []
        self.released: set[str] = set()
        self.reject_budget = False

    @workflow.signal
    def release(self, name: str) -> None:
        self.released.add(name)

    @workflow.signal
    def set_reject_budget(self) -> None:
        self.reject_budget = True

    @workflow.query
    def events(self) -> list[str]:
        return list(self.log)

    async def _check_budget(self, cfg: PipelineConfig) -> None:
        self.log.append("budget")
        if self.reject_budget:
            raise _BudgetRejected()

    @workflow.run
    async def run(self, scenario: str) -> str:
        host = self

        async def start(nc, act, cfg):
            return NodeResult(port="ok")

        async def sink(nc, act, cfg):
            host.log.append(f"{nc.node.id}-done")
            return NodeResult(port="done", result=f"done:{nc.node.id}")

        async def work_ok(nc, act, cfg):
            return NodeResult(port="out")

        async def wait_release(nc, act, cfg):
            try:
                await workflow.wait_condition(lambda: nc.node.id in host.released)
            except asyncio.CancelledError:
                host.log.append(f"{nc.node.id}-cancelled")
                raise
            host.log.append(f"{nc.node.id}-released")
            return NodeResult(port="out")

        async def boom(nc, act, cfg):
            raise ApplicationError("boom", type="X", non_retryable=True)

        async def crash(nc, act, cfg):
            raise RuntimeError("interpreter bug")

        async def result_on_edge(nc, act, cfg):
            return NodeResult(port="out", result="not-allowed")

        async def handled(nc, act, cfg):
            return NodeResult(port="done", result="handled")

        async def fix_once(nc, act, cfg):
            if act.round == 1:
                await workflow.wait_condition(lambda: "x-waiting" in host.log)
                return NodeResult(port="fix")
            return NodeResult(port="done", result="done:u")

        async def wait_first_round(nc, act, cfg):
            if act.round == 1:
                host.log.append("x-waiting")
                try:
                    await workflow.wait_condition(lambda: False)
                except asyncio.CancelledError:
                    host.log.append("x-cancelled")
                    raise
            host.log.append(f"x-round-{act.round}")
            return NodeResult(port="done", result="done:x")

        async def blocking(nc, act, cfg):
            host.log.append("blocking-started")
            await workflow.execute_activity(
                block_forever, start_to_close_timeout=timedelta(hours=1),
                heartbeat_timeout=timedelta(seconds=2), retry_policy=RetryPolicy(maximum_attempts=1),
            )
            return NodeResult(port="out")

        async def exiting_with_finalize(nc, act, cfg):
            async def fin():
                host.log.append("finalize")
            await workflow.wait_condition(lambda: nc.node.id in host.released)
            return NodeResult(port="out", finalize=fin)

        table: dict[str, tuple[Any, dict[str, Any]]] = {
            "linear": (_linear(), {"start": start, "work": work_ok, "sink": sink}),
            "unrouted_failure": (_linear(), {"start": start, "work": boom, "sink": sink}),
            "routed_failure": (
                graph([node("start", "start"), node("w", "work"), node("h", "handler"), node("s", "sink")],
                      [edge("start.ok", "w.trigger"), edge("w.fail", "h.failure"), edge("w.out", "s.art")]),
                {"start": start, "work": boom, "handler": handled, "sink": sink},
            ),
            "crash": (_linear(), {"start": start, "work": crash, "sink": sink}),
            "result_on_edge": (_linear(), {"start": start, "work": result_on_edge, "sink": sink}),
            "budget_quiescence": (_parallel("work.exiting"), {"start": start, "work.exiting": work_ok, "work": wait_release, "sink": sink}),
            "budget_halt": (_parallel("work.exiting"), {"start": start, "work.exiting": exiting_with_finalize, "work": work_ok, "sink": sink}),
            "failure_cancels_sibling": (_parallel(), {"start": start, "work": None, "sink": sink}),
            "cancel_fanout": (_linear(), {"start": start, "work": blocking, "sink": sink}),
            "back_edge_cancel": (
                graph(
                    [node("start", "start"), node("v", "loop"), node("u", "fixer"), node("x", "waiter")],
                    [edge("start.ok", "v.trigger"), edge("v.out", "u.trigger"), edge("v.out", "x.trigger"),
                     edge("u.fix", "v.guidance", bound=1)],
                ),
                {"start": start, "loop": work_ok, "fixer": fix_once, "waiter": wait_first_round},
            ),
        }
        g, handlers = table[scenario]
        if scenario == "failure_cancels_sibling":
            async def a_or_b(nc, act, cfg):
                return await (boom(nc, act, cfg) if nc.node.id == "a" else wait_release(nc, act, cfg))
            handlers = {**handlers, "work": a_or_b}
        report = validate(g, REG, roles=roles())
        assert report.topology is not None, report.problems
        router = GraphRouter(report.topology)
        facts = RunFacts(idea=greenfield_idea(), repo_path="/r", run_id=workflow.info().workflow_id, seeded=None, memory_watermark=None)
        dispatcher = GraphDispatcher(host=self, services=None, router=router, graph=g, registry=REG,
                                     handlers=handlers, facts=facts, cfg=PipelineConfig())
        outcome = await dispatcher.run()
        if outcome.stored_failure is not None:
            raise outcome.stored_failure
        return outcome_string(outcome, router.topology)


async def _env_run(scenario: str, drive=None):
    async with await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TQ, workflows=[DispatchProbe], activities=[block_forever],
                              workflow_runner=UnsandboxedWorkflowRunner()):
                handle = await env.client.start_workflow(DispatchProbe.run, scenario, id=f"probe-{uuid.uuid4()}", task_queue=TQ)
                return await (drive(handle) if drive else handle.result()), handle


async def _has_event(handle, event_type) -> bool:
    history = await handle.fetch_history()
    return any(e.event_type == event_type for e in history.events)


@pytest.mark.asyncio
async def test_linear_graph_completes_with_the_sink_result():
    result, _ = await _env_run("linear")
    assert result == "done:s"


@pytest.mark.asyncio
async def test_unrouted_failure_reraises_the_original_exception():
    async def drive(handle):
        with pytest.raises(WorkflowFailureError) as info:
            await handle.result()
        return info.value.cause

    cause, _ = await _env_run("unrouted_failure", drive)
    assert isinstance(cause, ApplicationError)
    assert (cause.type, cause.message, cause.non_retryable) == ("X", "boom", True)
    assert cause.cause is None


@pytest.mark.asyncio
async def test_routed_failure_is_topology():
    result, _ = await _env_run("routed_failure")
    assert result == "handled"


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["crash", "result_on_edge"])
async def test_interpreter_bugs_fail_the_workflow_task_not_the_run(scenario):
    async def drive(handle):
        for _ in range(100):
            if await _has_event(handle, EventType.EVENT_TYPE_WORKFLOW_TASK_FAILED):
                break
            await asyncio.sleep(0.1)
        described = await handle.describe()
        await handle.terminate("probe done")
        return described.status

    status, handle = await _env_run(scenario, drive)
    assert status.name == "RUNNING"


@pytest.mark.asyncio
async def test_budget_boundary_waits_for_quiescence():
    async def drive(handle):
        await asyncio.sleep(1.0)
        assert "budget" not in await handle.query(DispatchProbe.events)
        await handle.signal(DispatchProbe.release, "b")
        return await handle.result()

    result, handle = await _env_run("budget_quiescence", drive)
    events = await handle.query(DispatchProbe.events)
    assert events.index("b-released") < events.index("budget")
    assert result.startswith("done:")


@pytest.mark.asyncio
async def test_budget_rejection_halts_and_skips_finalize():
    async def drive(handle):
        await handle.signal(DispatchProbe.set_reject_budget)
        await handle.signal(DispatchProbe.release, "a")
        return await handle.result()

    result, handle = await _env_run("budget_halt", drive)
    assert result == "rejected:budget"
    assert "finalize" not in await handle.query(DispatchProbe.events)


@pytest.mark.asyncio
async def test_failed_terminal_cancels_the_running_sibling():
    async def drive(handle):
        with pytest.raises(WorkflowFailureError):
            await handle.result()
        return await handle.query(DispatchProbe.events)

    events, _ = await _env_run("failure_cancels_sibling", drive)
    assert "b-cancelled" in events


@pytest.mark.asyncio
async def test_back_edge_traversal_cancels_a_live_region_activation():
    """§5.4 step 6: step.cancelled from a REGION invalidation cancels the live
    task; its late result is discarded (not live) and the node re-runs."""

    async def drive(handle):
        result = await handle.result()
        return result, await handle.query(DispatchProbe.events)

    (result, events), _ = await _env_run("back_edge_cancel", drive)
    assert events.index("x-cancelled") < events.index("x-round-2")
    assert "x-round-1" not in events
    assert result.startswith("done:")


@pytest.mark.asyncio
async def test_workflow_cancellation_fans_out_to_running_handlers():
    async def drive(handle):
        # ActivityTaskStarted reaches history only when the attempt closes,
        # so wait on the handler's own log line instead.
        for _ in range(200):
            if "blocking-started" in await handle.query(DispatchProbe.events):
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.5)  # let the activity attempt reach the worker
        await handle.cancel()
        with pytest.raises(WorkflowFailureError) as info:
            await handle.result()
        assert isinstance(info.value.cause, CancelledError)
        return await _has_event(handle, EventType.EVENT_TYPE_ACTIVITY_TASK_CANCEL_REQUESTED)

    cancel_requested, _ = await _env_run("cancel_fanout", drive)
    assert cancel_requested
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/graph_workflow/test_graph_dispatch.py -m temporal -q --timeout=300 --timeout-method=thread`
Expected: FAIL. `ModuleNotFoundError: No module named 'sdlc.workflows.graph_dispatch'`.

- [ ] **Step 3: Implement `src/sdlc/workflows/graph_dispatch.py`**

```python
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
from typing import Any

from temporalio import workflow
from temporalio.exceptions import FailureError, is_cancelled_exception

with workflow.unsafe.imports_passed_through():
    from pydantic import PydanticUserError
    from pydantic_ai.exceptions import AgentRunError, UserError

    from ..core.models import NodeFailure, PipelineConfig
    from ..graph.model import PipelineGraph
    from ..graph.node_types import NodeTypeSpec
    from ..graph.router import Activation, Emitted, GraphRouter, Halt, RouterState, Step
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
FAILURE_TYPES: tuple[type[BaseException], ...] = (FailureError, UserError, PydanticUserError, AgentRunError)


@dataclass
class DispatchOutcome:
    state: RouterState
    terminal_result: str | None
    last_sink_result: str | None
    budget_halted: bool
    stored_failure: BaseException | None


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

    @property
    def _t(self) -> Topology:
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

        async def _one() -> None:
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
            return NodeResult(
                port="fail",
                payload=NodeFailure(activation_id=aid, error_type=type(raw).__name__, message=str(raw)),
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
            task = self._tasks.pop(cid, None)
            if task is not None:
                task.cancel()
                self._cancelled.append(task)


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
        if ns.status == "done" and ns.taken_port is not None and not topology.out_ports[n][ns.taken_port]
    )
    return f"completed:{','.join(sinks)}"
```

An unrouted `fail` also leaves `terminal_result` unset: `outcome_string` is never reached, because `GraphWorkflow.run` raises `stored_failure` first (Task 19).

Known limitations, recorded and unreachable on the shipped linear graphs:
- A cancelled handler that swallows `ActivityError(CancelledError)` stalls the final `wait_condition`s. Examples are `_run_role` pricing and `_calibration_verdict`. FeatureWorkflow swallows at the same awaits today.
- A non-cancellation raise from `_loop` does not cancel running siblings; that covers an unrouted failure on a gate and an interpreter bug. This matches FeatureWorkflow.

Both matter only for future parallel user graphs (plan review: advisor Q3 M3/M4, skeptic F10).

- [ ] **Step 4: Run the test**

Run: `pytest tests/graph_workflow/test_graph_dispatch.py -m temporal -q --timeout=300 --timeout-method=thread`
Expected: PASS (10 passed). A hang is SG-4.

- [ ] **Step 5: Fast-tier pins: FAILURE_TYPES and the §5.6 wire-string table**

Create `tests/graph_workflow/test_outcome_string.py`:

```python
"""E-74 §5.6 wire contract and the D8 FAILURE_TYPES pin (fast tier)."""

from __future__ import annotations

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import FailureError
from temporalio.worker import Replayer

from sdlc.graph import validate
from sdlc.graph.router import NodeState, RouterState
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.graph_catalog import SHIPPED
from sdlc.workflows.graph_dispatch import FAILURE_TYPES, DispatchOutcome, outcome_string
from tests.graph.fixtures.registries import roles

TOPOLOGY = validate(SHIPPED["default"], roles=roles()).topology


def test_failure_types_cover_temporal_and_the_plugin():
    config = Replayer(
        workflows=[FeatureWorkflow], data_converter=pydantic_data_converter, plugins=[PydanticAIPlugin()]
    ).config(active_config=True)
    assert set(config["workflow_failure_exception_types"]) <= set(FAILURE_TYPES)
    assert FailureError in FAILURE_TYPES


def _state(outcome, reason=None, nodes=None) -> RouterState:
    return RouterState(nodes=nodes or {"intake": NodeState()}, outcome=outcome, reason=reason)


def _o(state, *, terminal=None, sink=None, budget=False) -> DispatchOutcome:
    return DispatchOutcome(state=state, terminal_result=terminal, last_sink_result=sink,
                           budget_halted=budget, stored_failure=None)


DONE = NodeState(round=1, status="done", taken_port="done")
MERGED = NodeState(round=1, status="done", taken_port="pr")


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (_o(_state("rejected", "budget"), budget=True), "rejected:budget"),
        (_o(_state("rejected", "architecture.reject"), budget=True), "rejected:budget"),
        (_o(_state("rejected", "intake.reject"), terminal="rejected:intake (not a git repository)"), "rejected:intake (not a git repository)"),
        (_o(_state("rejected", "merge.reject"), terminal="rejected:merge:advisory"), "rejected:merge:advisory"),
        (_o(_state("rejected", "architecture.reject")), "rejected:architecture"),
        (_o(_state("rejected", "plan.reject")), "rejected:plan"),
        (_o(_state("failed", "plan_check.halt"), terminal="failed:plan-validation:dependency cycle: a -> b -> a"), "failed:plan-validation:dependency cycle: a -> b -> a"),
        (_o(_state("failed", "code.halt"), terminal="failed:dependency-cycle"), "failed:dependency-cycle"),
        (_o(_state("failed", "code.halt"), terminal="failed:integration-conflict:t1"), "failed:integration-conflict:t1"),
        (_o(_state("failed", "code.halt"), terminal="failed:quarantined-tasks"), "failed:quarantined-tasks"),
        (_o(_state("escalated", "architecture.revise: exhausted")), "escalated:architecture.revise: exhausted"),
        (_o(_state("completed"), sink="deployed:https://example.test/pr/1"), "deployed:https://example.test/pr/1"),
        (_o(_state("completed"), sink="merged-not-deployed:https://example.test/pr/1"), "merged-not-deployed:https://example.test/pr/1"),
        (_o(_state("completed", nodes={"deploy": DONE, "merge": MERGED})), "completed:deploy"),
    ],
)
def test_outcome_string_table(outcome, expected):
    assert outcome_string(outcome, TOPOLOGY) == expected
```

Run: `pytest tests/graph_workflow/test_outcome_string.py -q`
Expected: PASS (15 passed).

- [ ] **Step 6: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t15-msg.txt`:

```text
feat(workflows): E-74 GraphDispatcher dispatch loop

Router state owned by run(); tasks catch and append; classification
routes FAILURE_TYPES to fail ports and re-raises the original object when
unrouted; budget boundary at quiescence before finalize and advance;
workflow cancellation fans out to running handlers. Probe tests pin each rule.
```

```bash
git add src/sdlc/workflows/graph_dispatch.py
git add tests/graph_workflow/test_graph_dispatch.py
git add tests/graph_workflow/test_outcome_string.py
git commit -F .workspace/tmp/e74-t15-msg.txt
```

### Task 16: Pre-code handlers (intake, context, research, clarify, architect, plan)

**Files:**
- Create: `src/sdlc/workflows/graph_nodes/precode.py`
- Test: `tests/graph_workflow/test_precode_handlers.py`

**Interfaces:**
- Consumes:
  - from Task 13: `NodeContext`, `NodeResult`, `input_model`, `guidance_text`;
  - `sdlc.stages.architecture.step.prepare/produce/finish` (Task 5);
  - `sdlc.stages.plan.step.prepare/produce/finish` (Task 6).
- Produces: `intake_node`, `context_node`, `research_node`, `clarify_node`, `architect_node`, `plan_node`, all `Handler`s.
  - `architect_node`/`plan_node` store their prep in `nc.carry(node_id)["prep"]` and set `NodeResult.author_model = prep.resolved_model`. Task 17's gate reads both.

- [ ] **Step 1: Write the failing test**

```python
"""E-74 §6: pre-code handlers adapt the stage steps; host mirrors and carry (§5.3, D4)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from sdlc.core.models import GateDecision, GateOutcome, IdeaBrief, PipelineConfig, ProjectMode
from sdlc.graph import NODE_TYPES, from_yaml, validate
from sdlc.graph.router import Activation
from sdlc.vcs import IntegrationHandle, IntegrationInput
from sdlc.workflows.graph_catalog import SHIPPED
from sdlc.workflows.graph_nodes import precode
from sdlc.workflows.graph_nodes.base import NodeContext, RunFacts, StoredPayload
from tests.fakes.canned import ARCH, CLARIFIED, greenfield_idea
from tests.graph.fixtures.registries import roles

PRE_CODE = Path(__file__).resolve().parents[1] / "graph" / "fixtures" / "pre_code.graph.yaml"


class Host:
    def __init__(self):
        self._integration_head = ""
        self._base_sha = ""
        self._integration_wt = ""
        self._codebase_map = None
        self._memory_watermark = "wm"
        self.published: list[tuple[str, bool]] = []

    async def _board_publish(self, cfg, key, content_json, *, approved=True):
        self.published.append((key, approved))
        return 7


def _nc(node_id: str, *, graph=None, idea: IdeaBrief | None = None, payloads=None, host=None, services=None):
    graph = graph or SHIPPED["default"]
    topology = validate(graph, roles=roles()).topology
    node = next(n for n in graph.nodes if n.id == node_id)
    facts = RunFacts(idea=idea or greenfield_idea(), repo_path="/fake/repo", run_id="wf-1", seeded=None, memory_watermark="wm")
    return NodeContext(ctx=services or SimpleNamespace(), host=host or Host(), facts=facts, node=node,
                       spec=NODE_TYPES[node.type], topology=topology, payloads=payloads or {}, carries={})


def _act(node_id: str, round_: int = 1, inputs=None) -> Activation:
    return Activation(activation_id=f"{node_id}#{round_}", node_id=node_id, round=round_, inputs=inputs or {}, unavailable_ports={})


def test_intake_sets_up_integration_after_passing_and_mirrors_the_host(monkeypatch):
    calls = []

    async def fake_step(ctx, *, cfg, idea, repo_path):
        calls.append(("intake", repo_path))
        return None

    async def fake_activity(fn, arg, **kw):
        calls.append(("activity", fn.__name__, arg))
        return IntegrationHandle(head_sha="h1", worktree_path="/wt")

    monkeypatch.setattr(precode, "intake", SimpleNamespace(step=fake_step))
    monkeypatch.setattr(precode.workflow, "execute_activity", fake_activity)
    nc = _nc("intake")
    out = asyncio.run(precode.intake_node(nc, _act("intake"), PipelineConfig()))
    assert out.port == "ok"
    assert calls[0] == ("intake", "/fake/repo")
    assert calls[1][2] == IntegrationInput(repo_path="/fake/repo", run_id="wf-1", base_branch="main")
    assert (nc.host._integration_head, nc.host._base_sha, nc.host._integration_wt) == ("h1", "h1", "/wt")
    assert nc.facts.base_sha == "h1"


def test_intake_rejection_creates_no_branch(monkeypatch):
    async def fake_step(ctx, *, cfg, idea, repo_path):
        return "rejected:intake (not a git repository)"

    async def no_activity(*a, **k):
        raise AssertionError("no branch on a rejected intake")

    monkeypatch.setattr(precode, "intake", SimpleNamespace(step=fake_step))
    monkeypatch.setattr(precode.workflow, "execute_activity", no_activity)
    out = asyncio.run(precode.intake_node(_nc("intake"), _act("intake"), PipelineConfig()))
    assert (out.port, out.result) == ("reject", "rejected:intake (not a git repository)")


def test_intake_rejects_a_mode_the_graph_has_no_path_for(monkeypatch):
    async def fake_step(ctx, *, cfg, idea, repo_path):
        return None

    async def no_activity(*a, **k):
        raise AssertionError("no branch without a path")

    monkeypatch.setattr(precode, "intake", SimpleNamespace(step=fake_step))
    monkeypatch.setattr(precode.workflow, "execute_activity", no_activity)
    brown = IdeaBrief(title="t", description="d", mode=ProjectMode.BROWNFIELD, repo_url="/r")
    nc = _nc("intake", graph=from_yaml(PRE_CODE.read_text(encoding="utf-8")), idea=brown)
    out = asyncio.run(precode.intake_node(nc, _act("intake"), PipelineConfig()))
    assert out.result == "rejected:intake (graph has no brownfield path)"


def test_clarify_passes_the_research_digest_publishes_and_retains(monkeypatch):
    seen = {}

    async def fake_step(ctx, **kw):
        seen.update(kw)
        return CLARIFIED

    retained = []

    async def retain(cfg, kind, bank, text, metadata):
        retained.append((text, metadata))

    monkeypatch.setattr(precode, "clarify", SimpleNamespace(step=fake_step))
    graph = SHIPPED["default-research"]
    payloads = {"research#1.brief": StoredPayload(model=None, producer="research#1", meta={"digest": "d1"})}
    nc = _nc("clarify", graph=graph, payloads=payloads, services=SimpleNamespace(retain=retain))
    act = _act("clarify", inputs={"research": "research#1.brief"})
    out = asyncio.run(precode.clarify_node(nc, act, PipelineConfig()))
    assert out.payload is CLARIFIED
    assert seen["brief_digest"] == "d1" and seen["codebase_map"] is None
    assert nc.host.published == [("requirements", True)]
    assert retained == [(f"clarify: {CLARIFIED.summary}", {"stage": "clarify", "run_id": "wf-1"})]


def test_architect_prepares_once_and_reads_guidance(monkeypatch):
    prepared, produced = [], []

    async def fake_prepare(ctx, **kw):
        prepared.append(kw)
        return SimpleNamespace(resolved_model="m-arch")

    async def fake_produce(ctx, prep, **kw):
        produced.append(kw["guidance"])
        return ARCH

    monkeypatch.setattr(precode, "arch_prepare", fake_prepare)
    monkeypatch.setattr(precode, "arch_produce", fake_produce)
    monkeypatch.setattr(precode, "resolve_role_model", lambda cfg, stage: f"model-{stage}")
    decision = GateDecision(gate="architecture", outcome=GateOutcome.REVISE, decided_by="human", guidance="g1")
    payloads = {
        "clarify#1.requirements": StoredPayload(model=CLARIFIED, producer="clarify#1"),
        "architecture#1.revise": StoredPayload(model=decision, producer="architecture#1"),
    }
    nc = _nc("architect", payloads=payloads)
    first = asyncio.run(precode.architect_node(nc, _act("architect", 1, {"requirements": "clarify#1.requirements"}), PipelineConfig()))
    second = asyncio.run(precode.architect_node(nc, _act("architect", 2, {"requirements": "clarify#1.requirements", "guidance": "architecture#1.revise"}), PipelineConfig()))
    assert len(prepared) == 1 and prepared[0]["architect_model"] == "model-architect"
    assert produced == [None, "g1"]
    assert (first.port, first.author_model, second.payload) == ("spec", "m-arch", ARCH)
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/graph_workflow/test_precode_handlers.py -q`
Expected: FAIL. `ImportError: cannot import name 'precode'`.

- [ ] **Step 3: Implement `src/sdlc/workflows/graph_nodes/precode.py`**

```python
"""Pre-code node handlers (E-74 spec §6): adapters over the stage steps.

Each handler reproduces the matching `_pipeline` section's commands in order
(golden command projection, spec §7.3). Host attribute mirrors follow §5.3.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ...agents.roles import (
        resolve_role_model,
        t_architect,
        t_clarify,
        t_clarify_probe,
        t_clarify_route,
        t_planner,
        t_research,
    )
    from ...core.models import PipelineConfig, ProjectMode
    from ...graph.router import Activation
    from ...memory.models import MemoryKind
    from ...stages import clarify, context, intake, research
    from ...stages.architecture.step import prepare as arch_prepare
    from ...stages.architecture.step import produce as arch_produce
    from ...stages.plan.step import prepare as plan_prepare
    from ...stages.plan.step import produce as plan_produce
    from ...stages.research.models import ResearchBrief
    from ...vcs import IntegrationInput, setup_integration_branch
    from .base import NodeContext, NodeResult, guidance_text, input_model

ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)


async def intake_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    idea = nc.facts.idea
    err = await intake.step(nc.ctx, cfg=cfg, idea=idea, repo_path=nc.facts.repo_path)
    if err is not None:
        return NodeResult(port="reject", result=err)
    brownfield = idea.mode is ProjectMode.BROWNFIELD
    port = "brownfield" if brownfield else "ok"
    if not nc.connected(port):
        mode = "brownfield" if brownfield else "greenfield"
        return NodeResult(port="reject", result=f"rejected:intake (graph has no {mode} path)")
    # ADR-14: the branch is cut only after intake passes (feature.py:490-510) --
    # never more reachable for the stale-branch defect than today (spec §11).
    integration = await workflow.execute_activity(
        setup_integration_branch,
        IntegrationInput(repo_path=nc.facts.repo_path, run_id=nc.facts.run_id, base_branch=idea.base_branch),
        **ACT,
    )
    nc.facts.set_integration(integration)
    nc.host._integration_head = integration.head_sha
    nc.host._base_sha = integration.head_sha
    nc.host._integration_wt = integration.worktree_path
    return NodeResult(port=port)


async def context_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    res = await context.step(
        nc.ctx,
        cfg=cfg,
        idea=nc.facts.idea,
        repo_path=nc.facts.repo_path,
        commit_sha=nc.host._integration_head,
    )
    if isinstance(res, str):
        return NodeResult(port="reject", result=res)
    if res is None:
        return NodeResult(port="reject", result="rejected:context (greenfield run has no codebase to map)")
    nc.host._codebase_map = res
    return NodeResult(port="map", payload=res)


async def research_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    if t_research is None:
        raise RuntimeError("research node on a worker without agents/research (select_graph guards this)")
    out = await research.step(
        nc.ctx,
        cfg=cfg,
        idea=nc.facts.idea,
        memory_watermark=nc.host._memory_watermark,
        research_agent=t_research,
        research_model=resolve_role_model(cfg, "research"),
    )
    if out.rejection:
        return NodeResult(port="reject", result=out.rejection)
    brief = ResearchBrief.model_validate(out.model_dump(exclude={"digest", "rejection"}))
    return NodeResult(port="brief", payload=brief, meta={"digest": out.digest})


async def clarify_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    research_ref = act.inputs.get("research")
    digest = nc.payload(research_ref).meta.get("digest", "") if isinstance(research_ref, str) else ""
    reqs = await clarify.step(
        nc.ctx,
        cfg=cfg,
        idea=nc.facts.idea,
        codebase_map=input_model(nc, act, "codebase_map"),
        brief_digest=digest,
        clarify_agent=t_clarify,
        route_agent=t_clarify_route,
        probe_agent=t_clarify_probe,
        clarify_model=resolve_role_model(cfg, "clarify"),
    )
    await nc.host._board_publish(cfg, "requirements", reqs.model_dump_json())
    await nc.ctx.retain(
        cfg,
        MemoryKind.STAGE_SUMMARY,
        cfg.memory.project_bank,
        text=f"clarify: {reqs.summary}",
        metadata={"stage": "clarify", "run_id": nc.facts.run_id},
    )
    return NodeResult(port="requirements", payload=reqs)


async def architect_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    carry = nc.carry(nc.node.id)
    codebase_map = input_model(nc, act, "codebase_map")
    if "prep" not in carry:  # once per stage (§7.2, C1)
        carry["prep"] = await arch_prepare(
            nc.ctx,
            cfg=cfg,
            codebase_map=codebase_map,
            idea=nc.facts.idea,
            architect_model=resolve_role_model(cfg, "architect"),
        )
    prep = carry["prep"]
    spec = await arch_produce(
        nc.ctx,
        prep,
        cfg=cfg,
        requirements=input_model(nc, act, "requirements"),
        codebase_map=codebase_map,
        memory_watermark=nc.host._memory_watermark,
        repo_path=nc.facts.repo_path,
        architect_agent=t_architect,
        guidance=guidance_text(nc, act),
    )
    return NodeResult(port="spec", payload=spec, author_model=prep.resolved_model)


async def plan_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    carry = nc.carry(nc.node.id)
    if "prep" not in carry:
        carry["prep"] = await plan_prepare(
            nc.ctx, cfg=cfg, idea=nc.facts.idea, planner_model=resolve_role_model(cfg, "plan")
        )
    prep = carry["prep"]
    plan = await plan_produce(
        nc.ctx,
        prep,
        cfg=cfg,
        architecture=input_model(nc, act, "spec"),
        requirements=input_model(nc, act, "requirements"),
        planner_agent=t_planner,
        guidance=guidance_text(nc, act),
    )
    return NodeResult(port="plan", payload=plan, author_model=prep.resolved_model)
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/graph_workflow/test_precode_handlers.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t16-msg.txt`:

```text
feat(workflows): E-74 pre-code node handlers

intake (branch cut after passing, host mirrors), context, research
(composite, digest in payload meta), clarify (publish + retain), architect
and plan (prepare once via carry, produce per round, author model on the
payload).
```

```bash
git add src/sdlc/workflows/graph_nodes/precode.py
git add tests/graph_workflow/test_precode_handlers.py
git commit -F .workspace/tmp/e74-t16-msg.txt
```

### Task 17: The generic gate handler

**Files:**
- Create: `src/sdlc/workflows/graph_nodes/gate.py`
- Test: `tests/graph_workflow/test_gate_handler.py`

**Interfaces:**
- Consumes: carry `"prep"` and `StoredPayload.author_model` (Task 16); `finish` from Tasks 5/6.
- Produces:
  - `gate_node`, the `Handler` for `gate.architecture` and `gate.plan`
  - `GATE_FINISH: Mapping[str, GateFinish]`, keyed by gate type
  - `GateFinish(finish, board_key: str, sets_plan_version: bool)`

- [ ] **Step 1: Write the failing test**

```python
"""E-74 §6.1: the generic gate reproduces _revisable_stage (role_host.py:219-271)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sdlc.core.models import GateConfig, GateDecision, GateOutcome, GatePolicy, PipelineConfig
from sdlc.graph import NODE_TYPES
from sdlc.graph.router import Activation
from sdlc.pending import GateContext
from sdlc.workflows.graph_catalog import SHIPPED
from sdlc.workflows.graph_nodes import gate as gate_module
from sdlc.workflows.graph_nodes.base import NodeContext, RunFacts, StoredPayload
from tests.fakes.canned import ARCH, PLAN, greenfield_idea
from tests.graph.fixtures.registries import roles
from sdlc.graph import validate


class Recorder:
    def __init__(self, outcome: GateOutcome):
        self.outcome = outcome
        self.gate_calls: list[tuple[str, dict]] = []
        self.finished: list[tuple[str, bool]] = []

    async def gate(self, name, settings, **kw):
        self.gate_calls.append((name, kw))
        return GateDecision(gate=name, round=kw["round"], outcome=self.outcome, decided_by="human", guidance="g")


class Host:
    def __init__(self):
        self.calibration: list[tuple[str, str]] = []
        self.published: list[tuple[str, bool]] = []
        self._plan_version = None

    async def _calibration_verdict(self, cfg, gate, author_model):
        self.calibration.append((gate, author_model))
        return "verdict"

    async def _board_publish(self, cfg, key, content_json, *, approved=True):
        self.published.append((key, approved))
        return 11


def _nc(gate_id: str, producer: str, artifact, rec: Recorder, host: Host):
    graph = SHIPPED["default"]
    node = next(n for n in graph.nodes if n.id == gate_id)
    payloads = {f"{producer}#1.x": StoredPayload(model=artifact, producer=f"{producer}#1", author_model="m-author")}
    nc = NodeContext(ctx=rec, host=host, facts=RunFacts(idea=greenfield_idea(), repo_path="/r", run_id="wf", seeded=None, memory_watermark=None),
                     node=node, spec=NODE_TYPES[node.type], topology=validate(graph, roles=roles()).topology,
                     payloads=payloads, carries={producer: {"prep": "PREP"}})
    return nc, f"{producer}#1.x"


def _act(gate_id: str, ref: str, round_: int, final: bool) -> Activation:
    return Activation(activation_id=f"{gate_id}#{round_}", node_id=gate_id, round=round_, inputs={"artifact": ref},
                      unavailable_ports={"revise": "exhausted"} if final else {})


@pytest.fixture
def finishes(monkeypatch):
    done: list[tuple[str, object, bool]] = []

    def make(board_key, sets_plan_version):
        async def fin(ctx, prep, *, cfg, artifact, gate):
            done.append((board_key, prep, gate.approved))
        return gate_module.GateFinish(finish=fin, board_key=board_key, sets_plan_version=sets_plan_version)

    monkeypatch.setattr(gate_module, "GATE_FINISH", {"gate.architecture": make("architecture", False), "gate.plan": make("plan", True)})
    monkeypatch.setattr(gate_module, "auto_decision_for", lambda name, cfg, confidence, calibration: "AUTO")
    return done


def test_in_loop_soft_round_reads_calibration_and_passes_confidence(finishes):
    rec, host = Recorder(GateOutcome.APPROVE), Host()
    nc, ref = _nc("plan", "planner", PLAN, rec, host)
    cfg = PipelineConfig()  # plan is SOFT by default
    out = asyncio.run(gate_module.gate_node(nc, _act("plan", ref, 1, final=False), cfg))
    name, kw = rec.gate_calls[0]
    assert name == "plan" and host.calibration == [("plan", "m-author")]
    assert kw == {"auto_decision": "AUTO", "round": 1, "context": GateContext(spec_summary=gate_module._spec_summary(PLAN)),
                  "confidence": PLAN.confidence, "author_model": "m-author"}
    assert (out.port, out.payload) == ("approve", PLAN)
    assert finishes == [("plan", "PREP", True)]
    asyncio.run(out.finalize())
    assert host.published == [("plan", True)] and host._plan_version == 11


def test_hard_round_reads_no_calibration(finishes):
    rec, host = Recorder(GateOutcome.APPROVE), Host()
    nc, ref = _nc("architecture", "architect", ARCH, rec, host)
    asyncio.run(gate_module.gate_node(nc, _act("architecture", ref, 1, final=False), PipelineConfig()))
    assert host.calibration == []
    assert rec.gate_calls[0][1]["auto_decision"] is None


def test_default_soft_policy_without_an_entry_reads_no_calibration(finishes):
    rec, host = Recorder(GateOutcome.APPROVE), Host()
    nc, ref = _nc("architecture", "architect", ARCH, rec, host)
    cfg = PipelineConfig(default_gate_policy=GatePolicy.SOFT)
    cfg.gates.pop("architecture")
    asyncio.run(gate_module.gate_node(nc, _act("architecture", ref, 1, final=False), cfg))
    assert host.calibration == []  # C3: GateConfig().policy is HARD


def test_in_loop_revise_emits_the_decision_without_finish(finishes):
    rec, host = Recorder(GateOutcome.REVISE), Host()
    nc, ref = _nc("architecture", "architect", ARCH, rec, host)
    out = asyncio.run(gate_module.gate_node(nc, _act("architecture", ref, 1, final=False), PipelineConfig()))
    assert out.port == "revise" and out.payload.outcome is GateOutcome.REVISE
    assert finishes == [] and out.finalize is None


def test_final_round_skips_calibration_and_maps_revise_to_reject(finishes):
    rec, host = Recorder(GateOutcome.REVISE), Host()
    nc, ref = _nc("plan", "planner", PLAN, rec, host)
    out = asyncio.run(gate_module.gate_node(nc, _act("plan", ref, 3, final=True), PipelineConfig()))
    name, kw = rec.gate_calls[0]
    assert host.calibration == []
    assert kw == {"round": 3, "context": GateContext(spec_summary=gate_module._spec_summary(PLAN)), "author_model": "m-author"}
    assert out.port == "reject" and finishes == [("plan", "PREP", False)]
    asyncio.run(out.finalize())
    assert host.published == [("plan", False)]
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/graph_workflow/test_gate_handler.py -q`
Expected: FAIL. `ImportError: cannot import name 'gate'`.

- [ ] **Step 3: Implement `src/sdlc/workflows/graph_nodes/gate.py`**

```python
"""The generic gate handler (E-74 spec §6.1): _revisable_stage as topology.

In-loop rounds (revise available) read calibration only under the verbatim
predicate of role_host.py:245-249 and pass confidence; the final round
(revise unavailable) reads nothing, passes no confidence and no
auto_decision, and maps REVISE to reject (E-73 §6.5). Post-gate work runs
on approve/reject only; the board publish rides `finalize` so it lands
after the dispatcher's budget boundary (feature.py:588-591).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ...calibration.decision import auto_decision_for
    from ...core.models import GateConfig, GateOutcome, GatePolicy, PipelineConfig
    from ...graph.router import Activation
    from ...pending import GateContext
    from ...stages.architecture.step import finish as architecture_finish
    from ...stages.plan.step import finish as plan_finish
    from ..role_host import _spec_summary
    from .base import NodeContext, NodeResult


@dataclass(frozen=True)
class GateFinish:
    finish: Callable[..., Awaitable[None]]
    board_key: str
    sets_plan_version: bool


GATE_FINISH: Mapping[str, GateFinish] = MappingProxyType(
    {
        "gate.architecture": GateFinish(architecture_finish, "architecture", False),
        "gate.plan": GateFinish(plan_finish, "plan", True),
    }
)


async def gate_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    ref = act.inputs["artifact"]
    assert isinstance(ref, str)
    stored = nc.payload(ref)
    artifact: Any = stored.model
    author = stored.author_model or ""
    name = nc.node.id  # E-72 D7: gate identity is the node id
    confidence = getattr(artifact, "confidence", None)
    context = GateContext(spec_summary=_spec_summary(artifact))
    final = "revise" in act.unavailable_ports

    if not final:
        auto = None
        if confidence is not None and cfg.gates.get(name, GateConfig()).policy is GatePolicy.SOFT:
            calibration = await nc.host._calibration_verdict(cfg, name, author)
            auto = auto_decision_for(name, cfg, confidence, calibration)
        decision = await nc.ctx.gate(
            name,
            cfg.gate_settings(),
            auto_decision=auto,
            round=act.round,
            context=context,
            confidence=confidence,
            author_model=author,
        )
    else:
        decision = await nc.ctx.gate(
            name, cfg.gate_settings(), round=act.round, context=context, author_model=author
        )

    if decision.outcome is GateOutcome.REVISE and not final and nc.connected("revise"):
        return NodeResult(port="revise", payload=decision)

    approved = decision.outcome is GateOutcome.APPROVE
    port = "approve" if approved else "reject"
    fin = GATE_FINISH[nc.spec.type]
    producer_node = stored.producer.rpartition("#")[0]
    await fin.finish(nc.ctx, nc.carry(producer_node)["prep"], cfg=cfg, artifact=artifact, gate=decision)

    async def _publish() -> None:
        version = await nc.host._board_publish(
            cfg, fin.board_key, artifact.model_dump_json(), approved=decision.approved
        )
        if fin.sets_plan_version:
            nc.host._plan_version = version

    return NodeResult(
        port=port,
        payload=artifact if approved else None,
        author_model=author if approved else None,
        finalize=_publish,
    )
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/graph_workflow/test_gate_handler.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t17-msg.txt`:

```text
feat(workflows): E-74 generic gate handler

Reproduces _revisable_stage: verbatim SOFT calibration predicate in loop,
byte-exact final round (no calibration read, no confidence), REVISE on a
final round maps to reject, finish per gate type via the producer's carry,
board publish deferred to finalize.
```

```bash
git add src/sdlc/workflows/graph_nodes/gate.py
git add tests/graph_workflow/test_gate_handler.py
git commit -F .workspace/tmp/e74-t17-msg.txt
```

### Task 18: Post-plan handlers and the handler table

**Files:**
- Create: `src/sdlc/workflows/graph_nodes/postplan.py`
- Modify: `src/sdlc/workflows/graph_nodes/__init__.py` (`HANDLERS`, `NOT_EXECUTABLE` re-export)
- Test: `tests/graph_workflow/test_postplan_handlers.py`

**Interfaces:**
- Consumes: `run_tasks` (Task 4), `validate_task_graph` (Task 4), payload models (Task 9).
- Produces:
  - `plan_check_node`, `seed_spec_node`, `seed_plan_node`, `code_node`, `analyze_node`, `merge_node`, `deploy_node`
  - `HANDLERS: Mapping[str, Handler]` covering every `NODE_TYPES` key except `gate.research`

- [ ] **Step 1: Write the failing test**

```python
"""E-74 §6: post-plan handlers and handler coverage."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sdlc.core.models import PipelineConfig
from sdlc.graph import NODE_TYPES
from sdlc.graph.router import Activation
from sdlc.stages.analyze.models import AnalysisReport
from sdlc.stages.plan.models import DevTask, ImplementationPlan
from sdlc.vcs import IntegrationHandle
from sdlc.workflows.graph_catalog import NOT_EXECUTABLE, SHIPPED
from sdlc.workflows.graph_nodes import HANDLERS, postplan
from sdlc.workflows.graph_nodes.base import NodeContext, RunFacts, StoredPayload
from sdlc.workflows.models import AnalyzeResult, BuildResult, PullRequest, SeededWork, TaskResult
from tests.fakes.canned import ARCH, PLAN, greenfield_idea


def test_handlers_cover_every_executable_type():
    assert sorted(HANDLERS) == sorted(t for t in NODE_TYPES if t not in NOT_EXECUTABLE)


class Host:
    def __init__(self):
        self._plan_version = 3
        self.synced = None
        self.stages: list[tuple[str, str]] = []

    async def _board_sync_tasks(self, cfg, version, tasks):
        self.synced = (version, [t.id for t in tasks])

    def _stage(self, status, trace=None):
        self.stages.append((status, trace))


def _nc(node_id: str, graph="default", payloads=None, host=None, seeded=None):
    g = SHIPPED[graph]
    node = next(n for n in g.nodes if n.id == node_id)
    facts = RunFacts(idea=greenfield_idea(), repo_path="/r", run_id="wf", seeded=seeded, memory_watermark=None)
    facts.set_integration(IntegrationHandle(head_sha="base", worktree_path="/wt"))
    return NodeContext(ctx=SimpleNamespace(), host=host or Host(), facts=facts, node=node, spec=NODE_TYPES[node.type],
                       topology=None, payloads=payloads or {}, carries={})


def _act(node_id, inputs=None):
    return Activation(activation_id=f"{node_id}#1", node_id=node_id, round=1, inputs=inputs or {}, unavailable_ports={})


def test_plan_check_halts_on_an_invalid_graph_and_syncs_a_valid_one():
    bad = ImplementationPlan(tasks=[DevTask(id="a", title="a", description="a", acceptance_criteria=["x"], depends_on=["z"])])
    nc = _nc("plan_check", payloads={"plan#1.approve": StoredPayload(model=bad, producer="plan#1")})
    out = asyncio.run(postplan.plan_check_node(nc, _act("plan_check", {"plan": "plan#1.approve"}), PipelineConfig()))
    assert (out.port, out.result) == ("halt", "failed:plan-validation:task 'a' depends on unknown task id(s) ['z']")
    nc = _nc("plan_check", payloads={"plan#1.approve": StoredPayload(model=PLAN, producer="plan#1")})
    out = asyncio.run(postplan.plan_check_node(nc, _act("plan_check", {"plan": "plan#1.approve"}), PipelineConfig()))
    assert (out.port, out.payload, nc.host.synced) == ("ok", PLAN, (3, ["t1"]))


def test_seed_nodes_emit_the_seeded_work():
    seeded = SeededWork(arch=ARCH, plan=PLAN)
    spec_nc = _nc("seed_spec", graph="seeded", seeded=seeded)
    plan_nc = _nc("seed_plan", graph="seeded", seeded=seeded)
    assert asyncio.run(postplan.seed_spec_node(spec_nc, _act("seed_spec"), PipelineConfig())).payload is ARCH
    out = asyncio.run(postplan.seed_plan_node(plan_nc, _act("seed_plan"), PipelineConfig()))
    assert out.payload is PLAN and plan_nc.host.stages == [("coding", "code")]


def test_code_maps_run_tasks_outcomes(monkeypatch):
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b")

    async def ok(host, *, cfg, plan, repo_path):
        return {"t1": tr}, None

    async def conflict(host, *, cfg, plan, repo_path):
        return {}, "failed:integration-conflict:t1"

    payloads = {"plan_check#1.ok": StoredPayload(model=PLAN, producer="plan_check#1")}
    monkeypatch.setattr(postplan, "run_tasks", ok)
    out = asyncio.run(postplan.code_node(_nc("code", payloads=payloads), _act("code", {"plan": "plan_check#1.ok"}), PipelineConfig()))
    assert out.port == "results" and out.payload.task_results == [tr]
    monkeypatch.setattr(postplan, "run_tasks", conflict)
    out = asyncio.run(postplan.code_node(_nc("code", payloads=payloads), _act("code", {"plan": "plan_check#1.ok"}), PipelineConfig()))
    assert (out.port, out.result) == ("halt", "failed:integration-conflict:t1")


def test_merge_rejection_and_pr(monkeypatch):
    analysis = AnalyzeResult(report=AnalysisReport(traceability=[], summary="s", confidence=0.5), untraced=["c"], integration_diff={"files": []})
    payloads = {
        "code#1.results": StoredPayload(model=BuildResult(task_results=[]), producer="code#1"),
        "plan_check#1.ok": StoredPayload(model=PLAN, producer="plan_check#1"),
        "architecture#1.approve": StoredPayload(model=ARCH, producer="architecture#1"),
        "analyze#1.analysis": StoredPayload(model=analysis, producer="analyze#1"),
    }
    inputs = {"results": "code#1.results", "plan": "plan_check#1.ok", "spec": "architecture#1.approve", "analysis": "analyze#1.analysis"}
    seen = {}

    async def fake_merge(ctx, **kw):
        seen.update(kw)
        return seen.get("next", "rejected:merge:advisory")

    monkeypatch.setattr(postplan, "merge", SimpleNamespace(step=fake_merge))
    out = asyncio.run(postplan.merge_node(_nc("merge", payloads=payloads), _act("merge", inputs), PipelineConfig()))
    assert (out.port, out.result) == ("reject", "rejected:merge:advisory")
    assert seen["untraced"] == ["c"] and seen["base_sha"] == "base" and seen["arch"] is ARCH

    async def pr_merge(ctx, **kw):
        return "https://example.test/pr/1"

    monkeypatch.setattr(postplan, "merge", SimpleNamespace(step=pr_merge))
    out = asyncio.run(postplan.merge_node(_nc("merge", payloads=payloads), _act("merge", inputs), PipelineConfig()))
    assert out.port == "pr" and out.payload == PullRequest(url="https://example.test/pr/1")


@pytest.mark.parametrize("prefix", ["deployed", "merged-not-deployed", "deploy-broken", "deploy-rejected", "rolled-back"])
def test_every_deploy_result_rides_the_done_sink_unchanged(monkeypatch, prefix):
    async def fake_deploy(ctx, **kw):
        return f"{prefix}:{kw['pr_url']}"

    monkeypatch.setattr(postplan, "deploy", SimpleNamespace(step=fake_deploy, _deploy_plan=lambda cfg, wid: "PLAN"))
    payloads = {"merge#1.pr": StoredPayload(model=PullRequest(url="u"), producer="merge#1")}
    out = asyncio.run(postplan.deploy_node(_nc("deploy", payloads=payloads), _act("deploy", {"pr": "merge#1.pr"}), PipelineConfig()))
    assert (out.port, out.result) == ("done", f"{prefix}:u")
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/graph_workflow/test_postplan_handlers.py -q`
Expected: FAIL. `ImportError: cannot import name 'HANDLERS'`.

- [ ] **Step 3: Implement `src/sdlc/workflows/graph_nodes/postplan.py`**

```python
"""Post-plan node handlers (E-74 spec §6; coarse `code` per U1)."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ...agents.roles import STAGE_MODELS, resolve_role_model, t_analyst, t_merge_verdict
    from ...core.models import PipelineConfig
    from ...graph.router import Activation
    from ...stages import analyze, deploy, merge
    from ...stages.analyze.models import untraced_criteria
    from ...stages.plan.validation import validate_task_graph
    from ...vcs import DiffInput, get_task_diff
    from ..build import run_tasks
    from ..models import AnalyzeResult, BuildResult, PullRequest
    from .base import NodeContext, NodeResult, input_model

ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)


async def plan_check_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    plan = input_model(nc, act, "plan")
    graph_error = validate_task_graph(plan.tasks)
    if graph_error:
        return NodeResult(port="halt", result=f"failed:plan-validation:{graph_error}")
    # Sync only after the graph is valid (feature.py:614-617).
    await nc.host._board_sync_tasks(cfg, nc.host._plan_version, plan.tasks)
    return NodeResult(port="ok", payload=plan)


async def seed_spec_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    seeded = nc.facts.seeded
    if seeded is None:
        raise RuntimeError("seed.spec activated on a run without SeededWork")
    return NodeResult(port="spec", payload=seeded.arch)


async def seed_plan_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    seeded = nc.facts.seeded
    if seeded is None:
        raise RuntimeError("seed.plan activated on a run without SeededWork")
    nc.host._stage("coding", "code")  # feature.py:518 -- the seeded path's only stage event here
    return NodeResult(port="plan", payload=seeded.plan)


async def code_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    done, failure = await run_tasks(
        nc.host, cfg=cfg, plan=input_model(nc, act, "plan"), repo_path=nc.facts.repo_path
    )
    if failure is not None:
        return NodeResult(port="halt", result=failure)
    return NodeResult(port="results", payload=BuildResult(task_results=list(done.values())))


async def analyze_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    results = input_model(nc, act, "results")
    plan = input_model(nc, act, "plan")
    integration = nc.facts.integration
    assert integration is not None, "intake sets RunFacts.integration before any post-plan node"
    integration_diff = await workflow.execute_activity(
        get_task_diff,
        DiffInput(worktree=integration.worktree_path, branch_point=nc.facts.base_sha),
        **ACT,
    )
    done = {r.task_id: r for r in results.task_results}
    authoritative: list[tuple[str, str]] = [
        (t.id, c) for t in plan.tasks for c in t.acceptance_criteria
    ]
    analysis = await analyze.step(
        nc.ctx,
        cfg=cfg,
        plan=plan,
        task_results=done,
        diff=integration_diff,
        integration_wt=integration.worktree_path,
        base_branch=nc.facts.idea.base_branch,
        analyst_agent=t_analyst,
        analyst_model=resolve_role_model(cfg, "analyze"),
    )
    return NodeResult(
        port="analysis",
        payload=AnalyzeResult(
            report=analysis,
            untraced=untraced_criteria(authoritative, analysis),
            integration_diff=integration_diff,
        ),
    )


async def merge_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    results = input_model(nc, act, "results")
    analysis = input_model(nc, act, "analysis")
    integration = nc.facts.integration
    assert integration is not None, "intake sets RunFacts.integration before any post-plan node"
    pr_url = await merge.step(
        nc.ctx,
        cfg=cfg,
        task_results=list(results.task_results),
        integration_wt=integration.worktree_path,
        idea=nc.facts.idea,
        arch=input_model(nc, act, "spec"),
        plan=input_model(nc, act, "plan"),
        base_sha=nc.facts.base_sha or "",
        integration_diff=analysis.integration_diff,
        untraced=analysis.untraced,
        merge_agent=t_merge_verdict,
        merge_model=STAGE_MODELS.get("merge_verdict", "unknown"),
    )
    if pr_url.startswith("rejected:"):
        return NodeResult(port="reject", result=pr_url)
    return NodeResult(port="pr", payload=PullRequest(url=pr_url))


async def deploy_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    pr = input_model(nc, act, "pr")
    out = await deploy.step(
        nc.ctx,
        cfg=cfg,
        deploy_plan=deploy._deploy_plan(cfg, nc.facts.run_id),
        repo_path=nc.facts.repo_path,
        pr_url=pr.url,
    )
    return NodeResult(port="done", result=out)
```

Replace `src/sdlc/workflows/graph_nodes/__init__.py` with:

```python
"""Graph node handlers (E-74 spec §6). HANDLERS binds node types to handlers;
worker boot asserts set(NODE_TYPES) == set(HANDLERS) | set(NOT_EXECUTABLE)."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from .base import Handler
from .gate import gate_node
from .postplan import (
    analyze_node,
    code_node,
    deploy_node,
    merge_node,
    plan_check_node,
    seed_plan_node,
    seed_spec_node,
)
from .precode import (
    architect_node,
    clarify_node,
    context_node,
    intake_node,
    plan_node,
    research_node,
)

HANDLERS: Mapping[str, Handler] = MappingProxyType(
    {
        "analyze": analyze_node,
        "architect": architect_node,
        "clarify": clarify_node,
        "code": code_node,
        "context": context_node,
        "deploy": deploy_node,
        "gate.architecture": gate_node,
        "gate.plan": gate_node,
        "intake": intake_node,
        "merge": merge_node,
        "plan": plan_node,
        "plan_check": plan_check_node,
        "research": research_node,
        "seed.plan": seed_plan_node,
        "seed.spec": seed_spec_node,
    }
)

__all__ = ["HANDLERS"]
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/graph_workflow -q`
Expected: PASS for every fast-tier file in the directory. `test_graph_dispatch.py` is temporal and skipped here.

- [ ] **Step 5: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t18-msg.txt`:

```text
feat(workflows): E-74 post-plan handlers and handler table

plan_check (validate then sync), seed.spec/seed.plan, coarse code over
build.run_tasks, analyze (diff once, untraced), merge (reject vs PR),
deploy (every result string on the done sink). HANDLERS covers every
executable node type.
```

```bash
git add src/sdlc/workflows/graph_nodes/postplan.py
git add src/sdlc/workflows/graph_nodes/__init__.py
git add tests/graph_workflow/test_postplan_handlers.py
git commit -F .workspace/tmp/e74-t18-msg.txt
```

### Task 19: `GraphWorkflow`, worker registration and boot checks

**Files:**
- Create: `src/sdlc/workflows/graph.py`
- Modify: `src/sdlc/worker.py` (import, registration, `graph_boot_problems()`, call it in `main()`)
- Modify: `tests/replay/harness.py` (add `GRAPH_STARTER`)
- Modify: `tests/test_run_state_query.py` (parametrize over both classes)
- Test: `tests/graph_workflow/test_graph_workflow_class.py` (fast), `tests/graph_workflow/test_graph_workflow_smoke.py` (temporal)

**Interfaces:**
- Consumes: everything from Tasks 13–18.
- Produces:
  - `GraphWorkflow` with `run(inp: GraphRunInput) -> str`
  - queries `run_state`, `run_summary`; inherited `status`, `pending_gate`, `pending_decisions`
  - signals `submit_gate_decision`, `answer_question`
  - `sdlc.worker.graph_boot_problems() -> list[str]`
  - `harness.GRAPH_STARTER: Starter`

- [ ] **Step 1: Write the failing fast test `tests/graph_workflow/test_graph_workflow_class.py`**

```python
"""E-74 §5.7: GraphWorkflow exposes FeatureWorkflow's HITL surface by the same names."""

from __future__ import annotations

import ast
from pathlib import Path

from temporalio.workflow import _Definition

from sdlc.worker import graph_boot_problems
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.gates import GateHost
from sdlc.workflows.graph import GraphWorkflow
from sdlc.workflows.run_host import RunHost


def test_graph_workflow_serves_the_same_queries_and_signals():
    g = _Definition.must_from_class(GraphWorkflow)
    f = _Definition.must_from_class(FeatureWorkflow)
    assert set(g.queries) == set(f.queries)
    assert set(g.signals) == set(f.signals)


def test_run_host_precedes_gate_host():
    mro = GraphWorkflow.__mro__
    assert mro.index(RunHost) < mro.index(GateHost)


def test_bare_instance_run_state_is_none():
    assert GraphWorkflow().run_state() is None


def test_boot_checks_are_healthy():
    assert graph_boot_problems() == []


def test_worker_registers_both_pipeline_workflows():
    src = (Path(__file__).resolve().parents[2] / "src" / "sdlc" / "worker.py").read_text(encoding="utf-8")
    names = {n.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Name)}
    assert {"FeatureWorkflow", "GraphWorkflow", "graph_boot_problems"} <= names
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/graph_workflow/test_graph_workflow_class.py -q`
Expected: FAIL. `ImportError: cannot import name 'graph_boot_problems' from 'sdlc.worker'`.

- [ ] **Step 3: Implement `src/sdlc/workflows/graph.py`**

```python
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
    from ..agents import loader as _loader  # noqa: F401 -- validate()'s lazy import stays passthrough
    from ..core.context import StageServices
    from ..core.models import RunState, RunSummary
    from ..graph.node_types import NODE_TYPES
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
        """Live run state for the dashboard fleet view (E-10)."""
        return self._snapshot_run_state()

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
        outcome = await dispatcher.run()
        if outcome.stored_failure is not None:
            raise outcome.stored_failure  # D8: same failure as FeatureWorkflow; retro not run (U9)
        result = outcome_string(outcome, router.topology)
        await self._retro(cfg, idea, result)
        return result
```

- [ ] **Step 4: Wire the worker**

In `src/sdlc/worker.py`:
1. Add `from .workflows.graph import GraphWorkflow` beside the other workflow imports.
2. Add above `main()`:

```python
def graph_boot_problems() -> list[str]:
    """E-72 D2 / E-74 D14: the registry self-check plus handler coverage, at boot."""
    from .graph.node_types import NODE_TYPES, check_node_types
    from .workflows.graph_catalog import NOT_EXECUTABLE
    from .workflows.graph_nodes import HANDLERS

    problems = list(check_node_types())
    expected = sorted(NODE_TYPES)
    covered = sorted({*HANDLERS, *NOT_EXECUTABLE})
    if expected != covered:
        problems.append(f"handler coverage mismatch: registry {expected} vs handled {covered}")
    return problems
```

3. In `main()`, after `validate_crew_clis()`:

```python
    # E-74: a registry the graph interpreter cannot run must never boot a worker.
    graph_problems = graph_boot_problems()
    if graph_problems:
        raise SystemExit("graph registry unhealthy: " + "; ".join(graph_problems))
```

4. Add `GraphWorkflow,` right after `FeatureWorkflow,` in the `workflows=[...]` list.

- [ ] **Step 5: Add `GRAPH_STARTER` to `tests/replay/harness.py`**

Append:

```python
async def _start_graph(client: Client, scenario: Scenario, wf_id: str) -> WorkflowHandle:
    from sdlc.workflows.graph import GraphWorkflow
    from sdlc.workflows.graph_catalog import build_run_input

    run_input = build_run_input(scenario.idea(), scenario.cfg(), scenario.seeded())
    return await client.start_workflow(GraphWorkflow.run, run_input, id=wf_id, task_queue=TASK_QUEUE)


def _graph_workflows() -> tuple[type, ...]:
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.graph import GraphWorkflow

    return (GraphWorkflow, DeploymentWorkflow)


GRAPH_STARTER = Starter("GraphWorkflow", _graph_workflows(), _start_graph)
```

- [ ] **Step 6: Parametrize `tests/test_run_state_query.py` over both classes**

1. Add `import pytest` and `from sdlc.workflows.graph import GraphWorkflow`.
2. Add the fixture:

```python
@pytest.fixture(params=[FeatureWorkflow, GraphWorkflow], ids=["feature", "graph"])
def wf_cls(request):
    return request.param
```

3. Change `_wf(**overrides)` to `_wf(cls, **overrides)`; its first line becomes `wf = cls()`.
4. Every test function gains a `wf_cls` parameter. Replace each `FeatureWorkflow()` with `wf_cls()` and each `_wf(` with `_wf(wf_cls, `. Do not change any assertion.

- [ ] **Step 7: Write the temporal smoke test `tests/graph_workflow/test_graph_workflow_smoke.py`**

```python
"""A SANDBOXED GraphWorkflow run ships end to end (E-74 §4.2 F1 residue: the
production sandbox, not the unsandboxed capture runner)."""

from __future__ import annotations

import pytest

from tests.replay.harness import GRAPH_STARTER, capture
from tests.replay.scenarios import SCENARIOS

pytestmark = pytest.mark.temporal
GREENFIELD = next(s for s in SCENARIOS if s.name == "greenfield_happy")


@pytest.mark.asyncio
async def test_sandboxed_graph_workflow_greenfield_deploys(monkeypatch, tmp_path):
    captured = await capture(GREENFIELD, GRAPH_STARTER, monkeypatch, tmp_path, sandboxed=True)
    assert captured.golden["close"].startswith("deployed:"), captured.golden["close"]
```

- [ ] **Step 8: Run the tests**

Run: `pytest tests/graph_workflow/test_graph_workflow_class.py tests/test_run_state_query.py -q`
Expected: PASS.

Run: `pytest tests/graph_workflow/test_graph_workflow_smoke.py -m temporal -q --timeout=300 --timeout-method=thread`
Expected: PASS.

If this fails with a sandbox error (`RestrictedWorkflowAccessError`, or a pydantic `ValidationError` whose input type equals the expected class name), a sandbox-executed module is missing a passthrough import. Add that import under `imports_passed_through()` in the named module and re-run. Any other failure is SG-5.

- [ ] **Step 9: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t19-msg.txt`:

```text
feat(workflows): E-74 GraphWorkflow

Thin Temporal layer: validates and executable-checks the pinned graph,
captures the watermark, runs the dispatcher, re-raises an unrouted
failure unchanged, maps the outcome string, runs retro. Registered beside
FeatureWorkflow with registry and handler-coverage checks at worker boot;
sandboxed greenfield smoke run deploys.
```

```bash
git add src/sdlc/workflows/graph.py
git add src/sdlc/worker.py
git add tests/replay/harness.py
git add tests/test_run_state_query.py
git add tests/graph_workflow/test_graph_workflow_class.py
git add tests/graph_workflow/test_graph_workflow_smoke.py
git commit -F .workspace/tmp/e74-t19-msg.txt
```

### Task 20: Golden-trace equality — the reproduction proof (constraint 7)

**Files:**
- Create: `tests/replay/test_graph_golden.py` (temporal tier)
- Test: the same file (golden equality, live query, memo-key parity)

**Interfaces:**
- Consumes: `GRAPH_STARTER`, `FEATURE_STARTER`, `capture`, `load_golden`, `GOLDEN_SCENARIOS` (Tasks 1, 19).

- [ ] **Step 1: Write the test**

```python
"""E-74 §7.3: GraphWorkflow reproduces FeatureWorkflow's golden traces EXACTLY.

Stop-guard SG-3: any difference is a STOP. Never edit a golden file.
"""

from __future__ import annotations

import dataclasses

import pytest
from temporalio import activity

from sdlc.core.models import MemoryConfig
from sdlc.memoization.activities import CacheGetInput, CachePutInput
from tests.fakes.canned import e2e_config
from tests.replay.harness import FEATURE_STARTER, GRAPH_STARTER, capture, load_golden
from tests.replay.scenarios import GOLDEN_SCENARIOS, SCENARIOS, A, answer_clarify, decide, wait_for

pytestmark = pytest.mark.temporal
GREENFIELD = next(s for s in SCENARIOS if s.name == "greenfield_happy")


@pytest.mark.asyncio
@pytest.mark.parametrize("sandboxed", [False, True], ids=["unsandboxed", "sandboxed"])
@pytest.mark.parametrize("scenario", GOLDEN_SCENARIOS, ids=[s.name for s in GOLDEN_SCENARIOS])
async def test_graph_workflow_reproduces_the_golden_trace(scenario, sandboxed, monkeypatch, tmp_path):
    """Unsandboxed runs record the stage/gate trace (the recorder patches a class);
    sandboxed runs prove the same commands and close under the production sandbox."""
    captured = await capture(scenario, GRAPH_STARTER, monkeypatch, tmp_path, sandboxed=sandboxed)
    golden = load_golden(scenario.name)
    assert captured.golden["commands"] == golden["commands"], "SG-3: command projection differs"
    assert captured.golden["close"] == golden["close"], "SG-3: close differs"
    if not sandboxed:
        assert captured.golden["trace"] == golden["trace"], "SG-3: stage/gate trace differs"


@pytest.mark.asyncio
async def test_live_queries_on_a_sandboxed_graph_workflow(monkeypatch, tmp_path):
    observed: dict = {}

    async def drive(handle, env):
        await answer_clarify(handle)
        await wait_for(handle, "awaiting:architecture")
        observed["state"] = await handle.query("run_state")
        observed["pending"] = await handle.query("pending_decisions")
        for gate in ("architecture", "plan", "deploy"):
            await decide(handle, gate, 1, A)

    scenario = dataclasses.replace(GREENFIELD, name="live_query", drive=drive)
    captured = await capture(scenario, GRAPH_STARTER, monkeypatch, tmp_path, sandboxed=True)
    assert observed["state"]["current_stage"] == "architecture"
    assert observed["pending"], "the architecture gate must be pending"
    golden = load_golden("greenfield_happy")
    assert captured.golden["commands"] == golden["commands"]
    assert captured.golden["close"] == golden["close"]


@activity.defn(name="cache_get")
async def fake_cache_get(inp: CacheGetInput) -> str | None:
    return None


@activity.defn(name="cache_put")
async def fake_cache_put(inp: CachePutInput) -> None:
    return None


@activity.defn(name="reflect")
async def fake_reflect(*args: object) -> None:
    return None  # retro schedules reflect when memory is on (retro/step.py:75-85)


@pytest.mark.asyncio
async def test_memo_key_inputs_match_feature_workflow(monkeypatch, tmp_path):
    """§5.3 host mirrors: with memoization and memory ON, every content_key
    input (incl. the watermark) is identical across the two workflows."""
    from sdlc.memory.activities import recall_snapshot, retain
    import sdlc.workflows.role_host as role_host

    seen: dict[str, list[tuple]] = {"FeatureWorkflow": [], "GraphWorkflow": []}
    current = {"name": ""}
    original = role_host.content_key

    def recording(*args):
        seen[current["name"]].append(args)
        return original(*args)

    monkeypatch.setattr(role_host, "content_key", recording)

    def memo_cfg():
        cfg = e2e_config()
        cfg.deploy.enabled = True
        cfg.memoization_enabled = True
        cfg.memory = MemoryConfig(enabled=True, backend="fake", watermark="wm-e74")
        return cfg

    scenario = dataclasses.replace(
        GREENFIELD,
        name="memo_parity",
        cfg=memo_cfg,
        activities=lambda: [*GREENFIELD.activities(), fake_cache_get, fake_cache_put, fake_reflect, recall_snapshot, retain],
    )
    for starter in (FEATURE_STARTER, GRAPH_STARTER):
        current["name"] = starter.name
        await capture(scenario, starter, monkeypatch, tmp_path / starter.name)
    assert seen["FeatureWorkflow"], "memoization must have computed keys"
    assert seen["GraphWorkflow"] == seen["FeatureWorkflow"]
    assert all(args[-1] == "wm-e74" for args in seen["GraphWorkflow"])
```

- [ ] **Step 2: Run the golden equality, one scenario per invocation**

For each id in `GOLDEN_SCENARIOS` (the 15 names of Task 1 Step 9 without `partial_awaiting_architecture`):

Run: `pytest "tests/replay/test_graph_golden.py::test_graph_workflow_reproduces_the_golden_trace[greenfield_happy-unsandboxed]" -m temporal -q --timeout=300 --timeout-method=thread`
Expected: PASS. Then run the same test id with `-sandboxed`. Run one invocation per scenario × mode (30 total).

Any assertion failure is **SG-3**. STOP and report:
- the scenario;
- the first differing index of the command projection, with 5 entries of context from both sides;
- the trace diff.

Do not edit golden files. Do not change a handler to "match" without reporting first.

- [ ] **Step 3: Run the live-query and memo-parity tests**

Run: `pytest "tests/replay/test_graph_golden.py::test_live_queries_on_a_sandboxed_graph_workflow" -m temporal -q --timeout=300 --timeout-method=thread`
Expected: PASS.

Run: `pytest "tests/replay/test_graph_golden.py::test_memo_key_inputs_match_feature_workflow" -m temporal -q --timeout=300 --timeout-method=thread`
Expected: PASS. If `recall_snapshot`/`retain` with `backend="fake"` cannot run offline, that is SG-5: STOP and report the error. Do not drop the memory flag; the watermark mirror is what this test exists for.

- [ ] **Step 4: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t20-msg.txt`:

```text
test(replay): E-74 GraphWorkflow reproduces every golden trace

Exact equality on stage/gate trace, ordered command projection and close
for all 15 golden scenarios; live run_state/pending_decisions on a
sandboxed run; memo-key inputs (watermark included) identical to
FeatureWorkflow with memoization and memory on.
```

```bash
git add tests/replay/test_graph_golden.py
git commit -F .workspace/tmp/e74-t20-msg.txt
```

### Task 21: Cutover of the start sites, inbox and fleet

**Files:**
- Modify: `src/sdlc/cli.py:51` (import), `:414-456` (`start`), `:764`, `:782`
- Modify: `interfaces/dashboard/api/main.py:36,53-59`
- Modify: `src/sdlc/dashboard/api.py:232-239`
- Modify: `src/sdlc/operator/tools.py:538-546`
- Modify: `src/sdlc/channels/inbox.py:91,110`
- Modify: `src/sdlc/dashboard/fleet.py:58-61`
- Modify: `tests/test_fleet_capacity_wiring.py`, `tests/test_dashboard_api.py`, `tests/test_operator_tools_runs.py`, `tests/test_channel_inbox.py`
- Test: `tests/graph_workflow/test_cutover_wiring.py`

**Interfaces:**
- Consumes: `build_run_input`, `GraphStartError` (Task 14); `GraphWorkflow` (Task 19).

- [ ] **Step 1: Write the failing tests**

`tests/graph_workflow/test_cutover_wiring.py`:

```python
"""E-74 §8.1: every new start goes to GraphWorkflow; queries see both types."""

from __future__ import annotations

import inspect
from pathlib import Path

from sdlc import cli
from sdlc.channels import inbox
from sdlc.dashboard import fleet

ROOT = Path(__file__).resolve().parents[2]


def test_cli_start_builds_a_graph_run_input_and_starts_graph_workflow():
    src = inspect.getsource(cli.main)
    assert "build_run_input(" in src
    assert "GraphWorkflow.run" in src
    assert "FeatureWorkflow.run" not in src  # cli.py:635 keeps an unrelated prose mention


def test_dashboard_starter_starts_graph_workflow():
    src = (ROOT / "interfaces" / "dashboard" / "api" / "main.py").read_text(encoding="utf-8")
    assert "GraphWorkflow.run" in src and "build_run_input(" in src
    assert "FeatureWorkflow" not in src


def test_open_run_queries_include_both_types():
    assert "GraphWorkflow" in inspect.getsource(inbox.list_open_run_ids)
    assert "GraphWorkflow" in inspect.getsource(inbox)


def test_closed_run_queries_keep_both_types_permanently():
    for query in (fleet._CLOSED_QUERY, fleet._CLOSED_QUERY_UNORDERED):
        assert "WorkflowType='FeatureWorkflow'" in query and "WorkflowType='GraphWorkflow'" in query
```

Append to `tests/test_dashboard_api.py`:

```python
def test_start_run_422s_on_an_unstartable_graph(snap):
    from sdlc.workflows.graph_catalog import GraphStartError

    async def starter(idea, cfg, wf_id):
        raise GraphStartError(["no_handler: no handler for node type 'x'"])

    app = FastAPI()
    app.include_router(create_router(_FakePoller(snap), starter=starter))
    r = TestClient(app).post("/runs", json={"title": "t", "description": "d", "mode": "greenfield"})
    assert r.status_code == 422
    assert "no_handler" in r.text
```

Append to `tests/test_operator_tools_runs.py`:

```python
@pytest.mark.asyncio
async def test_start_run_turns_an_unstartable_graph_into_a_tool_error(deps):
    from sdlc.core.models import ProjectMode
    from sdlc.workflows.graph_catalog import GraphStartError

    async def starter(idea, cfg, wf_id):
        raise GraphStartError(["max_gate_rounds must be >= 1 on the graph path (got 0)"])

    deps.starter = starter
    with pytest.raises(ToolError) as e:
        await tools.start_run(deps, "Add SSO", ProjectMode.GREENFIELD)
    assert "max_gate_rounds" in e.value.message
```

If `OperatorDeps` is frozen, build a new one instead: `OperatorDeps(poller=deps.poller, board=None, starter=starter)`.

In `tests/test_fleet_capacity_wiring.py`, replace the literal `"FeatureWorkflow.run"` with `"GraphWorkflow.run"`, and the message text `"the capacity guard must precede the FeatureWorkflow start"` with `"the capacity guard must precede the GraphWorkflow start"`. Update the module docstring's first line to name `GraphWorkflow`.

In `tests/test_channel_inbox.py`, next to the existing `assert "FeatureWorkflow" in query` (`:121`), add `assert "GraphWorkflow" in query`.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/graph_workflow/test_cutover_wiring.py tests/test_dashboard_api.py tests/test_operator_tools_runs.py tests/test_fleet_capacity_wiring.py tests/test_channel_inbox.py -q`
Expected: FAIL (cutover assertions, 422 and ToolError rows).

- [ ] **Step 3: Implement the cutover**

`src/sdlc/cli.py`:
1. Replace `from .workflows.feature import FeatureWorkflow` with `from .workflows.graph import GraphWorkflow`.
2. In `if args.cmd == "start":`, keep the role-override block, `wf_id`, and the fleet guard exactly as they are. Replace the `handle = await client.start_workflow(FeatureWorkflow.run, args=[IdeaBrief(...), cfg, None], id=wf_id, task_queue=TASK_QUEUE)` statement with:

```python
        from .workflows.graph_catalog import GraphStartError, build_run_input

        idea = IdeaBrief(
            title=args.title,
            description=args.description,
            mode=ProjectMode(args.mode),
            repo_url=args.repo,
        )
        try:
            run_input = build_run_input(idea, cfg)
        except GraphStartError as e:
            print(f"cannot start: {e}")
            raise SystemExit(1) from None
        handle = await client.start_workflow(
            GraphWorkflow.run, run_input, id=wf_id, task_queue=TASK_QUEUE
        )
```

3. `:764` becomes `handle = client.get_workflow_handle_for(GraphWorkflow.run, args.id)` and `:782` becomes `print(await handle.query(GraphWorkflow.status))`. Signals and queries go by name, so in-flight FeatureWorkflow runs are still served.

`interfaces/dashboard/api/main.py`: replace the FeatureWorkflow import with `from sdlc.workflows.graph import GraphWorkflow` and `from sdlc.workflows.graph_catalog import build_run_input`. `_start` becomes:

```python
async def _start(idea: IdeaBrief, cfg: PipelineConfig, wf_id: str) -> str:
    client = await poller._client_or_connect()
    run_input = build_run_input(idea, cfg)  # GraphStartError -> 422 in dashboard/api.py
    handle = await client.start_workflow(
        GraphWorkflow.run, run_input, id=wf_id, task_queue=TASK_QUEUE
    )
    return handle.id
```

`src/sdlc/dashboard/api.py`: in `start`, insert between `except HTTPException: raise` and `except Exception as e:`:

```python
        except GraphStartError as e:
            raise HTTPException(422, str(e)) from e
```

Add `from ..workflows.graph_catalog import GraphStartError` to the module imports. If that import pulls `temporalio` into a module the dashboard purity tests forbid, move it inside `start` instead and note it.

`src/sdlc/operator/tools.py` `start_run`: insert before `except Exception as e:  # noqa: BLE001 -- narrowed into ToolError`:

```python
    except GraphStartError as e:
        raise ToolError(f"this run cannot start: {e}") from None
```

Import `GraphStartError` the same way as in `api.py`, with the same purity caveat.

`src/sdlc/channels/inbox.py`:
- `:91` → `query = _open_runs_query(*(types or ("FeatureWorkflow", "GraphWorkflow")))`
- `:110` → `run_ids = await list_open_run_ids(client, "FeatureWorkflow", "GraphWorkflow", "CrewTaskWorkflow")`
- Update the docstring sentence "Defaults to FeatureWorkflow alone" to "Defaults to FeatureWorkflow and GraphWorkflow (E-74 grace)".

`src/sdlc/dashboard/fleet.py`:

```python
_PIPELINE_TYPES = "(WorkflowType='FeatureWorkflow' OR WorkflowType='GraphWorkflow')"
_CLOSED_QUERY = f"{_PIPELINE_TYPES} AND ExecutionStatus!='Running' ORDER BY CloseTime DESC"
_CLOSED_QUERY_UNORDERED = f"{_PIPELINE_TYPES} AND ExecutionStatus!='Running'"
```

Keep FeatureWorkflow in the closed-run query permanently: pre-cutover runs must stay visible (skeptic F9).

- [ ] **Step 4: Run the tests**

Run: `pytest tests/graph_workflow/test_cutover_wiring.py tests/test_dashboard_api.py tests/test_operator_tools_runs.py tests/test_fleet_capacity_wiring.py tests/test_channel_inbox.py tests/test_inbox_query.py -q`
Expected: PASS.

Run: `pytest -q`
Expected: green. A failure is SG-5.

- [ ] **Step 5: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t21-msg.txt`:

```text
feat: E-74 cut every new start over to GraphWorkflow

sdlc start, the dashboard/operator starter build a validated GraphRunInput
and start GraphWorkflow (unstartable graph: exit 1 / HTTP 422 / ToolError);
gate commands retype to GraphWorkflow; open-run queries list both types
while grace lasts, closed-run queries keep both permanently.
```

```bash
git add src/sdlc/cli.py
git add interfaces/dashboard/api/main.py
git add src/sdlc/dashboard/api.py
git add src/sdlc/operator/tools.py
git add src/sdlc/channels/inbox.py
git add src/sdlc/dashboard/fleet.py
git add tests/graph_workflow/test_cutover_wiring.py
git add tests/test_dashboard_api.py
git add tests/test_operator_tools_runs.py
git add tests/test_fleet_capacity_wiring.py
git add tests/test_channel_inbox.py
git commit -F .workspace/tmp/e74-t21-msg.txt
```

### Task 22: Per-child patches in the parent workflows

**Files:**
- Create: `src/sdlc/workflows/pipeline_child.py`
- Modify: `src/sdlc/workflows/tidyup.py:41,228-240`
- Modify: `src/sdlc/benchmarks/workflow.py:33,269-274`
- Test: `tests/graph_workflow/test_pipeline_child_upgrade.py` (temporal), `tests/graph_workflow/test_parent_wiring.py` (fast)

**Interfaces:**
- Produces: `async execute_pipeline_child(*, child_id: str, idea: IdeaBrief, cfg: PipelineConfig, seeded: SeededWork | None, task_queue: str) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/graph_workflow/test_parent_wiring.py`:

```python
from __future__ import annotations

import inspect

from sdlc.benchmarks import workflow as benchmark_workflow
from sdlc.workflows import tidyup


def test_parents_start_pipeline_children_through_the_patched_helper():
    for module in (tidyup, benchmark_workflow):
        src = inspect.getsource(module)
        assert "execute_pipeline_child(" in src, module.__name__
        assert "FeatureWorkflow.run" not in src, module.__name__
```

`tests/graph_workflow/test_pipeline_child_upgrade.py`:

```python
"""E-74 §8.2: a parent in flight at cutover replays its started children as
FeatureWorkflow and starts every later child as GraphWorkflow (per-child ids)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from temporalio import workflow
from temporalio.api.enums.v1 import EventType
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.workflows.pipeline_child import execute_pipeline_child
from tests.fakes.canned import e2e_config, greenfield_idea

pytestmark = pytest.mark.temporal
TQ = "e74-parent"


@workflow.defn(name="FeatureWorkflow", sandboxed=False)
class StubFeature:
    @workflow.run
    async def run(self, idea: Any = None, cfg: Any = None, seeded: Any = None) -> str:
        return "feature-child"


@workflow.defn(name="GraphWorkflow", sandboxed=False)
class StubGraph:
    @workflow.run
    async def run(self, inp: Any = None) -> str:
        return "graph-child"


@workflow.defn(name="ParentProbe", sandboxed=False)
class ParentBeforeCutover:
    def __init__(self) -> None:
        self.go = False

    @workflow.signal
    def proceed(self) -> None:
        self.go = True

    @workflow.run
    async def run(self) -> list[str]:
        wid = workflow.info().workflow_id
        out = [await workflow.execute_child_workflow("FeatureWorkflow", args=[greenfield_idea(), e2e_config(), None], id=f"{wid}-c1", task_queue=TQ)]
        await workflow.wait_condition(lambda: self.go)
        out.append(await workflow.execute_child_workflow("FeatureWorkflow", args=[greenfield_idea(), e2e_config(), None], id=f"{wid}-c2", task_queue=TQ))
        return out


@workflow.defn(name="ParentProbe", sandboxed=False)
class ParentAfterCutover:
    def __init__(self) -> None:
        self.go = False

    @workflow.signal
    def proceed(self) -> None:
        self.go = True

    @workflow.run
    async def run(self) -> list[str]:
        wid = workflow.info().workflow_id
        out = [await execute_pipeline_child(child_id=f"{wid}-c1", idea=greenfield_idea(), cfg=e2e_config(), seeded=None, task_queue=TQ)]
        await workflow.wait_condition(lambda: self.go)
        out.append(await execute_pipeline_child(child_id=f"{wid}-c2", idea=greenfield_idea(), cfg=e2e_config(), seeded=None, task_queue=TQ))
        return out


def _child_types(history) -> list[str]:
    return [
        e.start_child_workflow_execution_initiated_event_attributes.workflow_type.name
        for e in history.events
        if e.event_type == EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED
    ]


@pytest.mark.asyncio
async def test_started_children_replay_as_feature_and_later_children_are_graph():
    async with await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            wid = f"parent-{uuid.uuid4()}"
            async with Worker(env.client, task_queue=TQ, workflows=[ParentBeforeCutover, StubFeature],
                              workflow_runner=UnsandboxedWorkflowRunner(), max_cached_workflows=0):
                handle = await env.client.start_workflow("ParentProbe", id=wid, task_queue=TQ, result_type=list)
                for _ in range(200):
                    events = (await handle.fetch_history()).events
                    if any(e.event_type == EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_COMPLETED for e in events):
                        break
                    await asyncio.sleep(0.05)
            async with Worker(env.client, task_queue=TQ, workflows=[ParentAfterCutover, StubFeature, StubGraph],
                              workflow_runner=UnsandboxedWorkflowRunner(), max_cached_workflows=0):
                await handle.signal("proceed")
                result = await handle.result()
            history = await handle.fetch_history()
    assert result == ["feature-child", "graph-child"]
    assert _child_types(history) == ["FeatureWorkflow", "GraphWorkflow"]
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/graph_workflow/test_parent_wiring.py -q`
Expected: FAIL (`execute_pipeline_child(` not found).

Run: `pytest tests/graph_workflow/test_pipeline_child_upgrade.py -m temporal -q --timeout=300 --timeout-method=thread`
Expected: FAIL. `ModuleNotFoundError: No module named 'sdlc.workflows.pipeline_child'`.

- [ ] **Step 3: Implement `src/sdlc/workflows/pipeline_child.py`**

```python
"""Start one pipeline child from a parent workflow (E-74 spec §8.2, D13).

The patch id is PER CHILD: workflow.patched memoises per id per execution
(temporalio/worker/_workflow_instance.py:1362), so a single id would let an
in-flight parent keep starting FeatureWorkflow children after cutover. A child
already in history replays as FeatureWorkflow; every child not yet started
goes to GraphWorkflow. The else-branch is deleted with FeatureWorkflow (§8.5).
"""

from __future__ import annotations

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..agents import loader as _loader  # noqa: F401 -- validate()'s lazy import stays passthrough
    from ..agents.roles import REGISTRY
    from ..core.models import IdeaBrief, PipelineConfig
    from .feature import FeatureWorkflow
    from .graph import GraphWorkflow
    from .graph_catalog import build_run_input
    from .graph_nodes import HANDLERS
    from .models import SeededWork


async def execute_pipeline_child(
    *,
    child_id: str,
    idea: IdeaBrief,
    cfg: PipelineConfig,
    seeded: SeededWork | None,
    task_queue: str,
) -> str:
    if workflow.patched(f"e74-graph-child:{child_id}"):
        run_input = build_run_input(
            idea, cfg, seeded, registry_roles=REGISTRY, handler_types=HANDLERS
        )  # GraphStartError propagates into the parent's existing failure branch
        return await workflow.execute_child_workflow(
            GraphWorkflow.run, run_input, id=child_id, task_queue=task_queue
        )
    return await workflow.execute_child_workflow(
        FeatureWorkflow.run, args=[idea, cfg, seeded], id=child_id, task_queue=task_queue
    )
```

`src/sdlc/workflows/tidyup.py`:
1. Replace `from .feature import FeatureWorkflow` (`:41`) with `from .pipeline_child import execute_pipeline_child`.
2. In `_fix_run`, replace the `workflow.execute_child_workflow(FeatureWorkflow.run, args=[IdeaBrief(...), inp.fix_cfg, seeded_work_for(...)], id=wf_id, task_queue=...)` call with:

```python
            outcome = await execute_pipeline_child(
                child_id=wf_id,
                idea=IdeaBrief(
                    title=f"tidy-up: {finding.rule}",
                    description=finding.detail,
                    mode=ProjectMode.BROWNFIELD,
                    repo_url=inp.repo_dir,
                    base_branch=inp.base_branch,
                ),
                cfg=inp.fix_cfg,
                seeded=seeded_work_for(identity, finding, signal_version),
                task_queue=workflow.info().task_queue,
            )
```

The surrounding `try/except Exception` stays. Update the module docstring's "brownfield FeatureWorkflow child runs" to "brownfield pipeline child runs (GraphWorkflow; FeatureWorkflow for children started before E-74)".

`src/sdlc/benchmarks/workflow.py`:
1. Replace `from ..workflows.feature import FeatureWorkflow` with `from ..workflows.pipeline_child import execute_pipeline_child`.
2. Replace the child call with:

```python
                await execute_pipeline_child(
                    child_id=child_id,
                    idea=idea,
                    cfg=cfg,
                    seeded=None,
                    task_queue=workflow.info().task_queue,
                )
```

Update its module docstring "start a FeatureWorkflow child" to "start a pipeline child".

- [ ] **Step 4: Run the tests**

Run: `pytest tests/graph_workflow/test_parent_wiring.py tests/test_tidyup_workflow.py tests/test_benchmark_workflow.py -q`
Expected: PASS.

Run: `pytest tests/graph_workflow/test_pipeline_child_upgrade.py -m temporal -q --timeout=300 --timeout-method=thread`
Expected: PASS.

Run: `pytest tests/replay/test_feature_replay.py -q`
Expected: PASS (17). Tidy-up and benchmark are not in the FeatureWorkflow histories, so any red here is SG-2.

- [ ] **Step 5: Gates and commit**

Run separately: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

Message file `.workspace/tmp/e74-t22-msg.txt`:

```text
feat(workflows): E-74 per-child patched pipeline children

TidyUp and Benchmark start children through execute_pipeline_child:
workflow.patched("e74-graph-child:<child_id>") replays children already in
history as FeatureWorkflow and sends every later child to GraphWorkflow.
Upgrade test swaps worker code mid-run to prove it.
```

```bash
git add src/sdlc/workflows/pipeline_child.py
git add src/sdlc/workflows/tidyup.py
git add src/sdlc/benchmarks/workflow.py
git add tests/graph_workflow/test_parent_wiring.py
git add tests/graph_workflow/test_pipeline_child_upgrade.py
git commit -F .workspace/tmp/e74-t22-msg.txt
```

### Task 23: Determinism lint, cold import, benchmark purity, landing docs — CHECKPOINT M2

**Files:**
- Create: `tests/graph_workflow/test_determinism_lint.py`
- Create: `tests/graph_workflow/test_cold_import.py`
- Modify: `tests/test_factory_purity.py` (append)
- Modify: `src/sdlc/workflows/run_host.py` (one allowlist comment)
- Modify docs:
  - `docs/roadmap/pipeline-as-data.md`
  - `ROADMAP.md:396,398`
  - `ARCHITECTURE.md:36,59,73,772`
  - `AGENTS.md:107`
  - `src/sdlc/workflows/AGENTS.md:3,10`
  - `PRD.md:740-754`
- Create (not committed; `.workspace/` is gitignored): `.workspace/tasks/2026-09-15-e74-delete-featureworkflow.md`

- [ ] **Step 1: Write the lint, cold-import and purity tests**

`tests/graph_workflow/test_determinism_lint.py`:

```python
"""E-74 §10.1: determinism rules on the graph workflow modules (constraint 6)."""

from __future__ import annotations

import ast
from pathlib import Path

WF = Path(__file__).resolve().parents[2] / "src" / "sdlc" / "workflows"
MODULES = sorted(
    [
        WF / "build.py",
        WF / "graph.py",
        WF / "graph_catalog.py",
        WF / "graph_dispatch.py",
        WF / "pipeline_child.py",
        WF / "run_host.py",
        *sorted((WF / "graph_nodes").glob("*.py")),
    ]
)
ALLOW = "# determinism:"
EXPECTED_ALLOWS = {"build.py": 3, "run_host.py": 1}
BANNED_ATTR_CALLS = {("asyncio", "wait"), ("asyncio", "as_completed"), ("time", "time"),
                     ("uuid", "uuid4"), ("datetime", "now"), ("datetime", "utcnow")}


def _is_unordered_iter(node: ast.expr) -> bool:
    if isinstance(node, (ast.Set, ast.SetComp)):
        return True
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in {"set", "frozenset"}:
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"keys", "values", "items"}:
            return True
    return False


def _violations(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    out: list[str] = []

    tree = ast.parse(src)
    spans = sorted(
        (n.lineno, n.end_lineno or n.lineno) for n in ast.walk(tree) if isinstance(n, ast.stmt)
    )

    def flag(node: ast.AST, why: str) -> None:
        # The allowlist comment may sit on any line of the innermost enclosing
        # statement: ruff format moves trailing comments when it wraps a line.
        line_no = node.lineno
        start, end = min(
            (s for s in spans if s[0] <= line_no <= s[1]), key=lambda s: s[1] - s[0]
        )
        if not any(ALLOW in lines[i - 1] for i in range(start, end + 1)):
            out.append(f"{path.name}:{line_no}: {why}")

    for node in ast.walk(tree):
        if isinstance(node, ast.For) and _is_unordered_iter(node.iter):
            flag(node, "for-loop over an unordered collection; wrap in sorted()")
        if isinstance(node, ast.comprehension) and _is_unordered_iter(node.iter):
            flag(node.iter, "comprehension over an unordered collection; wrap in sorted()")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            if "random" in names:
                flag(node, "random is banned in workflow code")
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if (node.value.id, node.attr) in BANNED_ATTR_CALLS:
                flag(node, f"{node.value.id}.{node.attr} is nondeterministic")
            if (node.value.id, node.attr) == ("os", "environ"):
                flag(node, "os.environ read in workflow code")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and (node.func.value.id, node.func.attr) == ("asyncio", "gather")
        ):
            for arg in node.args:
                inner = arg.value if isinstance(arg, ast.Starred) else arg
                ok = isinstance(inner, (ast.List, ast.Tuple)) and not any(isinstance(e, ast.Starred) for e in inner.elts)
                ok = ok or (
                    isinstance(inner, ast.ListComp)
                    and all(isinstance(g.iter, ast.Call) and isinstance(g.iter.func, ast.Name) and g.iter.func.id == "sorted" for g in inner.generators)
                )
                if not ok:
                    flag(node, "asyncio.gather over a non-literal, unsorted collection")
    return out


def test_graph_workflow_modules_obey_the_determinism_rules():
    problems = [v for path in MODULES for v in _violations(path)]
    assert problems == []


def test_allowlist_comments_are_counted():
    counts = {p.name: p.read_text(encoding="utf-8").count(ALLOW) for p in MODULES}
    assert {k: v for k, v in counts.items() if v} == EXPECTED_ALLOWS


def test_the_lint_catches_what_it_claims():
    import tempfile

    bad = "import random\nimport asyncio\nd = {}\nfor k in d.keys():\n    pass\nasyncio.gather(*[f(x) for x in d])\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bad.py"
        path.write_text(bad, encoding="utf-8")
        assert len(_violations(path)) == 3
```

`tests/graph_workflow/test_cold_import.py`:

```python
"""A cold import of the interpreter survives the benchmarks<->stages cycle
(.workspace/tasks/2026-09-12-b0-lazy-step-export-shadowing.md)."""

from __future__ import annotations

import subprocess
import sys


def test_graph_workflow_module_imports_cold():
    r = subprocess.run(
        [sys.executable, "-c", "import sdlc.workflows.graph, sdlc.workflows.pipeline_child"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
```

Append to `tests/test_factory_purity.py`:

```python
GRAPH_MODULES = sorted(
    [
        *(Path(__file__).resolve().parents[1] / "src" / "sdlc" / "workflows" / "graph_nodes").glob("*.py"),
        Path(__file__).resolve().parents[1] / "src" / "sdlc" / "workflows" / "graph.py",
        Path(__file__).resolve().parents[1] / "src" / "sdlc" / "workflows" / "graph_dispatch.py",
    ]
)


def test_graph_modules_schedule_benchmark_activities_only_through_the_guarded_helpers():
    for path in GRAPH_MODULES:
        src = path.read_text(encoding="utf-8")
        for name in _BENCHMARK_ACTIVITIES:
            assert name not in src, f"{path.name} references {name}; use BenchmarkHost._record/_judge"
```

- [ ] **Step 2: Run the lint test and fix only allowlisted orderings**

Run: `pytest tests/graph_workflow/test_determinism_lint.py tests/graph_workflow/test_cold_import.py tests/test_factory_purity.py -q`
Expected: the first run FAILS on exactly one finding, `run_host.py`'s moved `self._role_usage.values()` comprehension.

Fix it by adding `  # determinism: insertion-ordered usage dict` to the `priced = [...]` statement. This is a comment-only change in verbatim-moved code, and the Replayer stays green.

Any other finding is new M2 code violating the rule. Fix it by wrapping the iterable in `sorted(...)`; never allowlist new code. If a finding is in `build.py` beyond its three allowlisted statements, that is SG-5.

Re-run until PASS.

- [ ] **Step 3: Landing docs (docs describe main)**

`docs/roadmap/pipeline-as-data.md`, E-74 bullet: change `- [ ] **E-74` to `- [x] **E-74` and append after its paragraph:

```markdown

  **Landed** (spec `docs/superpowers/specs/2026-09-15-graph-workflow-cutover-design.md`,
  plan `docs/superpowers/plans/2026-09-15-graph-workflow-cutover.md`): every new run —
  `sdlc start`, dashboard/operator, benchmark cells, tidy-up fix runs — starts
  `GraphWorkflow` over a pinned, validated graph (`workflows/graphs/default`,
  `default-research`, `seeded`), and GraphWorkflow reproduces FeatureWorkflow's
  golden traces exactly (stage/gate trace, command projection, close). `code` is one
  coarse node; **follow-ups:** per-task topology with `max_fix_attempts → max_traversals`
  (E74-OQ-3), research-as-topology (E74-OQ-2), and the FeatureWorkflow deletion gated
  on the two Running queries of spec §8.5. Rollback is roll-forward only.
```

`ROADMAP.md:398`: change `- [ ] **FR-1203**` to `- [x] **FR-1203**` and append ` Landed: GraphWorkflow serves every new run; FeatureWorkflow retained for in-flight runs until the §8.5 deletion follow-up.` In `ROADMAP.md:396`, replace the clause `registry validation, ADR-6 and \`PROMPT_SHAS\` keep working only once E-74 projects \`node.role\` into the run config.` with `E-74 projects \`node.role\` into the run config (a run-level override wins).`

`ARCHITECTURE.md`:
- `:36`: `FW[FeatureWorkflow + MaintenanceWorkflow<br/>deterministic orchestration]` → `FW[GraphWorkflow + MaintenanceWorkflow<br/>deterministic orchestration]`
- `:59` table row: first cell `FeatureWorkflow` → `GraphWorkflow (FeatureWorkflow retained for in-flight runs)`.
- `:73`: `One \`FeatureWorkflow\` per run` → `One \`GraphWorkflow\` per run, executing a pinned \`PipelineGraph\` (E-74)`.
- `:772` tree comment: `feature.py         #   FeatureWorkflow — the 15-stage DAG, gates, fix loops` → `feature.py         #   FeatureWorkflow — retained for in-flight runs (E-74 grace)`. Add sibling lines: `├── graph.py           #   GraphWorkflow — the pipeline as data (E-74)` and `├── graph_nodes/       #   node handlers over the stage steps`.
- After the `:73` paragraph, add one sentence: `Rollback of E-74 is roll-forward only: there is no start-site switch back to FeatureWorkflow.`

`AGENTS.md:107-108`: `the orchestrator (\`FeatureWorkflow\`) is the sole coordinator` → `the orchestrator (\`GraphWorkflow\`; \`FeatureWorkflow\` only for in-flight runs) is the sole coordinator`.

`src/sdlc/workflows/AGENTS.md`:
- `:3`: `Attributes on \`FeatureWorkflow\`'s MRO` → `Attributes on the MRO of \`FeatureWorkflow\` and \`GraphWorkflow\``.
- `:10`: `live on \`FeatureWorkflow\` or \`GateHost\`` → `live on the concrete workflow class (\`FeatureWorkflow\`, \`GraphWorkflow\`) or \`GateHost\``.

`PRD.md`, OQ-10 bullet (`:740-754`), append before `(Same question, same number as`:

```markdown
  **Amended 2026-09-15 (E-74 U7):** the deletion is a separate follow-up
  even when nothing is in flight at cutover, and it additionally waits for
  no Running `TidyUpWorkflow`/`BenchmarkWorkflow` started before the
  cutover deploy (their replay still starts FeatureWorkflow children).
```

- [ ] **Step 4: File the deletion follow-up inbox task (not committed)**

Create `.workspace/tasks/2026-09-15-e74-delete-featureworkflow.md`:

```markdown
| | |
|---|---|
| From | E-74 exec (M2 landing) |
| Size | L |
| Status | open — gated |

## Delete FeatureWorkflow after grace-retention ends (E-74 spec §8.5)

**Gate — run both; proceed only when BOTH return empty:**

    temporal workflow list --query "ExecutionStatus='Running' AND WorkflowType='FeatureWorkflow'"
    temporal workflow list --query "ExecutionStatus='Running' AND (WorkflowType='TidyUpWorkflow' OR WorkflowType='BenchmarkWorkflow') AND StartTime < '<M2 worker deploy instant, RFC 3339 UTC, e.g. 2026-09-20T14:00:00Z>'"

Record the actual deploy instant here when M2 is deployed.

**Delete:**
- `FeatureWorkflow`, with `_pipeline` and the dead `_run_handoff`
- `_revisable_stage` and `StageServices.revisable_stage`
- the `step()` composites of architecture/plan
- the `else` branch of `workflows/pipeline_child.py`
- `tests/replay/histories/` and `tests/replay/test_feature_replay.py`
- FeatureWorkflow-only tests (migrate the rest to GraphWorkflow)
- `FeatureWorkflow` from `channels/inbox.py`'s open-run types
- the grace-edit rule in `workflows/AGENTS.md`

**Keep:**
- `FeatureWorkflow` in `dashboard/fleet.py`'s closed-run queries, permanently
- `tests/replay/golden/`; re-baseline from GraphWorkflow with the diff attached

**Register candidates this follow-up does not own:** per-task topology (E74-OQ-3), research-as-topology (E74-OQ-2), retro on FAILED executions (E74-OQ-5).
```

- [ ] **Step 5: Full M2 gates, one invocation each**

Run, one per invocation:
- `pytest -q`
- `pytest tests/replay/test_feature_replay.py -q`
- `pytest tests/graph_workflow/test_graph_dispatch.py -m temporal -q --timeout=300 --timeout-method=thread`
- `pytest tests/graph_workflow/test_graph_workflow_smoke.py -m temporal -q --timeout=300 --timeout-method=thread`
- `pytest tests/graph_workflow/test_pipeline_child_upgrade.py -m temporal -q --timeout=300 --timeout-method=thread`
- `python scripts/check_ui.py`
- `ruff check .`
- `ruff format --check .`
- `mypy`
- `python scripts/check_file_size.py`

Re-run the golden equality: `pytest tests/replay/test_graph_golden.py -m temporal -q --timeout=300 --timeout-method=thread`. If the full file hangs, run one scenario per invocation as in Task 20 Step 2.

Expected: all green.

- [ ] **Step 6: Commit**

Message file `.workspace/tmp/e74-t23-msg.txt`:

```text
test,docs: E-74 determinism lint, cold import, landing docs

AST lint pins sorted iteration, literal gathers and no clock/random/env
reads in the graph workflow modules (two allowlisted replay-safe
orderings); cold import of the interpreter; benchmark purity extended.
Roadmap, ROADMAP, ARCHITECTURE, AGENTS and the PRD OQ-10 amendment
describe GraphWorkflow as the pipeline.
```

```bash
git add tests/graph_workflow/test_determinism_lint.py
git add tests/graph_workflow/test_cold_import.py
git add tests/test_factory_purity.py
git add src/sdlc/workflows/run_host.py
git add docs/roadmap/pipeline-as-data.md
git add ROADMAP.md
git add ARCHITECTURE.md
git add AGENTS.md
git add src/sdlc/workflows/AGENTS.md
git add PRD.md
git commit -F .workspace/tmp/e74-t23-msg.txt
```

- [ ] **Step 7: CHECKPOINT M2 — STOP**

Report to the orchestrator:
- `git log --oneline main..HEAD`;
- every Step 5 gate result;
- the 15 golden scenario verdicts;
- the path of the filed deletion inbox task;
- any named deviation, including trailers omitted per the standing ruling.

Do not merge. The orchestrator verifies and fast-forwards `main`.

---

## Spec coverage map (self-review)

| Spec section | Task(s) |
|---|---|
| §4.1 capture + capture-twice | 1 |
| §4.2 Replayer + plugin effect pin + query tests | 2, 19 (parametrized queries), 20 (live query) |
| §4.3 extractions (RunHost, run_tasks, validate_task_graph, prepare/produce/finish) | 3, 4, 5, 6 |
| §4.4 terminal ports, `failed`, `Halt`, payloads, `budget_after`, catalog, `_resolve_payload`, errata | 7, 8, 9, 10, 11 |
| §5.1 GraphRunInput, run(), re-validation | 13, 19 |
| §5.2 NodeContext, projection (U5), projection identity | 13, 14 |
| §5.3 RunFacts, host mirrors, memo-ON parity | 13, 16, 20 |
| §5.4 dispatch loop (classification, back-edge and workflow cancellation, ordering, no timers, FAILURE_TYPES pin) | 15 |
| §5.5 budget boundaries | 10 (types), 15 (dispatcher), 20 (budget golden scenarios) |
| §5.6 outcome strings (wire-string table, every deploy string) | 15 (`test_outcome_string.py`), 18 (deploy pass-through), 20 (goldens) |
| §5.7 queries/signals | 19, 20 |
| §5.8 executable + boot checks | 14, 19 |
| §6, §6.1 catalog and handlers, generic gate | 10, 16, 17, 18 |
| §7.1 graphs, selection guard, templating (U4) | 14 |
| §7.2 NodeResult, finalize, once-per-stage | 13, 16, 17 |
| §7.3 golden equality | 20 |
| §8.1 start sites, inbox, fleet | 21 |
| §8.2 per-child patches | 22 |
| §8.3 grace-edit rule (U6) | 2 |
| §8.4 roll-forward (U8) | 23 (ARCHITECTURE) |
| §8.5 deletion criteria + follow-up (U7) | 23 |
| §9 config split | 13, 14 |
| §10.1 determinism lint | 23 |
| §10.2 remaining tests (cold import, purity, frontend) | 10, 23 |
| §10.6 docs on landing | 2, 3, 5, 6, 11, 23 |
| §11 inbox tasks | 16 (branch after intake), 23 (cold import), 11 (minor 2) |


## Plan review dispositions

The consultation logs live in `.workspace/tmp/` (uncommitted): `e74-plan-skeptic.md` (F1–F10) and `advisor-e74-q3.md` (I1–I3, M1–M5).

| ID | Finding | Disposition |
|---|---|---|
| skeptic F1, F7 / advisor I2 | `waves` ordered by a real-time sleep: flaky, slow | **Applied.** t2's coding fake waits for an event set by t1's last command (review evidence write). |
| skeptic F2 | seeded graph lacks `plan_check`, so `sync_plan_tasks` would be missing | **Rejected on evidence.** `feature.py:516-519` returns into `_build_and_merge` before the validation and sync at `:611-617`; seeded runs never sync today. |
| skeptic F3 | blocking cancel fake ignores cancellation | **Applied.** It loops on `activity.is_cancelled()` and raises `CancelledError`. |
| skeptic F4 | golden runs only unsandboxed | **Applied.** Every golden scenario also runs sandboxed (commands + close); the trace needs the unsandboxed recorder. |
| skeptic F5 | `FAILED:` type may be empty | **Rejected.** An untyped `ApplicationError` projects as `FAILED::<msg>` identically on both workflows (`_failure_converter.py:150`); equality is the claim, not semantics. |
| skeptic F6 | analyze/merge read integration from host privates | **Applied.** Both read `RunFacts.integration` / `base_sha`; the fixtures set integration. |
| skeptic F8 | lazy `REGISTRY` import if called in the sandbox | **Applied as contract.** Workflow callers pass `registry_roles=`/`handler_types=`, which `pipeline_child` and `GraphWorkflow` already do; the docstring states the rule. |
| skeptic F9 | directory `git add` | **Applied.** One `git add` per fixture file. |
| skeptic F10 / advisor M3, M4 | sibling tasks not cancelled on a non-cancellation raise; swallowed cancellations stall waits | **Recorded.** Known limitations under Task 15, unreachable on the shipped linear graphs and identical to FeatureWorkflow. |
| advisor I1 | partial scenario close is `OPEN`, not `TERMINATED` | **Applied.** |
| advisor I3 | `cli.main` source keeps a `FeatureWorkflow` prose mention | **Applied.** The assertion narrows to `FeatureWorkflow.run`. |
| advisor M1 | cancel probe polled an event written only at attempt close | **Applied.** It polls the handler's log line. |
| advisor M2 | memo-parity run lacks a `reflect` fake | **Applied.** |
| advisor M5 | tests replaced the whole `workflow` global | **Applied.** They patch only `workflow.execute_activity`. |
| reviewer R1 | `npm` run directly | **Applied.** `python scripts/check_ui.py` in Tasks 10 and 23; Global Constraints name it as the only JS entry point. |
| reviewer R2 | back-edge cancellation and the FAILURE_TYPES pin untested | **Applied.** `back_edge_cancel` probe (Task 15) and a fast-tier pin in `test_outcome_string.py`. |
| reviewer R3 | wire-string table not discharged | **Applied.** A `outcome_string` table covers every §5.6 row; the deploy pass-through is parametrized over all five strings. |
| reviewer R4 | seed triggers required, spec says optional | **Applied.** `required=False`. |
| reviewer R5 | no latitude to correct a mis-predicted `EXPECTED_CLOSES` prefix | **Applied.** Allowed, citing the golden's close. |
