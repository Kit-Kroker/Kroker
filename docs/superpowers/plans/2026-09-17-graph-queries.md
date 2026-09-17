# E-75 Dashboard Graph Queries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the graph a run executes and its per-node state (status, cost, duration, traversal counters) beside the existing dashboard run queries, with content-addressed `graphs/<sha>.yaml` storage and no graph database (FR-1204).

**Architecture:** A pure run-view layer in `sdlc/graph/run_view.py` holds the raw facts model and every projection (node status, run outcome, stage marks). `GraphWorkflow` gains a sync `graph_view` query over router state plus per-activation facts the dispatcher and hosts record in memory (a `ContextVar` attributes cost and pendings to the running activation) — no new workflow commands. The dashboard reads a run's graph from the start input in history, stores it content-addressed, queries `graph_view`, and projects FINAL `graph_wire` models behind three routes; catalog capabilities stay `false`.

**Tech Stack:** Python 3.11+, temporalio 1.30.0 (`WorkflowHandle.describe`, `fetch_history_events`, `WorkflowEnvironment.start_time_skipping`), pydantic v2, FastAPI + `TestClient`, PyYAML, pytest (+ pytest-asyncio, pytest-timeout).

**Spec:** `docs/superpowers/specs/2026-09-17-graph-queries-design.md` (user-approved 2026-09-17: E75-OQ-1 = backend-only; E75-OQ-2…4 accepted deferrals; R-Q2 confirmed). Read it beside this plan; section numbers below (§) refer to it.

**Plan review:** reviewer-approved 2026-09-17 (round 2, after one CHANGES REQUESTED round); plan skeptic round (P1–P7) dispositioned in the last section. Consultation logs: `.workspace/tmp/e75-plan-skeptic.md`, `e75-plan-reviewer-r1.md`, `e75-plan-reviewer-r2.md` (uncommitted scratch).

## Global Constraints

- **Branch:** all work happens on `feat/graph-queries` in the exec worktree. Never commit on `main`. One fast-forward merge at the end (Task 11 is the checkpoint).
- **Commits:** write the message with the Write tool to `.workspace/tmp/e75-t<N>-msg.txt` (subject line + blank line + body), then `git add <path>` with **one path per `git add` invocation**, then `git commit -F .workspace/tmp/e75-t<N>-msg.txt`.
  - **No attribution trailers of any kind**: no `Co-Authored-By:` line in any form, no `Claude-Session:` links, no generated-by footers, even where a skill template prints one.
  - **No heredocs.** The host shell may be PowerShell 5.1.
- **Per-task review gate:** do not start Task N+1 until the reviewer seat has replied approve / fixes-needed on Task N's diff.
- **File ceiling:** 1000 physical lines per file (`python scripts/check_file_size.py`).
- **JavaScript:** no frontend *source* changes in E-75 (Task 10 adds generated JSON recordings only) (spec §1, E75-OQ-1 = (a)). If a gate needs the JS toolchain, run only `python scripts/check_ui.py`; never `npm`/`npx`/`vitest`/`playwright` directly.
- **Formatting:** code blocks here are exact in content, not layout. Run `ruff format <file>` and `ruff check --fix <file>` on every file you create or edit before the gates.
- **Every task's gates before commit:** the task's named tests; `ruff check .`; `ruff format --check .`; `mypy`; `python scripts/check_file_size.py`.
- **Temporal tier:** `pytest <one file> -m temporal -q --timeout=300 --timeout-method=thread`. Never chain two pytest invocations in one shell command. One test file per run. A run that exceeds its timeout without a verdict: STOP and report; never retry in a loop.
- **Sandbox imports:** every workflow module that names `sdlc.graph.run_view` imports it under `with workflow.unsafe.imports_passed_through():` (Temporal-sandbox pydantic duplication trap; and a sandbox re-import would split the `ContextVar` into two objects, spec D4).
- **Graph purity:** `src/sdlc/graph/` never imports `temporalio`, `sdlc.workflows`, `sdlc.stages`, `sdlc.agents`, `sdlc.dashboard` or `sdlc.benchmarks` at module level (`tests/graph/test_graph_purity.py`, exact file list).
- **Workflows never import the store:** no module under `src/sdlc/workflows/` imports `sdlc.graph.store` or `sdlc.graph.start` (pinned in Task 6).
- **Binding stop-guards.** On fire: stop, diagnose, report; clearance only from the orchestrator.
  - **SG-1:** `tests/replay/test_graph_golden.py` differs from its golden files (never edit a golden).
  - **SG-2:** `tests/replay/test_feature_replay.py` goes red (never re-record a history).
  - **SG-3:** any temporal-tier hang.
  - **SG-4:** a pre-existing test fails and the task does not name it.
- **Replay neutrality (spec D5):** no task adds a workflow command (activity, timer, child, marker, search attribute). Every workflow-side addition is an attribute write, a dict write, a `ContextVar` read/set, or a `workflow.now()` read at event time.
- **Capabilities stay `false`** (spec D7): `graph_wire.Capabilities()` defaults are not changed.

## File Structure

**Create:**
- `src/sdlc/graph/run_view.py` — `ACTIVATION`, `ActivationFacts`, `PendingFact`, `UnroutedFailure`, `GraphRunView`, `RunOutcome`, and the pure projections `pending_kind`, `latest_activation`, `node_status`, `node_cost`, `run_outcome`, `stage_marks`, `close_marks`.
- `src/sdlc/graph/store.py` — `GraphStore` (`put`, `get`), `GraphStoreCorrupt`, `default_root`.
- `src/sdlc/graph/start.py` — `start_graph_run` (client-only).
- `src/sdlc/dashboard/run_graph.py` — `RunGraphs` (describe, start input from history, `graph_view` query, closed-run cache), `RunSource`, `RunNotFound`.
- Tests: `tests/graph/test_run_view_models.py`, `tests/graph/test_run_view_projections.py`, `tests/graph/test_graph_store.py`, `tests/graph_workflow/test_host_attribution.py`, `tests/graph_workflow/test_graph_view_dispatch.py`, `tests/graph_workflow/test_graph_view_query.py`, `tests/graph_workflow/test_store_import_pin.py`, `tests/test_graph_start.py`, `tests/test_dashboard_graph_state_wire.py`, `tests/test_dashboard_run_graph_routes.py`, `tests/test_dashboard_fleet_marks.py`.

**Modify:**
- `src/sdlc/core/models.py` — `DotState`, `RunState.stage_marks`.
- `src/sdlc/graph/__init__.py` — export the run-view names.
- `src/sdlc/workflows/report_host.py`, `gates.py`, `question_host.py` — memory-only attribution.
- `src/sdlc/workflows/graph_dispatch.py` — per-activation facts, `ACTIVATION.set`, `escalated_by`, `unrouted_failure`, `view()`, `topology`.
- `src/sdlc/workflows/graph.py` — `graph_view` query, `run_state` stage marks, `_result` after retro.
- `src/sdlc/workflows/AGENTS.md` — ownership rows.
- `src/sdlc/cli.py`, `interfaces/dashboard/api/main.py` — start through `start_graph_run`.
- `src/sdlc/dashboard/graph_wire.py` — amended FINAL wire models, `graph_response`, `project_graph_state`, `with_executable`.
- `src/sdlc/dashboard/api.py` — three routes.
- `src/sdlc/dashboard/fleet.py` — `(id, type)` closed scan, `closed_marks`, marks cache.
- `scripts/dump_graph_fixtures.py`, `tests/test_graph_fixtures_fresh.py` — recorded run-state fixtures.
- `tests/graph/test_graph_purity.py`, `tests/conftest.py`, `.gitignore`.
- Docs (Task 11): `docs/roadmap/pipeline-as-data.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `docs/superpowers/specs/2026-09-14-graph-canvas-design.md` (§5.7 pointer).

---

### Task 1: Run-view facts model, `DotState`, and the activation context variable

**Files:**
- Create: `src/sdlc/graph/run_view.py`
- Modify: `src/sdlc/core/models.py` (beside `RunState`, `:502-525`), `src/sdlc/graph/__init__.py`, `tests/graph/test_graph_purity.py` (`ALLOWED`)
- Test: `tests/graph/test_run_view_models.py`

**Interfaces:**
- Consumes: `RouterState` (`sdlc/graph/router.py:97`), `gate_key` (`core/models.py:237`).
- Produces:
  - `sdlc.core.models.DotState = Literal["pending","active","done","blocked","failed","skipped"]`; `RunState.stage_marks: dict[str, DotState] | None = None`.
  - `sdlc.graph.run_view.ACTIVATION: ContextVar[str | None]`.
  - `NodeRunStatus = Literal["idle","running","blocked","done","failed","stale","skipped","cancelled"]`, `PendingKind = Literal["gate","clarify","escalation"]`, `OutcomeState = Literal["running","completed","rejected","escalated","failed"]`.
  - Frozen models `ActivationFacts(started_at: datetime, ended_at: datetime | None = None, cost_usd: float = 0.0, priced: bool = True)`, `PendingFact(key: str, activation_id: str | None, kind: PendingKind)`, `UnroutedFailure(activation_id: str, error_type: str)`, `GraphRunView(graph_sha: str, state: RouterState, activations: dict[str, ActivationFacts] = {}, pending: tuple[PendingFact, ...] = (), result: str | None = None, escalated_by: str | None = None, unrouted_failure: UnroutedFailure | None = None)`, `RunOutcome(state: OutcomeState, reason: str | None = None, result: str | None = None)`.
  - `pending_kind(decision_kind: str) -> PendingKind`.
  - All of the above re-exported from `sdlc.graph`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/graph/test_run_view_models.py
"""E-75 spec §4.1: the raw facts GraphWorkflow's graph_view query returns."""

from __future__ import annotations

import contextvars
from datetime import UTC, datetime
from typing import get_args

import pytest
from pydantic import ValidationError

from sdlc.core.models import DotState, RunState
from sdlc.graph import (
    ACTIVATION,
    ActivationFacts,
    GraphRunView,
    PendingFact,
    RouterState,
    UnroutedFailure,
    pending_kind,
)
from sdlc.graph.router import NodeState
from sdlc.pending import PendingDecision

AT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


def _state() -> RouterState:
    return RouterState(nodes={"a": NodeState(round=1, status="running")})


def test_dot_state_is_the_stage_dots_vocabulary():
    # interfaces/ui/src/components/stage_dots/StageDots.vue:4
    assert set(get_args(DotState)) == {"pending", "active", "done", "blocked", "failed", "skipped"}


def test_run_state_stage_marks_defaults_to_none():
    s = RunState(run_id="r", title="t", mode="greenfield", status="running", started_at=AT)
    assert s.stage_marks is None
    assert RunState.model_validate(
        {**s.model_dump(mode="json"), "stage_marks": {"intake": "done"}}
    ).stage_marks == {"intake": "done"}


def test_view_round_trips_through_json_and_sorts_its_collections():
    view = GraphRunView(
        graph_sha="s",
        state=_state(),
        activations={
            "b#1": ActivationFacts(started_at=AT),
            "a#1": ActivationFacts(started_at=AT, ended_at=AT, cost_usd=1.5),
        },
        pending=(
            PendingFact(key="z#1", activation_id=None, kind="gate"),
            PendingFact(key="Q1", activation_id="a#1", kind="clarify"),
        ),
        unrouted_failure=UnroutedFailure(activation_id="a#1", error_type="ApplicationError"),
    )
    assert list(view.activations) == ["a#1", "b#1"]
    assert [p.key for p in view.pending] == ["Q1", "z#1"]
    assert GraphRunView.model_validate_json(view.model_dump_json()) == view


def test_view_is_frozen_and_forbids_extra_fields():
    view = GraphRunView(graph_sha="s", state=_state())
    with pytest.raises(ValidationError):
        view.graph_sha = "t"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        GraphRunView.model_validate({"graph_sha": "s", "state": _state(), "payloads": {}})


def test_pending_kind_covers_every_pending_decision_variant():
    union = get_args(get_args(PendingDecision)[0])
    kinds = {get_args(cls.model_fields["kind"].annotation)[0] for cls in union}
    assert {k: pending_kind(k) for k in sorted(kinds)} == {
        "clarify": "clarify",
        "merge_gate": "gate",
        "stage_gate": "gate",
        "task_escalation": "escalation",
    }
    with pytest.raises(KeyError):
        pending_kind("unknown")


def test_activation_defaults_to_none_and_a_set_never_leaks_out_of_its_context():
    assert ACTIVATION.get() is None

    def inner() -> str | None:
        ACTIVATION.set("a#1")
        return ACTIVATION.get()

    assert contextvars.copy_context().run(inner) == "a#1"
    assert ACTIVATION.get() is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/graph/test_run_view_models.py -q`
Expected: FAIL at import (`cannot import name 'DotState'`).

- [ ] **Step 3: Add `DotState` and `RunState.stage_marks` to `src/sdlc/core/models.py`**

Directly above `class RunState(BaseModel):` add:

```python
# The fleet strip's per-stage marks (E-75 spec §5.3); the vocabulary of
# interfaces/ui/src/components/stage_dots/StageDots.vue DotState.
DotState = Literal["pending", "active", "done", "blocked", "failed", "skipped"]
```

(`Literal` is already imported in `core/models.py`; if `ruff`/`mypy` says otherwise, add it to the existing `typing` import.) As the last field of `RunState` add:

```python
    # E-75 spec §5.3: canonical stage -> mark, projected from router state by
    # GraphWorkflow.run_state. None for FeatureWorkflow runs (linear strip
    # fallback). Not named `stages`: RunSummary.stages means something else.
    stage_marks: dict[str, DotState] | None = None
```

- [ ] **Step 4: Create `src/sdlc/graph/run_view.py` (models part)**

```python
"""Graph run view -- raw per-run facts and their projections (E-75, FR-1204).

Spec: docs/superpowers/specs/2026-09-17-graph-queries-design.md §4.1, §5.

GraphWorkflow's `graph_view` query returns a GraphRunView: router state plus
per-activation facts the dispatcher and hosts record in memory. The
projections in this module are pure and shared by the workflow
(RunState.stage_marks) and the dashboard (graph_wire), so the two cannot
disagree. The payload store is never part of a view (E-74 D3).

ACTIVATION is the id of the activation whose handler task is running. It is
set ONLY as the first statement of GraphDispatcher's per-activation task
(pinned by tests/graph_workflow/test_store_import_pin.py): asyncio tasks
copy their context, so sub-tasks a handler spawns inherit it and nothing set
inside a task leaks out. Every workflow module imports this module under
imports_passed_through, so there is one ContextVar per process.

Module-level imports stay within stdlib, pydantic, sdlc.core.models and
sdlc.graph (pinned by tests/graph/test_graph_purity.py).
"""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from ..core.models import gate_key
from .router import RouterState

ACTIVATION: ContextVar[str | None] = ContextVar("sdlc_graph_activation", default=None)

NodeRunStatus = Literal[
    "idle", "running", "blocked", "done", "failed", "stale", "skipped", "cancelled"
]
PendingKind = Literal["gate", "clarify", "escalation"]
OutcomeState = Literal["running", "completed", "rejected", "escalated", "failed"]

_FROZEN = ConfigDict(frozen=True, extra="forbid")

_PENDING_KINDS: dict[str, PendingKind] = {
    "clarify": "clarify",
    "merge_gate": "gate",
    "stage_gate": "gate",
    "task_escalation": "escalation",
}


def pending_kind(decision_kind: str) -> PendingKind:
    """PendingDecision.kind -> wire kind. A new variant raises KeyError until mapped."""
    return _PENDING_KINDS[decision_kind]


class ActivationFacts(BaseModel):
    """What happened to one activation. `cost_usd` is the priced model-role
    spend attributed to it -- the same scope as RunState.cost_usd_total
    (spec §4.3); `priced` turns False once any attributed call was unpriced."""

    model_config = _FROZEN

    started_at: datetime
    ended_at: datetime | None = None
    cost_usd: float = 0.0
    priced: bool = True


class PendingFact(BaseModel):
    model_config = _FROZEN

    key: str  # the pending_decisions key, verbatim
    activation_id: str | None  # None: opened outside any activation
    kind: PendingKind


class UnroutedFailure(BaseModel):
    """An unrouted `fail` being re-raised (E-74 D8). The message is not
    exposed; it stays on the execution's close failure."""

    model_config = _FROZEN

    activation_id: str
    error_type: str


class GraphRunView(BaseModel):
    model_config = _FROZEN

    graph_sha: str
    state: RouterState
    activations: dict[str, ActivationFacts] = {}
    pending: tuple[PendingFact, ...] = ()
    result: str | None = None  # the run's return string; set only after retro returns
    escalated_by: str | None = None  # activation whose emission hit an unavailable port
    unrouted_failure: UnroutedFailure | None = None

    @field_validator("activations")
    @classmethod
    def _sort_activations(cls, value: dict[str, Any]) -> dict[str, Any]:
        return dict(sorted(value.items()))

    @field_validator("pending")
    @classmethod
    def _sort_pending(cls, value: tuple[PendingFact, ...]) -> tuple[PendingFact, ...]:
        return tuple(sorted(value, key=lambda p: p.key))


class RunOutcome(BaseModel):
    model_config = _FROZEN

    state: OutcomeState
    reason: str | None = None
    result: str | None = None


def latest_activation(node_id: str, state: RouterState) -> str | None:
    """The id of a node's most recent activation (router ids are gate_key(node, round))."""
    rnd = state.nodes[node_id].round
    return gate_key(node_id, rnd) if rnd > 0 else None
```

(`latest_activation` is used from Task 2 on; it lands here because it is a one-liner over the model.)

- [ ] **Step 5: Export from `src/sdlc/graph/__init__.py`**

Add after the `.router` import block:

```python
from .run_view import (
    ACTIVATION,
    ActivationFacts,
    GraphRunView,
    NodeRunStatus,
    OutcomeState,
    PendingFact,
    PendingKind,
    RunOutcome,
    UnroutedFailure,
    latest_activation,
    pending_kind,
)
```

and add `"ACTIVATION"`, `"ActivationFacts"`, `"GraphRunView"`, `"NodeRunStatus"`, `"OutcomeState"`, `"PendingFact"`, `"PendingKind"`, `"RunOutcome"`, `"UnroutedFailure"`, `"latest_activation"`, `"pending_kind"` to `__all__` in sorted position.

- [ ] **Step 6: Pin the new module in `tests/graph/test_graph_purity.py`**

In `ALLOWED` add the entry, and add `"sdlc.graph.run_view"` to the `"__init__.py"` set:

```python
    "run_view.py": {STDLIB, "pydantic", "sdlc.core.models", "sdlc.graph.router"},
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pytest tests/graph/test_run_view_models.py tests/graph/test_graph_purity.py -q`
Expected: PASS.

- [ ] **Step 8: Gates, then commit**

Message (`.workspace/tmp/e75-t1-msg.txt`): `feat(graph): E-75 run-view facts model and activation context variable`. Add, one path each: `src/sdlc/core/models.py`, `src/sdlc/graph/run_view.py`, `src/sdlc/graph/__init__.py`, `tests/graph/test_graph_purity.py`, `tests/graph/test_run_view_models.py`.

---

### Task 2: Pure projections — node status, cost, run outcome, stage marks

**Files:**
- Modify: `src/sdlc/graph/run_view.py`, `src/sdlc/graph/__init__.py`, `tests/graph/test_graph_purity.py`
- Test: `tests/graph/test_run_view_projections.py`

**Interfaces:**
- Consumes: Task 1 models; `Topology.terminal_ports` (`graph/topology.py:149`); `NodeTypeSpec.role`, `.canonical_stage` (`graph/node_types.py:37`); `PipelineGraph.nodes`.
- Produces (all in `sdlc.graph.run_view`, re-exported from `sdlc.graph`):
  - `node_status(node_id: str, view: GraphRunView, topology: Topology, *, execution_closed: bool = False) -> NodeRunStatus`
  - `node_cost(node_id: str, view: GraphRunView, spec: NodeTypeSpec | None) -> float | None`
  - `run_outcome(view: GraphRunView | None, *, execution_closed: bool, close_status: str | None = None) -> RunOutcome`
  - `stage_marks(view: GraphRunView, topology: Topology, graph: PipelineGraph, registry: Mapping[str, NodeTypeSpec], *, execution_closed: bool = False) -> dict[str, DotState]`
  - `close_marks(marks: Mapping[str, DotState]) -> dict[str, DotState]` — the closed-execution adjustment of marks computed while open (used by the fleet, Task 9). `close_marks(stage_marks(v, …)) == stage_marks(v, …, execution_closed=True)` for every view (pinned below).

- [ ] **Step 1: Write the failing tests**

```python
# tests/graph/test_run_view_projections.py
"""E-75 spec §5.1-§5.3: node status, run outcome and stage marks are pure tables."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sdlc.graph import (
    ActivationFacts,
    Emitted,
    GraphRouter,
    Halt,
    GraphRunView,
    PendingFact,
    UnroutedFailure,
    close_marks,
    node_cost,
    node_status,
    run_outcome,
    stage_marks,
    validate,
)
from sdlc.graph.node_types import NodeTypeSpec
from tests.graph.fixtures.registries import (
    edge,
    gate,
    graph,
    node,
    port_in,
    port_out,
    registry,
    roles,
    stage,
)

AT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


def _staged(spec: NodeTypeSpec, canonical: str, role: str | None = None) -> NodeTypeSpec:
    return spec.model_copy(update={"canonical_stage": canonical, "role": role})


REG = registry(
    _staged(stage("start", port_out("ok", None), port_out("alt", None)), "intake"),
    _staged(
        stage(
            "work",
            port_in("trigger", None),
            port_in("guidance", "GateDecision", required=False),
            port_out("out", "P"),
            port_out("fail", "NodeFailure", terminal="failed"),
        ),
        "architecture",
        role="architect",
    ),
    _staged(gate("check", "P"), "architecture"),
    _staged(stage("side", port_in("trigger", None), port_out("done", None)), "context"),
    _staged(stage("sink", port_in("art", "P"), port_out("done", None)), "deploy"),
)

# start.ok -> w -> g (gate) -> s ; g.revise -> w.guidance (bound 1) ; start.alt -> x (side)
G = graph(
    [
        node("start", "start"),
        node("w", "work"),
        node("g", "check"),
        node("s", "sink"),
        node("x", "side"),
    ],
    [
        edge("start.ok", "w.trigger"),
        edge("start.alt", "x.trigger"),
        edge("w.out", "g.artifact"),
        edge("g.approve", "s.art"),
        edge("g.revise", "w.guidance", bound=1),
    ],
)
REPORT = validate(G, REG, roles=roles())
assert REPORT.topology is not None, REPORT.problems
T = REPORT.topology
ROUTER = GraphRouter(T)


def _emit(state, aid: str, port: str):
    return ROUTER.advance(state, Emitted(activation_id=aid, port=port, payload_ref=f"{aid}.{port}"))


def _at_gate():
    """start#1 ok -> w#1 out -> g#1 live; x is dead (start took ok)."""
    s = ROUTER.start().state
    s = _emit(s, "start#1", "ok").state
    return _emit(s, "w#1", "out").state


def _view(state, **kw) -> GraphRunView:
    return GraphRunView(graph_sha="sha", state=state, **kw)


def test_status_table_at_a_live_gate():
    v = _view(_at_gate())
    assert node_status("start", v, T) == "done"
    assert node_status("x", v, T) == "skipped"  # dead
    assert node_status("w", v, T) == "done"
    assert node_status("g", v, T) == "running"
    assert node_status("s", v, T) == "idle"


def test_a_pending_attributed_to_the_latest_activation_blocks():
    v = _view(_at_gate(), pending=(PendingFact(key="g#1", activation_id="g#1", kind="gate"),))
    assert node_status("g", v, T) == "blocked"
    other = _view(_at_gate(), pending=(PendingFact(key="k", activation_id=None, kind="gate"),))
    assert node_status("g", other, T) == "running"


def test_a_back_edge_makes_the_region_stale():
    s = _emit(_at_gate(), "g#1", "revise").state  # w re-issued as w#2; g reset to pending
    v = _view(s)
    assert node_status("w", v, T) == "running"
    assert node_status("g", v, T) == "stale"  # pending with round 1


def test_a_rejecting_gate_is_done_and_the_run_rejected():
    s = _emit(_at_gate(), "g#1", "reject").state  # terminal rejected; g done
    v = _view(s)
    assert s.outcome == "rejected"
    assert node_status("g", v, T) == "done"  # a rejecting gate did its job


def test_escalating_emitter_renders_failed():
    s = _emit(_at_gate(), "g#1", "revise").state
    s = _emit(s, "w#2", "out").state  # g#2 issued with revise exhausted
    step = _emit(s, "g#2", "revise")
    assert step.outcome == "escalated"
    v = _view(step.state, escalated_by="g#2")
    assert node_status("g", v, T) == "failed"


# A live bystander: start.ok feeds both w and y, so y is running while g decides.
G2 = graph(
    [node("start", "start"), node("w", "work"), node("g", "check"), node("s", "sink"),
     node("y", "side")],
    [
        edge("start.ok", "w.trigger"),
        edge("start.ok", "y.trigger"),
        edge("w.out", "g.artifact"),
        edge("g.approve", "s.art"),
        edge("g.revise", "w.guidance", bound=1),
    ],
)
T2 = validate(G2, REG, roles=roles()).topology
assert T2 is not None
ROUTER2 = GraphRouter(T2)


def _bystander_states():
    def emit(state, aid, port):
        return ROUTER2.advance(
            state, Emitted(activation_id=aid, port=port, payload_ref=f"{aid}.{port}")
        ).state

    s = emit(ROUTER2.start().state, "start#1", "ok")
    s = emit(s, "w#1", "out")  # g#1 and y#1 live
    rejected = emit(s, "g#1", "reject")
    s = emit(emit(s, "g#1", "revise"), "w#2", "out")
    escalated = emit(s, "g#2", "revise")
    return rejected, escalated


def test_bystanders_cancel_under_rejection_and_escalation():
    rejected, escalated = _bystander_states()
    assert rejected.outcome == "rejected" and escalated.outcome == "escalated"
    assert node_status("y", _view(rejected), T2) == "cancelled"
    v = _view(escalated, escalated_by="g#2")
    assert node_status("y", v, T2) == "cancelled"
    assert node_status("g", v, T2) == "failed"


def test_failed_terminal_and_fail_port_render_failed():
    s = ROUTER.start().state
    s = _emit(s, "start#1", "ok").state
    s = _emit(s, "w#1", "fail").state  # terminal failed
    v = _view(s, unrouted_failure=UnroutedFailure(activation_id="w#1", error_type="X"))
    assert node_status("w", v, T) == "failed"


def test_an_interrupted_execution_cancels_live_nodes_and_hides_blocking():
    v = _view(_at_gate(), pending=(PendingFact(key="g#1", activation_id="g#1", kind="gate"),))
    assert node_status("g", v, T, execution_closed=True) == "cancelled"


def test_node_cost_rules():
    s = _at_gate()
    v = _view(
        s,
        activations={
            "w#1": ActivationFacts(started_at=AT, cost_usd=1.25),
            "g#1": ActivationFacts(started_at=AT),
        },
    )
    assert node_cost("w", v, REG["work"]) == 1.25
    assert node_cost("g", v, REG["check"]) is None  # no role
    assert node_cost("s", v, REG["sink"]) is None  # never ran
    unpriced = _view(s, activations={"w#1": ActivationFacts(started_at=AT, priced=False)})
    assert node_cost("w", unpriced, REG["work"]) is None
    zero = _view(s, activations={"w#1": ActivationFacts(started_at=AT)})
    assert node_cost("w", zero, REG["work"]) == 0.0
    assert node_cost("w", zero, None) is None


@pytest.mark.parametrize(
    ("view", "closed", "close_status", "expected"),
    [
        (None, False, None, ("running", None, None)),
        (None, True, "failed", ("failed", "not_started:failed", None)),
        ("live", False, None, ("running", None, None)),
        ("live", True, "terminated", ("failed", "interrupted:terminated", None)),
        ("rejected", True, "completed", ("rejected", "g.reject", "rejected:g")),
        ("retro", False, None, ("completed", None, None)),
        ("unrouted", True, "failed", ("failed", "w.fail: ApplicationError", None)),
        ("budget", True, "completed", ("rejected", "budget", "rejected:budget")),
    ],
)
def test_run_outcome_table(view, closed, close_status, expected):
    views = {
        None: None,
        "live": _view(_at_gate()),
        "rejected": _view(_emit(_at_gate(), "g#1", "reject").state, result="rejected:g"),
        "retro": _view(_emit(_emit(_at_gate(), "g#1", "approve").state, "s#1", "done").state),
        "unrouted": _view(
            _emit(_emit(ROUTER.start().state, "start#1", "ok").state, "w#1", "fail").state,
            unrouted_failure=UnroutedFailure(activation_id="w#1", error_type="ApplicationError"),
        ),
        "budget": _view(
            ROUTER.advance(_at_gate(), Halt(outcome="rejected", reason="budget")).state,
            result="rejected:budget",
        ),
    }
    out = run_outcome(views[view], execution_closed=closed, close_status=close_status)
    assert (out.state, out.reason, out.result) == expected


def test_stage_marks_precedence_and_skipped():
    v = _view(_at_gate(), pending=(PendingFact(key="g#1", activation_id="g#1", kind="gate"),))
    assert stage_marks(v, T, G, REG) == {
        "architecture": "blocked",  # w done + g blocked
        "context": "skipped",  # only x, dead
        "deploy": "pending",
        "intake": "done",
    }


def test_stage_marks_cancelled_is_failed_and_stale_is_pending():
    rejected = _view(_emit(_at_gate(), "g#1", "reject").state)
    assert stage_marks(rejected, T, G, REG)["architecture"] == "done"
    revising = _view(_emit(_at_gate(), "g#1", "revise").state)
    assert stage_marks(revising, T, G, REG)["architecture"] == "active"  # w#2 running, g stale
    interrupted = stage_marks(_view(_at_gate()), T, G, REG, execution_closed=True)
    assert interrupted["architecture"] == "failed"
    halted = _view(ROUTER.advance(_at_gate(), Halt(outcome="rejected", reason="budget")).state)
    assert node_status("g", halted, T) == "cancelled"
    assert stage_marks(halted, T, G, REG)["architecture"] == "failed"  # F11


def test_nodes_without_a_canonical_stage_contribute_nothing():
    bare = registry(*(spec.model_copy(update={"canonical_stage": None}) for spec in REG.values()))
    assert stage_marks(_view(_at_gate()), T, G, bare) == {}


@pytest.mark.parametrize("which", ["rejected", "escalated"])
def test_close_marks_equivalence_with_a_cancelled_bystander(which):
    rejected, escalated = _bystander_states()
    v = _view({"rejected": rejected, "escalated": escalated}[which], escalated_by="g#2")
    assert close_marks(stage_marks(v, T2, G2, REG)) == stage_marks(
        v, T2, G2, REG, execution_closed=True
    )


@pytest.mark.parametrize("which", ["gate", "revise", "reject", "start"])
def test_close_marks_equals_recomputing_with_execution_closed(which):
    states = {
        "gate": _at_gate(),
        "revise": _emit(_at_gate(), "g#1", "revise").state,
        "reject": _emit(_at_gate(), "g#1", "reject").state,
        "start": ROUTER.start().state,
    }
    v = _view(states[which], pending=(PendingFact(key="g#1", activation_id="g#1", kind="gate"),))
    assert close_marks(stage_marks(v, T, G, REG)) == stage_marks(
        v, T, G, REG, execution_closed=True
    )
```

Note: `tests.graph.fixtures.registries.edge(..., bound=1)` is the existing loop-edge helper (used by `tests/graph_workflow/test_graph_dispatch.py`). If `gate()`'s `revise` payload name differs from the `guidance` port payload so validate rejects `G`, change `port_in("guidance", "GateDecision", …)` to the payload `gate()` declares for `revise` — the module-level `assert REPORT.topology is not None` prints the problem.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/graph/test_run_view_projections.py -q`
Expected: FAIL at import (`cannot import name 'close_marks'`).

- [ ] **Step 3: Append the projections to `src/sdlc/graph/run_view.py`**

Add to the imports: `from collections.abc import Mapping`, and extend the core import to `from ..core.models import DotState, gate_key`; add `from .model import PipelineGraph`, `from .node_types import NodeTypeSpec`, `from .topology import Topology`. Then append:

```python
# ---- projections (spec §5) -----------------------------------------------------


def node_status(
    node_id: str, view: GraphRunView, topology: Topology, *, execution_closed: bool = False
) -> NodeRunStatus:
    """Spec §5.1, first match wins. `execution_closed` is passed True only by
    the dashboard (an open workflow cannot observe its own close)."""
    ns = view.state.nodes[node_id]
    if ns.status == "dead":
        return "skipped"
    if ns.status == "pending":
        return "stale" if ns.round > 0 else "idle"
    aid = latest_activation(node_id, view.state)
    if ns.status == "running":
        if aid is not None and aid == view.escalated_by:
            return "failed"
        if view.state.outcome != "running" or execution_closed:
            return "cancelled"
        if any(p.activation_id == aid for p in view.pending):
            return "blocked"
        return "running"
    port = ns.taken_port or ""
    if port == "fail" or topology.terminal_ports.get(node_id, {}).get(port) == "failed":
        return "failed"
    return "done"


def node_cost(node_id: str, view: GraphRunView, spec: NodeTypeSpec | None) -> float | None:
    """Spec §4.3: null for role-less types, never-run nodes and unpriced activations."""
    if spec is None or spec.role is None:
        return None
    aid = latest_activation(node_id, view.state)
    facts = view.activations.get(aid) if aid is not None else None
    if facts is None or not facts.priced:
        return None
    return facts.cost_usd


def run_outcome(
    view: GraphRunView | None, *, execution_closed: bool, close_status: str | None = None
) -> RunOutcome:
    """Spec §5.2. `close_status` is the lower-case execution status name."""
    if view is None:
        if execution_closed:
            return RunOutcome(state="failed", reason=f"not_started:{close_status}")
        return RunOutcome(state="running")
    if view.unrouted_failure is not None:
        node = view.unrouted_failure.activation_id.rpartition("#")[0]
        return RunOutcome(
            state="failed", reason=f"{node}.fail: {view.unrouted_failure.error_type}"
        )
    st = view.state
    if st.outcome == "running":
        if execution_closed:
            return RunOutcome(state="failed", reason=f"interrupted:{close_status}")
        return RunOutcome(state="running")
    return RunOutcome(state=st.outcome, reason=st.reason, result=view.result)


_DOT: dict[str, DotState] = {
    "idle": "pending",
    "stale": "pending",
    "running": "active",
    "blocked": "blocked",
    "done": "done",
    "failed": "failed",
    "cancelled": "failed",
    "skipped": "skipped",
}
_RANK: dict[str, int] = {"pending": 0, "done": 1, "active": 2, "blocked": 3, "failed": 4}


def stage_marks(
    view: GraphRunView,
    topology: Topology,
    graph: PipelineGraph,
    registry: Mapping[str, NodeTypeSpec],
    *,
    execution_closed: bool = False,
) -> dict[str, DotState]:
    """Spec §5.3: per canonical stage, failed > blocked > active > done >
    pending; skipped only when every contributing node is skipped."""
    by_stage: dict[str, list[DotState]] = {}
    for n in graph.nodes:  # sorted by PipelineGraph's validator
        spec = registry.get(n.type)
        if spec is None or spec.canonical_stage is None:
            continue
        status = node_status(n.id, view, topology, execution_closed=execution_closed)
        by_stage.setdefault(spec.canonical_stage, []).append(_DOT[status])
    out: dict[str, DotState] = {}
    for name in sorted(by_stage):
        dots = [d for d in by_stage[name] if d != "skipped"]
        out[name] = max(dots, key=_RANK.__getitem__) if dots else "skipped"
    return out


def close_marks(marks: Mapping[str, DotState]) -> dict[str, DotState]:
    """Marks computed while open, adjusted for a closed execution: a live
    (active/blocked) stage is where the run stopped."""
    return {k: ("failed" if v in ("active", "blocked") else v) for k, v in sorted(marks.items())}
```

Export `close_marks`, `node_cost`, `node_status`, `run_outcome`, `stage_marks` from `sdlc/graph/__init__.py` (import list and `__all__`). Update the `run_view.py` purity entry:

```python
    "run_view.py": {
        STDLIB,
        "pydantic",
        "sdlc.core.models",
        "sdlc.graph.model",
        "sdlc.graph.node_types",
        "sdlc.graph.router",
        "sdlc.graph.topology",
    },
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/graph/test_run_view_projections.py tests/graph/test_run_view_models.py tests/graph/test_graph_purity.py -q`
Expected: PASS. If `test_close_marks_equals_recomputing_with_execution_closed` fails, the fix is in the projection, never in the test: the equality is the contract Task 9 relies on.

- [ ] **Step 5: Gates, then commit**

Message: `feat(graph): E-75 node status, run outcome and stage-mark projections`. Add: `src/sdlc/graph/run_view.py`, `src/sdlc/graph/__init__.py`, `tests/graph/test_graph_purity.py`, `tests/graph/test_run_view_projections.py`.

---

### Task 3: Host attribution — spend bags and pending → activation (memory-only)

**Files:**
- Modify: `src/sdlc/workflows/report_host.py` (`__init__` `:25-30`, `_track_usage` `:50-87`), `src/sdlc/workflows/gates.py` (`GateHost.__init__` `:59-67`, `submit_gate_decision`, `_gate` `:208-238`), `src/sdlc/workflows/question_host.py` (`answer_question`, `ask_and_wait` `:70-85`), `src/sdlc/workflows/AGENTS.md`
- Test: `tests/graph_workflow/test_host_attribution.py`

**Interfaces:**
- Consumes: `ACTIVATION`, `PendingFact`, `pending_kind` (Task 1).
- Produces:
  - `ReportHost._activation_spend: dict[str, tuple[float, bool]]` (activation id → (priced sum, all priced)); `ReportHost._unattributed_spend: tuple[float, bool]`.
  - `GateHost._pending_activation: dict[str, str | None]` (pending key → activation id at open).
  - `GateHost._pending_facts() -> tuple[PendingFact, ...]` — iterates `_pending` (source of truth) joined with `_pending_activation`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/graph_workflow/test_host_attribution.py
"""E-75 spec §4.3: hosts attribute spend and pendings to the running activation.

Memory-only and FeatureWorkflow-neutral: with ACTIVATION unset nothing is
attributed. `workflow.now` is patched because _emit stamps events with it.
"""

from __future__ import annotations

import contextvars
from datetime import UTC, datetime

import pytest
from temporalio import workflow

from sdlc.graph import ACTIVATION, PendingFact
from sdlc.pending import ClarifyPending, StageGatePending, TaskEscalationPending
from sdlc.workflows.gates import GateHost
from sdlc.workflows.report_host import ReportHost

AT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


class _Host(ReportHost, GateHost):
    pass


@pytest.fixture(autouse=True)
def _now(monkeypatch):
    monkeypatch.setattr(workflow, "now", lambda: AT)


def _in(aid: str | None, fn):
    def run():
        if aid is not None:
            ACTIVATION.set(aid)
        fn()

    contextvars.copy_context().run(run)


def test_spend_folds_into_the_running_activation_and_totals_reconcile():
    h = _Host()
    _in("a#1", lambda: h._track_usage(role="architect", model="m", cost_usd=1.0))
    _in("a#1", lambda: h._track_usage(role="architect", model="m", cost_usd=0.5))
    _in("b#1", lambda: h._track_usage(role="planner", model="m", cost_usd=None))
    _in("b#1", lambda: h._track_usage(role="planner", model="m", cost_usd=2.0))
    _in(None, lambda: h._track_usage(role="retro", model="m", cost_usd=0.25))
    assert h._activation_spend == {"a#1": (1.5, True), "b#1": (2.0, False)}
    assert h._unattributed_spend == (0.25, True)
    total = sum(u.cost_usd for u in h._role_usage.values() if u.cost_usd is not None)
    attributed = sum(cost for cost, _ in h._activation_spend.values())
    assert attributed + h._unattributed_spend[0] == pytest.approx(total)  # spec §4.3 invariant


def test_nothing_is_attributed_without_an_activation():
    h = _Host()
    h._track_usage(role="architect", model="m", cost_usd=1.0)
    assert h._activation_spend == {}


def test_pending_facts_iterate_pending_and_join_attribution():
    h = _Host()
    h._pending["architecture#1"] = StageGatePending(
        key="architecture#1", gate="architecture", round=1, spec_summary="s"
    )
    h._pending["Q1"] = ClarifyPending(key="Q1", question="q", why_it_matters="w")
    h._pending["task:t1#1"] = TaskEscalationPending(
        key="task:t1#1", gate="task:t1", round=1, task_id="t1", analysis="a", attempts=2
    )
    h._pending_activation.update({"architecture#1": "architecture#1", "Q1": "clarify#1"})
    h._pending_activation["stale#1"] = "gone#1"  # no longer pending: must not surface
    assert h._pending_facts() == (
        PendingFact(key="Q1", activation_id="clarify#1", kind="clarify"),
        PendingFact(key="architecture#1", activation_id="architecture#1", kind="gate"),
        PendingFact(key="task:t1#1", activation_id=None, kind="escalation"),
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/graph_workflow/test_host_attribution.py -q`
Expected: FAIL (`'_Host' object has no attribute '_activation_spend'`).

- [ ] **Step 3: `ReportHost` spend bags**

In `report_host.py`'s passthrough block add `from ..graph.run_view import ACTIVATION`. In `__init__` after `self._role_usage` add:

```python
        # E-75 §4.3: priced spend per graph activation (sum, all-priced) and the
        # remainder spent outside any activation (preamble, retro). Memory-only;
        # always empty on FeatureWorkflow, where ACTIVATION is never set.
        self._activation_spend: dict[str, tuple[float, bool]] = {}
        self._unattributed_spend: tuple[float, bool] = (0.0, True)
```

In `_track_usage`, before `self._emit(`:

```python
        aid = ACTIVATION.get()
        prior = self._activation_spend.get(aid, (0.0, True)) if aid else self._unattributed_spend
        folded = (prior[0] + (cost_usd or 0.0), prior[1] and cost_usd is not None)
        if aid:
            self._activation_spend[aid] = folded
        else:
            self._unattributed_spend = folded
```

- [ ] **Step 4: `GateHost` attribution and `_pending_facts`**

In `gates.py`'s passthrough block add `from ..graph.run_view import ACTIVATION, PendingFact, pending_kind`. In `GateHost.__init__` after `self._pending` add:

```python
        # E-75 §4.3: pending key -> the graph activation that opened it (None
        # outside one). Joined onto _pending, never iterated on its own.
        self._pending_activation: dict[str, str | None] = {}
```

In `submit_gate_decision`, after `self._pending.pop(key, None)` add `self._pending_activation.pop(key, None)`. In `_gate`, directly after `self._pending[key] = pending` add `self._pending_activation[key] = ACTIVATION.get()`, and in its `finally:` after `self._pending.pop(key, None)` add `self._pending_activation.pop(key, None)`. Add the method in the mechanics section:

```python
    def _pending_facts(self) -> tuple[PendingFact, ...]:
        """E-75 §4.3: every open pending with its attributed activation.
        Iterates _pending (the source of truth), so a stale attribution entry
        can never surface a decision that is no longer owed."""
        return tuple(
            sorted(
                (
                    PendingFact(
                        key=key,
                        activation_id=self._pending_activation.get(key),
                        kind=pending_kind(p.kind),
                    )
                    for key, p in self._pending.items()
                ),
                key=lambda f: f.key,
            )
        )
```

- [ ] **Step 5: `QuestionHost` attribution**

In `question_host.py`'s passthrough block add `from ..graph.run_view import ACTIVATION`. In `answer_question`, after `pending.pop(question_id, None)` (inside the same `if`), add:

```python
            getattr(self, "_pending_activation", {}).pop(question_id, None)
```

In `ask_and_wait`, replace the registration loop

```python
        if pending is not None:
            for p in clarify_pending(list(questions), set(), opened_at=workflow.now()):
                pending[p.key] = p
```

with

```python
        attribution = getattr(self, "_pending_activation", None)
        if pending is not None:
            for p in clarify_pending(list(questions), set(), opened_at=workflow.now()):
                pending[p.key] = p
                if attribution is not None:
                    attribution[p.key] = ACTIVATION.get()
```

and in the loop that pops answered questions add, after `pending.pop(q.id, None)`: `if attribution is not None: attribution.pop(q.id, None)` (inside the existing `if pending is not None:`). The timeout path is unchanged (spec §4.3 / F2: facts iterate `_pending`).

- [ ] **Step 6: Ownership rows in `src/sdlc/workflows/AGENTS.md`**

Append to the Attribute Ownership table:

```markdown
| `_activation_spend` | `ReportHost` | `GraphWorkflow.graph_view` | `ReportHost._track_usage` | E-75: priced spend per graph activation id, `(sum, all_priced)`; keyed by `ACTIVATION`; empty on FeatureWorkflow |
| `_unattributed_spend` | `ReportHost` | tests (spend invariant) | `ReportHost._track_usage` | E-75: spend outside any activation (preamble, retro) |
| `_pending_activation` | `GateHost` | `GateHost._pending_facts` | `GateHost._gate`, `GateHost.submit_gate_decision`, `QuestionHost.ask_and_wait`, `QuestionHost.answer_question` (cross-host, via `getattr`) | E-75: pending key → opening activation id; joined onto `_pending`, never iterated alone |
| `_graph`, `_graph_sha`, `_dispatcher`, `_result` | `GraphWorkflow` | `GraphWorkflow.graph_view`, `GraphWorkflow.run_state` | `GraphWorkflow.run` | E-75: pinned graph, its sha, the live dispatcher, the return string (set after retro) |
```

- [ ] **Step 7: Run the tests, then prove FeatureWorkflow neutrality**

Run: `pytest tests/graph_workflow/test_host_attribution.py -q` — Expected: PASS.
Run: `pytest tests/replay/test_feature_replay.py -q` — Expected: PASS unchanged (SG-2).

- [ ] **Step 8: Gates, then commit**

Message: `feat(workflows): E-75 attribute spend and pendings to graph activations`. Add: `src/sdlc/workflows/report_host.py`, `src/sdlc/workflows/gates.py`, `src/sdlc/workflows/question_host.py`, `src/sdlc/workflows/AGENTS.md`, `tests/graph_workflow/test_host_attribution.py`.

---

### Task 4: Dispatcher facts and `GraphDispatcher.view()`

**Files:**
- Modify: `src/sdlc/workflows/graph_dispatch.py` (`__init__` `:59-89`, `_loop` `:107-165`, `_start` `:167-190`, `_classify` `:192-213`, `_apply` `:234-240`)
- Test: `tests/graph_workflow/test_graph_view_dispatch.py`

**Interfaces:**
- Consumes: `ACTIVATION`, `ActivationFacts`, `GraphRunView`, `PendingFact`, `UnroutedFailure` (Task 1).
- Produces:
  - `GraphDispatcher.topology -> Topology` (public property).
  - `GraphDispatcher.view(*, graph_sha: str, result: str | None, pending: tuple[PendingFact, ...], spend: Mapping[str, tuple[float, bool]]) -> GraphRunView`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/graph_workflow/test_graph_view_dispatch.py
"""E-75 spec §4.2: the dispatcher's per-activation facts and view()."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.core.models import PipelineConfig
from sdlc.graph import ACTIVATION, GraphRouter, GraphRunView, validate
from sdlc.workflows.graph_dispatch import GraphDispatcher
from sdlc.workflows.graph_nodes.base import NodeResult, RunFacts
from tests.fakes.canned import greenfield_idea
from tests.graph.fixtures.registries import (
    edge,
    graph,
    node,
    port_in,
    port_out,
    registry,
    roles,
    stage,
)

pytestmark = pytest.mark.temporal
TQ = "e75-view-dispatch"

REG = registry(
    stage("start", port_out("ok", None)),
    stage(
        "work",
        port_in("trigger", None),
        port_out("out", "P"),
        port_out("fail", "NodeFailure", terminal="failed"),
    ),
    stage("sink", port_in("art", "P"), port_out("done", None)),
    stage(
        "loop",
        port_in("trigger", None),
        port_in("guidance", "GD", required=False),
        port_out("out", "P"),
    ),
    stage("fixer", port_in("trigger", "P"), port_out("fix", "GD"), port_out("done", None)),
)


@workflow.defn(sandboxed=False)
class ViewProbe:
    def __init__(self) -> None:
        self.seen: list[str] = []
        self.released = False
        self.dispatcher: GraphDispatcher | None = None

    @workflow.signal
    def release(self) -> None:
        self.released = True

    @workflow.query
    def view_json(self) -> str | None:
        d = self.dispatcher
        return None if d is None else _view(d).model_dump_json()

    @workflow.query
    def attributions(self) -> list[str]:
        return list(self.seen)

    @workflow.run
    async def run(self, scenario: str) -> str:
        host = self

        async def start(nc, act, cfg):
            return NodeResult(port="ok")

        async def sink(nc, act, cfg):
            return NodeResult(port="done", result="done")

        async def work_wait(nc, act, cfg):
            async def sub() -> None:
                host.seen.append(f"{act.activation_id}:{ACTIVATION.get()}")

            await asyncio.gather(sub(), sub())
            await workflow.wait_condition(lambda: host.released)
            return NodeResult(port="out")

        async def boom(nc, act, cfg):
            raise ApplicationError("boom", type="X", non_retryable=True)

        async def loop_ok(nc, act, cfg):
            return NodeResult(port="out")

        async def always_fix(nc, act, cfg):
            return NodeResult(port="fix")

        table = {
            "parallel": (
                graph(
                    [node("start", "start"), node("a", "work"), node("b", "work"),
                     node("sa", "sink"), node("sb", "sink")],
                    [edge("start.ok", "a.trigger"), edge("start.ok", "b.trigger"),
                     edge("a.out", "sa.art"), edge("b.out", "sb.art")],
                ),
                {"start": start, "work": work_wait, "sink": sink},
            ),
            "unrouted": (
                graph(
                    [node("start", "start"), node("w", "work"), node("s", "sink")],
                    [edge("start.ok", "w.trigger"), edge("w.out", "s.art")],
                ),
                {"start": start, "work": boom, "sink": sink},
            ),
            "escalation": (
                graph(
                    [node("start", "start"), node("v", "loop"), node("u", "fixer")],
                    [edge("start.ok", "v.trigger"), edge("v.out", "u.trigger"),
                     edge("u.fix", "v.guidance", bound=1)],
                ),
                {"start": start, "loop": loop_ok, "fixer": always_fix},
            ),
        }
        g, handlers = table[scenario]
        report = validate(g, REG, roles=roles())
        assert report.topology is not None, report.problems
        router = GraphRouter(report.topology)
        facts = RunFacts(
            idea=greenfield_idea(),
            repo_path="/r",
            run_id=workflow.info().workflow_id,
            seeded=None,
            memory_watermark=None,
        )
        self.dispatcher = GraphDispatcher(
            host=self, services=None, router=router, graph=g, registry=REG,
            handlers=handlers, facts=facts, cfg=PipelineConfig(),
        )
        await self.dispatcher.run()
        self.seen.append(f"run:{ACTIVATION.get()}")
        return _view(self.dispatcher).model_dump_json()


def _view(d: GraphDispatcher) -> GraphRunView:
    return d.view(graph_sha="sha", result=None, pending=(), spend={"a#1": (0.5, True)})


async def _run(scenario: str, drive=None):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client, task_queue=TQ, workflows=[ViewProbe],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ):
                handle = await env.client.start_workflow(
                    ViewProbe.run, scenario, id=f"view-{uuid.uuid4()}", task_queue=TQ
                )
                if drive is not None:
                    await drive(handle)
                return GraphRunView.model_validate_json(await handle.result()), handle


async def _poll_view(handle, predicate) -> GraphRunView:
    for _ in range(600):
        raw = await handle.query("view_json")
        if raw is not None:
            view = GraphRunView.model_validate_json(raw)
            if predicate(view):
                return view
        await asyncio.sleep(0.05)
    raise AssertionError("view never satisfied the predicate")


@pytest.mark.asyncio
async def test_concurrent_activations_attribute_their_own_subtasks():
    observed: dict = {}

    async def drive(handle):
        observed["live"] = await _poll_view(
            handle, lambda v: {"a#1", "b#1"} <= set(v.activations)
        )
        observed["seen"] = await handle.query("attributions")
        await handle.signal("release")

    final, handle = await _run("parallel", drive)
    live = observed["live"]
    assert live.activations["a#1"].ended_at is None and live.activations["b#1"].ended_at is None
    assert sorted(observed["seen"]) == ["a#1:a#1", "a#1:a#1", "b#1:b#1", "b#1:b#1"]
    assert "run:None" in await handle.query("attributions")
    for aid in ("start#1", "a#1", "b#1", "sa#1", "sb#1"):
        facts = final.activations[aid]
        assert facts.ended_at is not None and facts.ended_at >= facts.started_at
    assert final.activations["a#1"].cost_usd == 0.5  # spend joined by activation id
    assert final.state.outcome == "completed"


@pytest.mark.asyncio
async def test_unrouted_failure_is_recorded_without_its_message():
    final, _ = await _run("unrouted")
    assert final.unrouted_failure is not None
    assert final.unrouted_failure.model_dump() == {
        "activation_id": "w#1",
        "error_type": "ApplicationError",
    }
    assert final.state.outcome == "failed"
    assert "boom" not in final.model_dump_json()


@pytest.mark.asyncio
async def test_the_escalating_emission_is_recorded():
    final, _ = await _run("escalation")
    assert final.state.outcome == "escalated"
    assert final.escalated_by == "u#2"
    assert final.state.traversals == {"u.fix->v.guidance": 1}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/graph_workflow/test_graph_view_dispatch.py -m temporal -q --timeout=300 --timeout-method=thread`
Expected: FAIL — the probe cannot build a view (`GraphDispatcher` has no `view` yet; it surfaces as a query failure in the drive-based test or a workflow `AttributeError` through `handle.result()` in the others).

- [ ] **Step 3: Implement in `src/sdlc/workflows/graph_dispatch.py`**

Imports: add `from collections.abc import Mapping` is already present; add `from datetime import datetime` at module top; in the passthrough block add

```python
    from ..graph.run_view import (
        ACTIVATION,
        ActivationFacts,
        GraphRunView,
        PendingFact,
        UnroutedFailure,
    )
```

In `__init__` after `self._stored_failure` add:

```python
        # E-75 §4.2: memory-only facts for the graph_view query (no commands).
        self._started: dict[str, datetime] = {}
        self._ended: dict[str, datetime] = {}
        self._escalated_by: str | None = None
        self._unrouted: UnroutedFailure | None = None
```

Add the public property beside `_t`:

```python
    @property
    def topology(self) -> Topology:
        return self._router.topology
```

In `_loop`, directly after `self._tasks.pop(aid, None)` add `self._ended.setdefault(aid, workflow.now())`. Directly before `step = self._router.advance(` (the `Emitted` call) add:

```python
            live = next(a for a in self._state.live if a.activation_id == aid)
            if result.port in live.unavailable_ports and self._escalated_by is None:
                self._escalated_by = aid  # router step 2 terminates ESCALATED on this emission
```

In `_start`, before `async def _one`, add `self._started[act.activation_id] = workflow.now()`, and make `ACTIVATION.set(act.activation_id)` the first statement of `_one`:

```python
        async def _one() -> None:
            ACTIVATION.set(act.activation_id)  # the ONLY set site (E-75 D4; pinned)
            try:
```

In `_classify`, inside `if not self._t.out_ports[node_id]["fail"]:` after `self._stored_failure = raw` add:

```python
                self._unrouted = UnroutedFailure(activation_id=aid, error_type=type(raw).__name__)
```

In `_apply`, inside `for cid in step.cancelled:` first line add `self._ended.setdefault(cid, workflow.now())`.

Add the method after `_apply`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (each separately):
- `pytest tests/graph_workflow/test_graph_view_dispatch.py -m temporal -q --timeout=300 --timeout-method=thread` — PASS
- `pytest tests/graph_workflow/test_graph_dispatch.py -m temporal -q --timeout=300 --timeout-method=thread` — PASS unchanged

- [ ] **Step 5: Gates, then commit**

Message: `feat(workflows): E-75 per-activation facts and GraphDispatcher.view`. Add: `src/sdlc/workflows/graph_dispatch.py`, `tests/graph_workflow/test_graph_view_dispatch.py`.

---

### Task 5: `GraphWorkflow.graph_view`, `run_state` stage marks, result after retro

**Files:**
- Modify: `src/sdlc/workflows/graph.py`
- Test: `tests/graph_workflow/test_graph_view_query.py`

**Interfaces:**
- Consumes: `GraphDispatcher.view`, `.topology` (Task 4); `GateHost._pending_facts`, `ReportHost._activation_spend` (Task 3); `stage_marks` (Task 2).
- Produces: query `graph_view() -> GraphRunView | None` (name is a wire contract for Tasks 8–9); `run_state()` returns `RunState` with `stage_marks` set once dispatch started.

- [ ] **Step 1: Write the failing test**

```python
# tests/graph_workflow/test_graph_view_query.py
"""E-75 spec §4.2: graph_view on a SANDBOXED GraphWorkflow (catches the
pydantic class-duplication fingerprint), attribution through real hosts, and
command neutrality against the E-74 golden."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from sdlc.core.models import RunState
from sdlc.graph import GraphRunView
from tests.replay.harness import GRAPH_STARTER, capture, load_golden
from tests.replay.scenarios import (
    QUESTION_IDS,
    SCENARIOS,
    A,
    answer_clarify,
    decide,
    wait_for,
)

pytestmark = pytest.mark.temporal
GREENFIELD = next(s for s in SCENARIOS if s.name == "greenfield_happy")


async def _view(handle) -> GraphRunView | None:
    raw = await handle.query("graph_view")
    return None if raw is None else GraphRunView.model_validate(raw)


@pytest.mark.asyncio
async def test_graph_view_attributes_and_projects_on_a_sandboxed_run(monkeypatch, tmp_path):
    observed: dict = {}

    async def drive(handle, env):
        await wait_for(handle, "awaiting:clarify")
        observed["clarify"] = await _view(handle)
        await answer_clarify(handle)
        await wait_for(handle, "awaiting:architecture")
        observed["arch"] = await _view(handle)
        observed["state"] = RunState.model_validate(await handle.query("run_state"))
        for gate in ("architecture", "plan", "deploy"):
            await decide(handle, gate, 1, A)
        for _ in range(600):
            v = await _view(handle)
            if v is not None and v.result is not None:
                observed["final"] = v
                break
            await asyncio.sleep(0.05)

    scenario = dataclasses.replace(GREENFIELD, name="graph_view_query", drive=drive)
    captured = await capture(scenario, GRAPH_STARTER, monkeypatch, tmp_path, sandboxed=True)

    clarify = observed["clarify"]
    by_key = {p.key: p for p in clarify.pending}
    for qid in QUESTION_IDS:
        assert by_key[qid].activation_id == "clarify#1" and by_key[qid].kind == "clarify"

    arch = observed["arch"]
    assert {p.key: p.activation_id for p in arch.pending} == {"architecture#1": "architecture#1"}
    assert arch.state.nodes["architecture"].status == "running"
    assert arch.result is None
    assert len(arch.graph_sha) == 64

    marks = observed["state"].stage_marks
    assert marks is not None
    assert marks["intake"] == "done"
    assert marks["context"] == "skipped"
    assert marks["architecture"] == "blocked"

    final = observed["final"]
    assert final.state.outcome == "completed"
    assert final.result is not None and final.result.startswith("deployed")
    assert all(f.ended_at is not None for f in final.activations.values())

    golden = load_golden("greenfield_happy")
    assert captured.golden["commands"] == golden["commands"], "SG-1: command projection differs"
    assert captured.golden["close"] == golden["close"]


def test_result_is_published_only_after_retro():
    """Spec F3: the retro window (router completed, execution open) must read
    result=None. The live window is too short to poll reliably, so the
    ordering is pinned on the source."""
    import inspect

    from sdlc.workflows.graph import GraphWorkflow

    src = inspect.getsource(GraphWorkflow.run)
    assert src.index("await self._retro(") < src.index("self._result = result")
    assert src.count("self._result =") == 1
```

If `final.result` does not start with `deployed` on this scenario, assert it equals the golden close result instead — read `golden["close"]` for the return string; never weaken the "result is not None" assertion.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/graph_workflow/test_graph_view_query.py -m temporal -q --timeout=300 --timeout-method=thread`
Expected: FAIL (query `graph_view` not found / `unknown queryType`).

- [ ] **Step 3: Implement in `src/sdlc/workflows/graph.py`**

Passthrough imports: add `from ..graph.model import PipelineGraph` and `from ..graph.run_view import GraphRunView, stage_marks`.

In `__init__`, after `self._codebase_map = None` add:

```python
        # E-75 §4.2: read by graph_view / run_state only; set once by run().
        self._graph: PipelineGraph | None = None
        self._graph_sha: str = ""
        self._dispatcher: GraphDispatcher | None = None
        self._result: str | None = None
```

Replace the `run_state` query and add `graph_view` and a helper:

```python
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
```

In `run`, after the `executable` check and before `self._idea = idea`, add:

```python
        self._graph = inp.graph
        self._graph_sha = inp.graph.content_sha()
```

Change the dispatch tail to set the dispatcher before awaiting and the result only after retro (spec F3):

```python
        self._dispatcher = dispatcher
        outcome = await dispatcher.run()
        if outcome.stored_failure is not None:
            raise outcome.stored_failure  # D8: same failure as FeatureWorkflow; retro not run (U9)
        result = outcome_string(outcome, router.topology)
        await self._retro(cfg, idea, result)
        self._result = result  # E-75 F3: never a success string while retro can still fail
        return result
```

- [ ] **Step 4: Run the tests (each separately)**

- `pytest tests/graph_workflow/test_graph_view_query.py -m temporal -q --timeout=300 --timeout-method=thread` — PASS
- `pytest tests/replay/test_graph_golden.py -m temporal -q --timeout=300 --timeout-method=thread` — PASS unchanged (SG-1)
- `pytest tests/replay/test_feature_replay.py -q` — PASS unchanged (SG-2)
- `pytest tests/graph_workflow/test_graph_workflow_class.py -q` — PASS

- [ ] **Step 5: Gates, then commit**

Message: `feat(workflows): E-75 graph_view query and stage marks on run_state`. Add: `src/sdlc/workflows/graph.py`, `tests/graph_workflow/test_graph_view_query.py`.

---

### Task 6: Content-addressed store, client start helper, start sites

**Files:**
- Create: `src/sdlc/graph/store.py`, `src/sdlc/graph/start.py`
- Modify: `src/sdlc/cli.py` (`:442-457`), `interfaces/dashboard/api/main.py` (`_start`, `:55-61`), `tests/graph/test_graph_purity.py`, `tests/conftest.py`, `.gitignore`
- Test: `tests/graph/test_graph_store.py`, `tests/test_graph_start.py`, `tests/graph_workflow/test_store_import_pin.py`

**Interfaces:**
- Consumes: `to_yaml`, `from_yaml`, `GraphSchemaError` (`graph/io.py`), `PipelineGraph.content_sha()`.
- Produces:
  - `sdlc.graph.store.GraphStore(root: str | os.PathLike | None = None)` with `.root: Path`, `.put(graph: PipelineGraph) -> str`, `.get(sha: str) -> PipelineGraph | None`; `GraphStoreCorrupt(RuntimeError)`; `default_root() -> Path`.
  - `async sdlc.graph.start.start_graph_run(client, run, run_input, *, id: str, task_queue: str, store: GraphStore | None = None)` → the workflow handle.

- [ ] **Step 1: Write the failing tests**

```python
# tests/graph/test_graph_store.py
"""E-75 spec §6.1: graphs/<sha>.yaml, put-if-absent, verify-then-trust."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sdlc.graph import from_yaml
from sdlc.graph.store import GraphStore, GraphStoreCorrupt, default_root

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


@pytest.fixture
def graph():
    return from_yaml(FIXTURE.read_text(encoding="utf-8"))


def test_put_writes_sha_named_yaml_and_get_round_trips(tmp_path, graph):
    store = GraphStore(tmp_path)
    sha = store.put(graph)
    assert sha == graph.content_sha()
    assert (tmp_path / f"{sha}.yaml").is_file()
    assert store.get(sha) == graph
    assert list(tmp_path.glob("*.tmp")) == []


def test_put_is_idempotent_and_keeps_a_valid_file(tmp_path, graph):
    store = GraphStore(tmp_path)
    sha = store.put(graph)
    before = (tmp_path / f"{sha}.yaml").stat().st_mtime_ns
    assert store.put(graph) == sha
    assert (tmp_path / f"{sha}.yaml").stat().st_mtime_ns == before


@pytest.mark.parametrize("content", ["", "schema_version: 1\nnodes: [\n", "schema_version: 1\nnodes: []\nedges: []\n"])
def test_put_replaces_a_truncated_or_corrupt_existing_file(tmp_path, graph, content):
    store = GraphStore(tmp_path)
    target = tmp_path / f"{graph.content_sha()}.yaml"
    target.write_text(content, encoding="utf-8")
    store.put(graph)
    assert store.get(graph.content_sha()) == graph


def test_replace_refused_succeeds_only_if_the_target_then_verifies(tmp_path, graph, monkeypatch):
    store = GraphStore(tmp_path)
    sha = graph.content_sha()

    def racing_replace(src, dst):
        Path(dst).write_text(Path(src).read_text(encoding="utf-8"), encoding="utf-8")
        raise PermissionError("held by a concurrent reader")

    monkeypatch.setattr(os, "replace", racing_replace)
    assert store.put(graph) == sha
    assert list(tmp_path.glob("*.tmp")) == []

    def failing_replace(src, dst):
        raise PermissionError("held")

    other = tmp_path / "other"
    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(PermissionError):
        GraphStore(other).put(graph)


def test_get_missing_is_none_and_corruption_is_loud(tmp_path, graph):
    store = GraphStore(tmp_path)
    assert store.get(graph.content_sha()) is None
    (tmp_path / f"{graph.content_sha()}.yaml").write_text(
        "schema_version: 1\nnodes: []\nedges: []\n", encoding="utf-8"
    )
    with pytest.raises(GraphStoreCorrupt):
        store.get(graph.content_sha())


@pytest.mark.parametrize("bad", ["../x", "ABC", "a" * 63, "g" * 64])
def test_sha_must_be_lowercase_hex_64(tmp_path, bad):
    with pytest.raises(ValueError):
        GraphStore(tmp_path).get(bad)


def test_default_root_resolution(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_GRAPH_STORE", str(tmp_path / "g"))
    assert default_root() == (tmp_path / "g").resolve()
    monkeypatch.delenv("SDLC_GRAPH_STORE")
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path / "runs"))
    assert default_root() == (tmp_path / "graphs").resolve()
    assert GraphStore().root.is_absolute()
```

```python
# tests/test_graph_start.py
"""E-75 spec §6.1: client start helper -- store first, never blocks the start."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.graph import from_yaml
from sdlc.graph.start import start_graph_run
from sdlc.graph.store import GraphStore

FIXTURE = Path(__file__).parent / "graph" / "fixtures" / "pre_code.graph.yaml"


class _Input:
    def __init__(self) -> None:
        self.graph = from_yaml(FIXTURE.read_text(encoding="utf-8"))


class _Client:
    def __init__(self) -> None:
        self.started: list[tuple] = []

    async def start_workflow(self, run, arg, *, id, task_queue):
        self.started.append((run, arg, id, task_queue))
        return f"handle:{id}"


async def _run_fn(inp):  # stands in for GraphWorkflow.run
    return ""


@pytest.mark.asyncio
async def test_stores_the_graph_then_starts(tmp_path):
    client, inp = _Client(), _Input()
    store = GraphStore(tmp_path)
    handle = await start_graph_run(client, _run_fn, inp, id="feature-x", task_queue="q", store=store)
    assert handle == "handle:feature-x"
    assert client.started == [(_run_fn, inp, "feature-x", "q")]
    assert store.get(inp.graph.content_sha()) == inp.graph


@pytest.mark.asyncio
async def test_a_store_failure_never_blocks_the_start(caplog):
    class _Broken(GraphStore):
        def put(self, graph):
            raise OSError("disk full")

    client = _Client()
    await start_graph_run(client, _run_fn, _Input(), id="feature-y", task_queue="q", store=_Broken("x"))
    assert len(client.started) == 1
    assert "graph store write failed" in caplog.text
```

```python
# tests/graph_workflow/test_store_import_pin.py
"""E-75 D1/D4: workflow code never reaches the store or the client helper,
and ACTIVATION is set in exactly one place."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "sdlc"


def test_workflows_never_import_the_store_or_start():
    pattern = re.compile(r"graph\.store|graph\.start|graph import (store|start)")
    offenders = [
        p.relative_to(SRC).as_posix()
        for p in (SRC / "workflows").rglob("*.py")
        if pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_activation_is_set_only_in_the_dispatcher_task():
    hits = [
        (p.relative_to(SRC).as_posix(), line.strip())
        for p in SRC.rglob("*.py")
        for line in p.read_text(encoding="utf-8").splitlines()
        if "ACTIVATION.set(" in line
    ]
    assert hits == [
        ("workflows/graph_dispatch.py", "ACTIVATION.set(act.activation_id)  # the ONLY set site (E-75 D4; pinned)")
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/graph/test_graph_store.py tests/test_graph_start.py tests/graph_workflow/test_store_import_pin.py -q`
Expected: FAIL at import (`No module named 'sdlc.graph.store'`); the pin test passes already for ACTIVATION.

- [ ] **Step 3: Create `src/sdlc/graph/store.py`**

```python
"""Content-addressed graph store: graphs/<sha>.yaml (E-75, FR-1204).

Spec: docs/superpowers/specs/2026-09-17-graph-queries-design.md §6.

Files only -- there is no graph database and no index. A file is trusted only
after it verifies (parses, and its content_sha equals its name), so a
truncated or corrupt file is replaced rather than kept by existence. Written
by the client start helper (start.py) and backfilled by the dashboard from a
run's start input; never imported by workflow code (sandbox I/O).

Module-level imports stay within stdlib and sdlc.graph (pinned by
tests/graph/test_graph_purity.py).
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from pathlib import Path

from .io import GraphSchemaError, from_yaml, to_yaml
from .model import PipelineGraph

_log = logging.getLogger(__name__)
_SHA = re.compile(r"[0-9a-f]{64}")


class GraphStoreCorrupt(RuntimeError):
    """A stored file does not hash to its name, or to_yaml is not faithful."""


def default_root() -> Path:
    """SDLC_GRAPH_STORE, else a `graphs` sibling of the run artifact root --
    outside per-run directories, so pruning a run never deletes a graph."""
    explicit = os.environ.get("SDLC_GRAPH_STORE")
    if explicit:
        return Path(explicit).resolve()
    runs = os.environ.get("SDLC_ARTIFACT_ROOT") or os.environ.get("SDLC_EXPORT_ROOT") or "./runs"
    return (Path(runs).resolve().parent / "graphs").resolve()


class GraphStore:
    def __init__(self, root: str | os.PathLike | None = None) -> None:
        self.root = Path(root).resolve() if root is not None else default_root()
        _log.debug("graph store root: %s", self.root)

    def _path(self, sha: str) -> Path:
        if not _SHA.fullmatch(sha):
            raise ValueError(f"not a graph sha: {sha!r}")
        return self.root / f"{sha}.yaml"

    def _verifies(self, path: Path, sha: str) -> bool:
        try:
            return from_yaml(path.read_text(encoding="utf-8")).content_sha() == sha
        except (OSError, GraphSchemaError):
            return False

    def put(self, graph: PipelineGraph) -> str:
        sha = graph.content_sha()
        text = to_yaml(graph)
        if from_yaml(text).content_sha() != sha:
            raise GraphStoreCorrupt(f"to_yaml does not round-trip graph {sha}")
        target = self._path(sha)
        if self._verifies(target, sha):
            return sha
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f".{sha}.{uuid.uuid4().hex}.tmp"
        tmp.write_text(text, encoding="utf-8")
        try:
            os.replace(tmp, target)
        except (PermissionError, FileExistsError):
            # Windows: a concurrent writer or reader holds the target.
            tmp.unlink(missing_ok=True)
            if not self._verifies(target, sha):
                raise
        return sha

    def get(self, sha: str) -> PipelineGraph | None:
        path = self._path(sha)
        if not path.exists():
            return None
        try:
            graph = from_yaml(path.read_text(encoding="utf-8"))
        except GraphSchemaError as e:
            raise GraphStoreCorrupt(f"{path} does not parse") from e
        if graph.content_sha() != sha:
            raise GraphStoreCorrupt(f"{path} hashes to {graph.content_sha()}")
        return graph
```

- [ ] **Step 4: Create `src/sdlc/graph/start.py`**

```python
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
```

- [ ] **Step 5: Purity pins, test isolation, ignore rule**

`tests/graph/test_graph_purity.py` `ALLOWED` add:

```python
    "store.py": {STDLIB, "sdlc.graph.io", "sdlc.graph.model"},
    "start.py": {STDLIB, "sdlc.graph.store"},
```

`tests/conftest.py`: next to the other module-load `os.environ.setdefault` lines add:

```python
# E-75: start sites write graphs/<sha>.yaml; keep test runs out of the checkout.
os.environ.setdefault("SDLC_GRAPH_STORE", str(Path(tempfile.gettempdir()) / "sdlc-test-graphs"))
```

and add `import tempfile` to the conftest's stdlib imports.

`.gitignore`: add a line `/graphs/` (anchored — an unanchored `graphs/` would ignore `src/sdlc/workflows/graphs/`).

- [ ] **Step 6: Route the start sites through the helper**

`src/sdlc/cli.py` (the `start` branch, `:442-457`): replace

```python
        handle = await client.start_workflow(
            GraphWorkflow.run, run_input, id=wf_id, task_queue=TASK_QUEUE
        )
```

with

```python
        from .graph.start import start_graph_run

        handle = await start_graph_run(
            client, GraphWorkflow.run, run_input, id=wf_id, task_queue=TASK_QUEUE
        )
```

`interfaces/dashboard/api/main.py`: add `from sdlc.graph.start import start_graph_run` to the imports and replace the `client.start_workflow(...)` call in `_start` with

```python
    handle = await start_graph_run(
        client, GraphWorkflow.run, run_input, id=wf_id, task_queue=TASK_QUEUE
    )
```

- [ ] **Step 7: Run the tests**

- `pytest tests/graph/test_graph_store.py tests/test_graph_start.py tests/graph_workflow/test_store_import_pin.py tests/graph/test_graph_purity.py -q` — PASS
- `pytest tests/graph_workflow/test_cutover_wiring.py tests/test_dashboard_entrypoint.py tests/test_fleet_capacity_wiring.py -q` — PASS unchanged

- [ ] **Step 8: Gates, then commit**

Message: `feat(graph): E-75 content-addressed graph store and client start helper`. Add: `src/sdlc/graph/store.py`, `src/sdlc/graph/start.py`, `src/sdlc/cli.py`, `interfaces/dashboard/api/main.py`, `tests/graph/test_graph_purity.py`, `tests/conftest.py`, `.gitignore`, `tests/graph/test_graph_store.py`, `tests/test_graph_start.py`, `tests/graph_workflow/test_store_import_pin.py`.

---

### Task 7: FINAL wire models and their projections in `graph_wire`

**Files:**
- Modify: `src/sdlc/dashboard/graph_wire.py` (`Issue` `:278-285`; the PROVISIONAL run-state block `:372-425`)
- Test: `tests/test_dashboard_graph_state_wire.py`

**Interfaces:**
- Consumes: `GraphRunView`, `latest_activation`, `node_status`, `node_cost`, `run_outcome` (Tasks 1–2) via `from sdlc.graph import …` (graph_wire's import pin allows only the `sdlc.graph` root); `Topology`, `NODE_TYPES`.
- Produces (spec §7.4):
  - `NodeRunState.status` adds `skipped`, `cancelled`.
  - `RunOutcomeWire(state, reason, result)`; `GraphState.outcome: RunOutcomeWire` replaces `terminal`.
  - `PendingRef.node: str | None`.
  - `Issue.severity` adds `not_executable`.
  - `graph_response(graph: PipelineGraph) -> GraphResponse`
  - `project_graph_state(view: GraphRunView | None, graph: PipelineGraph, topology: Topology, *, execution_closed: bool, close_status: str | None = None, registry: Mapping[str, NodeTypeSpec] = NODE_TYPES) -> GraphState`
  - `with_executable(wire: ValidationWire, problems: Iterable[Any]) -> ValidationWire` (duck-typed `code`, `node`, `message`; graph_wire cannot import `workflows`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dashboard_graph_state_wire.py
"""E-75 spec §7.4: FINAL run-graph and run-state wire projections."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from sdlc.core.models import PipelineConfig
from sdlc.dashboard import graph_wire
from sdlc.graph import (
    ActivationFacts,
    Emitted,
    GraphRouter,
    GraphRunView,
    PendingFact,
    UnroutedFailure,
    from_yaml,
    validate,
)
from sdlc.graph.node_types import NODE_TYPES
from sdlc.workflows.graph_catalog import SHIPPED, executable, resolved_roles

AT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
GRAPH = SHIPPED["default"]
ROLES = resolved_roles(PipelineConfig())
TOPOLOGY = validate(GRAPH, NODE_TYPES, roles=ROLES).topology
assert TOPOLOGY is not None
ROUTER = GraphRouter(TOPOLOGY)


def _emit(state, aid, port):
    return ROUTER.advance(state, Emitted(activation_id=aid, port=port, payload_ref=f"{aid}.{port}")).state


def _at_architecture():
    s = ROUTER.start().state
    s = _emit(s, "intake#1", "ok")
    s = _emit(s, "clarify#1", "requirements")
    return _emit(s, "architect#1", "spec")


def test_graph_response_carries_sha_graph_and_sorted_back_edges():
    r = graph_wire.graph_response(GRAPH)
    assert r.kind == "graph" and r.sha == GRAPH.content_sha()
    assert [(e.source, e.source_port) for e in r.back_edges] == [
        ("architecture", "revise"),
        ("plan", "revise"),
    ]


def test_state_before_dispatch_is_all_idle_and_running():
    s = graph_wire.project_graph_state(None, GRAPH, TOPOLOGY, execution_closed=False)
    assert s.graph_sha == GRAPH.content_sha()
    assert {n.status for n in s.nodes.values()} == {"idle"}
    assert s.outcome.model_dump() == {"state": "running", "reason": None, "result": None}
    assert (s.edges, s.current_nodes, s.pending) == ([], [], [])


def test_state_at_a_blocked_gate():
    view = GraphRunView(
        graph_sha=GRAPH.content_sha(),
        state=_at_architecture(),
        activations={
            "architect#1": ActivationFacts(started_at=AT, ended_at=AT, cost_usd=1.5),
            "architecture#1": ActivationFacts(started_at=AT),
        },
        pending=(
            PendingFact(key="architecture#1", activation_id="architecture#1", kind="gate"),
            PendingFact(key="orphan#1", activation_id=None, kind="gate"),
        ),
    )
    s = graph_wire.project_graph_state(view, GRAPH, TOPOLOGY, execution_closed=False)
    assert s.nodes["architecture"].status == "blocked"
    assert s.nodes["architecture"].started_at == AT.isoformat()
    assert s.nodes["architecture"].ended_at is None
    assert s.nodes["architecture"].cost_usd is None  # gate: no role
    assert s.nodes["architect"].cost_usd == 1.5
    assert s.nodes["context"].status == "skipped"
    assert s.current_nodes == ["architecture"]
    assert [(p.node, p.key, p.kind) for p in s.pending] == [
        ("architecture", "architecture#1", "gate"),
        (None, "orphan#1", "gate"),
    ]


def test_traversed_back_edges_only_and_closed_runs_list_no_pendings():
    s = _emit(_at_architecture(), "architecture#1", "revise")
    view = GraphRunView(
        graph_sha="x",
        state=s,
        pending=(PendingFact(key="architecture#2", activation_id=None, kind="gate"),),
    )
    open_ = graph_wire.project_graph_state(view, GRAPH, TOPOLOGY, execution_closed=False)
    assert [(e.edge.source, e.edge.target, e.traversals) for e in open_.edges] == [
        ("architecture", "architect", 1)
    ]
    closed = graph_wire.project_graph_state(
        view, GRAPH, TOPOLOGY, execution_closed=True, close_status="terminated"
    )
    assert closed.pending == [] and closed.current_nodes == []
    assert closed.outcome.state == "failed" and closed.outcome.reason == "interrupted:terminated"
    assert closed.nodes["architect"].status == "cancelled"


def test_unrouted_failure_outcome_and_node():
    s = _emit(ROUTER.start().state, "intake#1", "fail")
    view = GraphRunView(
        graph_sha="x",
        state=s,
        unrouted_failure=UnroutedFailure(activation_id="intake#1", error_type="ApplicationError"),
    )
    out = graph_wire.project_graph_state(view, GRAPH, TOPOLOGY, execution_closed=True, close_status="failed")
    assert out.nodes["intake"].status == "failed"
    assert out.outcome.model_dump() == {
        "state": "failed",
        "reason": "intake.fail: ApplicationError",
        "result": None,
    }


def test_wire_models_are_final_shapes():
    with pytest.raises(ValidationError):
        graph_wire.GraphState.model_validate(
            {"kind": "state", "graph_sha": "x", "nodes": {}, "edges": [], "current_nodes": [],
             "pending": [], "terminal": None}
        )
    assert "terminal" not in graph_wire.GraphState.model_fields


def test_executable_problems_get_their_own_severity():
    pre_code = from_yaml(
        (Path(__file__).parent / "graph" / "fixtures" / "pre_code.graph.yaml").read_text(encoding="utf-8")
    )
    problems = executable(pre_code)
    assert problems, "pre_code has a gate.research node, which is not executable"
    wire = graph_wire.with_executable(graph_wire.validation(pre_code, roles=ROLES), problems)
    extra = [i for i in wire.issues if i.severity == "not_executable"]
    assert [(i.code, i.target.kind, i.target.id) for i in extra] == [
        (p.code, "node", p.node) for p in problems
    ]
```

If `executable(pre_code)` is empty (the fixture has no `gate.research` node), build the graph for the last test by adding `{id: research_gate, type: gate.research}` to a copy of `SHIPPED["default-research"]` via `PipelineGraph.model_validate`; the assertion that problems are non-empty must stay.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_dashboard_graph_state_wire.py -q`
Expected: FAIL (`module 'sdlc.dashboard.graph_wire' has no attribute 'graph_response'`).

- [ ] **Step 3: Amend `src/sdlc/dashboard/graph_wire.py`**

Imports: `from collections.abc import Iterable, Mapping`; extend the `from sdlc.graph import (...)` block with `GraphRunView`, `Topology`, `latest_activation`, `node_cost`, `node_status`, `run_outcome`. Module docstring: replace "E-75's routes use the PROVISIONAL ones as `response_model=` later" with "E-75's routes use the run-graph and run-state models, FINAL since E-75 (spec 2026-09-17-graph-queries-design §7.4)".

`Issue.severity`:

```python
    severity: Literal["error", "warning", "not_executable"]
```

After `validation(...)` add:

```python
def with_executable(wire: ValidationWire, problems: Iterable[Any]) -> ValidationWire:
    """E74-OQ-4: executable() problems beside validate's, with a distinct
    severity -- a legal graph this worker cannot run is not an `error`.
    `problems` are workflows.graph_catalog.ExecutableProblem (duck-typed:
    graph_wire does not import workflow code)."""
    extra = [
        Issue(
            code=p.code,
            severity="not_executable",
            message=p.message,
            target=IssueTarget(kind="node", id=p.node),
        )
        for p in problems
    ]
    return ValidationWire(issues=[*wire.issues, *extra], back_edges=wire.back_edges)
```

Replace the whole `# --- PROVISIONAL: run graph and run state (E-75 on E-74) ---` block (through the end of `GraphState`) with:

```python
# --- run graph and run state (FINAL, E-75 spec §7) ------------------------------


class GraphResponse(BaseModel):
    model_config = _WIRE

    kind: Literal["graph"] = "graph"
    sha: str
    graph: dict[str, Any]
    back_edges: list[EdgeRef]


class NoGraph(BaseModel):
    model_config = _WIRE

    kind: Literal["no_graph"] = "no_graph"
    reason: Literal["legacy_run"] = "legacy_run"


class NodeRunState(BaseModel):
    model_config = _WIRE

    status: Literal[
        "idle", "running", "blocked", "done", "failed", "stale", "skipped", "cancelled"
    ]
    round: int
    started_at: str | None
    ended_at: str | None
    cost_usd: float | None


class EdgeRunState(BaseModel):
    model_config = _WIRE

    edge: EdgeRef
    traversals: int  # back edges only; absent = 0


class PendingRef(BaseModel):
    model_config = _WIRE

    node: str | None  # None: opened outside any activation
    key: str
    kind: Literal["gate", "clarify", "escalation"]


class RunOutcomeWire(BaseModel):
    model_config = _WIRE

    state: Literal["running", "completed", "rejected", "escalated", "failed"]
    reason: str | None
    result: str | None  # the run's return string (E74-OQ-1), once known


class GraphState(BaseModel):
    model_config = _WIRE

    kind: Literal["state"] = "state"
    graph_sha: str
    nodes: dict[str, NodeRunState]
    edges: list[EdgeRunState]
    current_nodes: list[str]
    pending: list[PendingRef]
    outcome: RunOutcomeWire


def _edge_ref(key: tuple[str, str, str, str]) -> EdgeRef:
    return EdgeRef(source=key[0], source_port=key[1], target=key[2], target_port=key[3])


def graph_response(graph: PipelineGraph) -> GraphResponse:
    back = sorted(
        (e.source, e.source_port, e.target, e.target_port)
        for e in graph.edges
        if e.max_traversals is not None
    )
    return GraphResponse(
        sha=graph.content_sha(),
        graph=_graph_json(graph),
        back_edges=[_edge_ref(k) for k in back],
    )


def project_graph_state(
    view: GraphRunView | None,
    graph: PipelineGraph,
    topology: Topology,
    *,
    execution_closed: bool,
    close_status: str | None = None,
    registry: Mapping[str, NodeTypeSpec] = NODE_TYPES,
) -> GraphState:
    """E-75 spec §5, §7.4. Every rule lives in sdlc.graph.run_view; this only
    shapes the wire. No field changes without a state change (E-76 §5.7)."""
    outcome = RunOutcomeWire(
        **run_outcome(view, execution_closed=execution_closed, close_status=close_status).model_dump()
    )
    if view is None:
        idle = NodeRunState(status="idle", round=0, started_at=None, ended_at=None, cost_usd=None)
        return GraphState(
            graph_sha=graph.content_sha(),
            nodes={n.id: idle for n in graph.nodes},
            edges=[],
            current_nodes=[],
            pending=[],
            outcome=outcome,
        )
    nodes: dict[str, NodeRunState] = {}
    for n in graph.nodes:
        aid = latest_activation(n.id, view.state)
        facts = view.activations.get(aid) if aid is not None else None
        nodes[n.id] = NodeRunState(
            status=node_status(n.id, view, topology, execution_closed=execution_closed),
            round=view.state.nodes[n.id].round,
            started_at=facts.started_at.isoformat() if facts is not None else None,
            ended_at=(
                facts.ended_at.isoformat()
                if facts is not None and facts.ended_at is not None
                else None
            ),
            cost_usd=node_cost(n.id, view, registry.get(n.type)),
        )
    edges = [
        EdgeRunState(edge=_edge_ref(topology.edges[eid]), traversals=count)
        for eid, count in sorted(view.state.traversals.items())
        if count > 0
    ]
    live = [] if execution_closed else sorted({a.node_id for a in view.state.live})
    pending = (
        []
        if execution_closed
        else [
            PendingRef(
                node=p.activation_id.rpartition("#")[0] if p.activation_id else None,
                key=p.key,
                kind=p.kind,
            )
            for p in view.pending
        ]
    )
    return GraphState(
        graph_sha=view.graph_sha,
        nodes=nodes,
        edges=edges,
        current_nodes=live,
        pending=pending,
        outcome=outcome,
    )
```

(`NodeTypeSpec`, `NODE_TYPES`, `PipelineGraph`, `EdgeRef`, `_graph_json`, `_WIRE` already exist in the module.)

- [ ] **Step 4: Run the tests**

- `pytest tests/test_dashboard_graph_state_wire.py tests/test_dashboard_graph_wire.py tests/test_graph_wire_validation_edge_cases.py -q` — PASS
- `pytest tests/test_graph_fixtures_fresh.py -q` — PASS (catalog/parse/serialize recordings unchanged)

- [ ] **Step 5: Gates, then commit**

Message: `feat(dashboard): E-75 FINAL run-graph and run-state wire projections`. Add: `src/sdlc/dashboard/graph_wire.py`, `tests/test_dashboard_graph_state_wire.py`.

---

### Task 8: `RunGraphs` source and the three routes

**Files:**
- Create: `src/sdlc/dashboard/run_graph.py`
- Modify: `src/sdlc/dashboard/api.py` (`create_router`, `:83`; new routes beside the graph routes `:196-214`)
- Test: `tests/test_dashboard_run_graph_routes.py`

**Interfaces:**
- Consumes: `GraphRunInput` (`workflows/models.py:93`), `GraphStore` (Task 6), `graph_view` query (Task 5), `graph_response` / `project_graph_state` / `with_executable` (Task 7), `executable` / `resolved_roles` (`workflows/graph_catalog.py`).
- Produces:
  - `RunNotFound(LookupError)`; `RunQueryFailed(RuntimeError)` (route → 502).
  - `RunSource` dataclass: `handle: Any`, `workflow_type: str`, `closed: bool`, `close_status: str | None`, `run_input: GraphRunInput | None`, `topology: Topology | None`.
  - `RunGraphs(client_getter: Callable[[], Awaitable[Any]], *, store: GraphStore | None = None, cache_size: int = 256)` with `async source(run_id) -> RunSource` and `async view(src: RunSource, run_id: str) -> GraphRunView | None`.
  - `create_router(poller, starter=None, run_graphs: RunGraphs | None = None)`.
  - Routes: `GET /runs/{run_id}/graph` → `GraphResponse | NoGraph`; `GET /runs/{run_id}/graph_state` → `GraphState | NoGraph`; `POST /graphs/validate` → `ValidationWire`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dashboard_run_graph_routes.py
"""E-75 spec §6.2, §7.1-§7.3: run graph, run state and validate routes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from temporalio.client import WorkflowExecutionStatus
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.service import RPCError, RPCStatusCode

from sdlc.core.models import PipelineConfig
from sdlc.dashboard import graph_wire
from sdlc.dashboard.api import create_router
from sdlc.dashboard.run_graph import RunGraphs
from sdlc.graph import NODE_TYPES, GraphRouter, GraphRunView, validate
from sdlc.graph.store import GraphStore
from sdlc.workflows.graph_catalog import build_run_input
from tests.fakes.canned import greenfield_idea

FIXTURE = Path(__file__).parent / "graph" / "fixtures" / "pre_code.graph.yaml"
RUN_INPUT = build_run_input(greenfield_idea(), PipelineConfig())


class _NoPoller:
    def __getattr__(self, name):
        raise AssertionError(f"run-graph route touched the poller: {name}")


class _Handle:
    def __init__(self, *, wf_type="GraphWorkflow", status=WorkflowExecutionStatus.RUNNING,
                 view=None, missing=False, history_gone=False, query_error=None):
        self.wf_type, self.status, self._view, self.missing = wf_type, status, view, missing
        self.history_gone, self.query_error = history_gone, query_error
        self.history_reads = 0
        self.queries = 0

    async def describe(self):
        if self.missing:
            raise RPCError("not found", RPCStatusCode.NOT_FOUND, b"")
        return SimpleNamespace(workflow_type=self.wf_type, status=self.status)

    async def fetch_history_events(self):
        self.history_reads += 1
        if self.history_gone:
            raise RPCError("history purged", RPCStatusCode.NOT_FOUND, b"")
        [payload] = await pydantic_data_converter.encode([RUN_INPUT])
        attrs = SimpleNamespace(input=SimpleNamespace(payloads=[payload]))
        yield SimpleNamespace(workflow_execution_started_event_attributes=attrs)

    async def query(self, name):
        assert name == "graph_view"
        self.queries += 1
        if self.query_error is not None:
            raise self.query_error
        return None if self._view is None else self._view.model_dump(mode="json")


class _Client:
    data_converter = pydantic_data_converter

    def __init__(self, handles):
        self.handles = handles

    def get_workflow_handle(self, run_id):
        return self.handles.get(run_id) or _Handle(missing=True)


def _live_view() -> GraphRunView:
    topology = validate(RUN_INPUT.graph, NODE_TYPES, roles=RUN_INPUT.roles).topology
    assert topology is not None
    return GraphRunView(
        graph_sha=RUN_INPUT.graph.content_sha(), state=GraphRouter(topology).start().state
    )


@pytest.fixture
def setup(tmp_path):
    handles = {
        "graph-run": _Handle(view=_live_view()),
        "closed-run": _Handle(status=WorkflowExecutionStatus.COMPLETED, view=_live_view()),
        "legacy-run": _Handle(wf_type="FeatureWorkflow"),
        "purged-run": _Handle(status=WorkflowExecutionStatus.COMPLETED, history_gone=True),
        "broken-run": _Handle(
            status=WorkflowExecutionStatus.FAILED,
            view=_live_view(),
            query_error=RuntimeError("no worker"),
        ),
    }
    client = _Client(handles)

    async def get_client():
        return client

    store = GraphStore(tmp_path)
    app = FastAPI()
    app.include_router(create_router(_NoPoller(), run_graphs=RunGraphs(get_client, store=store)))
    return TestClient(app), handles, store


def test_graph_route_decodes_the_start_input_and_backfills_the_store(setup):
    client, handles, store = setup
    r = client.get("/runs/graph-run/graph")
    assert r.status_code == 200
    assert r.json() == graph_wire.graph_response(RUN_INPUT.graph).model_dump(mode="json")
    assert store.get(RUN_INPUT.graph.content_sha()) == RUN_INPUT.graph
    client.get("/runs/graph-run/graph")
    assert handles["graph-run"].history_reads == 1  # start input cached per run


def test_legacy_and_unknown_runs(setup):
    client, _, _ = setup
    for path in ("/runs/legacy-run/graph", "/runs/legacy-run/graph_state"):
        r = client.get(path)
        assert r.status_code == 200 and r.json() == {"kind": "no_graph", "reason": "legacy_run"}
    assert client.get("/runs/nope/graph").status_code == 404
    assert client.get("/runs/nope/graph_state").status_code == 404


def test_purged_history_is_404_and_query_failure_is_502_uncached(setup):
    client, handles, _ = setup
    assert client.get("/runs/purged-run/graph").status_code == 404
    assert client.get("/runs/purged-run/graph_state").status_code == 404
    assert client.get("/runs/broken-run/graph_state").status_code == 502
    assert client.get("/runs/broken-run/graph_state").status_code == 502
    assert handles["broken-run"].queries == 2  # a failure is never cached


def test_graph_state_projects_the_view(setup):
    client, _, _ = setup
    body = client.get("/runs/graph-run/graph_state").json()
    assert body["kind"] == "state"
    assert body["graph_sha"] == RUN_INPUT.graph.content_sha()
    assert body["nodes"]["intake"]["status"] == "running"
    assert body["outcome"] == {"state": "running", "reason": None, "result": None}


def test_a_closed_run_is_queried_once(setup):
    client, handles, _ = setup
    first = client.get("/runs/closed-run/graph_state").json()
    second = client.get("/runs/closed-run/graph_state").json()
    assert first == second
    assert handles["closed-run"].queries == 1
    assert first["outcome"]["reason"] == "interrupted:completed"  # router still running
    assert first["pending"] == []


def test_validate_route_serves_validate_plus_executable(setup):
    client, _, _ = setup
    graph = graph_wire.parse_text(FIXTURE.read_text(encoding="utf-8")).graph
    r = client.post("/graphs/validate", json={"graph": graph})
    assert r.status_code == 200
    severities = {i["severity"] for i in r.json()["issues"]}
    assert "not_executable" in severities
    assert client.post("/graphs/validate", json={"yaml": "x"}).status_code == 422


def test_capabilities_stay_false():
    assert graph_wire.catalog().capabilities.model_dump(by_alias=True) == {
        "validate": False, "save": False, "load": False, "run_graph": False,
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_dashboard_run_graph_routes.py -q`
Expected: FAIL at import (`No module named 'sdlc.dashboard.run_graph'`).

- [ ] **Step 3: Create `src/sdlc/dashboard/run_graph.py`**

```python
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
        return RunSource(handle, desc.workflow_type, closed, close_status, run_input, topology)

    async def _input(self, client: Any, handle: Any, run_id: str) -> tuple[GraphRunInput, Topology]:
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
        if report.topology is None:  # the run validated this graph at start (E-74 D14)
            raise RuntimeError(f"{run_id}: pinned graph no longer validates: {report.problems}")
        try:
            self._store.put(run_input.graph)
        except Exception:  # noqa: BLE001 -- serving never depends on the store
            _log.warning("graph store backfill failed for %s", run_id, exc_info=True)
        self._inputs.put(run_id, (run_input, report.topology))
        return run_input, report.topology

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
```

- [ ] **Step 4: Routes in `src/sdlc/dashboard/api.py`**

Imports: `from ..workflows.graph_catalog import GraphStartError, executable, resolved_roles`; `from .run_graph import RunGraphs, RunNotFound, RunQueryFailed`. Signature: `def create_router(poller: FleetPoller, starter: Callable | None = None, run_graphs: RunGraphs | None = None) -> APIRouter:`; first lines of the body add:

```python
    # Lazy: the pure graph routes' tests pass a poller that fails on any attribute access.
    graphs = run_graphs if run_graphs is not None else RunGraphs(lambda: poller._client_or_connect())
```

After the `graph_serialize` route add:

```python
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

    async def _source(run_id: str):
        try:
            return await graphs.source(run_id)
        except RunNotFound as e:
            raise HTTPException(404, f"no run {run_id!r}") from e

    @router.get(
        "/runs/{run_id}/graph", response_model=graph_wire.GraphResponse | graph_wire.NoGraph
    )
    async def run_graph(run_id: str):
        src = await _source(run_id)
        if src.run_input is None:
            return graph_wire.NoGraph()
        return graph_wire.graph_response(src.run_input.graph)

    @router.get(
        "/runs/{run_id}/graph_state", response_model=graph_wire.GraphState | graph_wire.NoGraph
    )
    async def run_graph_state(run_id: str):
        src = await _source(run_id)
        if src.run_input is None or src.topology is None:
            return graph_wire.NoGraph()
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
        )
```

Add `from ..graph import PipelineGraph` to the imports. `RunGraphs(...)` constructs a `GraphStore()` eagerly; construction does no I/O.

- [ ] **Step 5: Run the tests**

- `pytest tests/test_dashboard_run_graph_routes.py tests/test_dashboard_graph_routes.py tests/test_dashboard_api.py tests/test_dashboard_entrypoint.py -q` — PASS

- [ ] **Step 6: Gates, then commit**

Message: `feat(dashboard): E-75 run graph, graph state and validate routes`. Add: `src/sdlc/dashboard/run_graph.py`, `src/sdlc/dashboard/api.py`, `tests/test_dashboard_run_graph_routes.py`.

---

### Task 9: Fleet closed-run stage marks

**Files:**
- Modify: `src/sdlc/dashboard/fleet.py` (`FleetSnapshot` `:66-81`, `_scan_closed`/`_closed_run_ids` `:109-129`, `fetch_fleet` `:132-169`, `FleetPoller.__init__` `:266-285`), `docs/superpowers/specs/2026-09-17-graph-queries-design.md` (§5.3 erratum, D8 wording)
- Test: `tests/test_dashboard_fleet_marks.py`

**Interfaces:**
- Consumes: `RunState.stage_marks` (Tasks 1, 5), `close_marks` (Task 2).
- Produces:
  - `FleetSnapshot.closed_marks: dict[str, dict[str, DotState]]` (default empty).
  - `_closed_runs(client, limit) -> list[tuple[str, str | None]]` (replaces `_closed_run_ids`).
  - `fetch_fleet(client, *, now, closed_limit=CLOSED_LIMIT, marks_cache: dict[str, dict[str, DotState]] | None = None)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dashboard_fleet_marks.py
"""E-75 spec §5.3: closed graph rows carry stage marks, queried once per run."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from sdlc.core.models import RunState, RunSummary
from sdlc.dashboard.fleet import FleetPoller, fetch_fleet

AT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


def _summary(run_id):
    return RunSummary(run_id=run_id, mode="greenfield", outcome="x", terminal_stage="retro",
                      started_at=AT, ended_at=AT, duration_s=1.0)


def _state(run_id, marks):
    return RunState(run_id=run_id, title="T", mode="greenfield", status="running",
                    started_at=AT, stage_marks=marks)


class _Handle:
    def __init__(self, *, summary=None, state=None, error=None):
        self.summary, self.state, self.error = summary, state, error
        self.calls: list[str] = []

    async def query(self, name):
        self.calls.append(name)
        if name == "run_state" and self.error is not None:
            raise self.error
        value = {"run_summary": self.summary, "run_state": self.state,
                 "pending_decisions": None}[name]
        return value.model_dump(mode="json") if value is not None else None


class _Client:
    def __init__(self, closed):  # run_id -> (workflow_type, handle)
        self.closed = closed

    async def list_workflows(self, query):
        if "!=" not in query:
            return
        for run_id, (wf_type, _) in self.closed.items():
            yield SimpleNamespace(id=run_id, workflow_type=wf_type)

    def get_workflow_handle(self, run_id):
        return self.closed[run_id][1]


@pytest.mark.asyncio
async def test_closed_graph_rows_get_closed_marks_and_are_queried_once():
    graph = _Handle(summary=_summary("g"), state=_state("g", {"intake": "done", "architecture": "blocked"}))
    legacy = _Handle(summary=_summary("f"))
    client = _Client({"g": ("GraphWorkflow", graph), "f": ("FeatureWorkflow", legacy)})
    cache: dict = {}
    snap = await fetch_fleet(client, now=AT, marks_cache=cache)
    assert snap.closed_marks == {"g": {"architecture": "failed", "intake": "done"}}
    assert "run_state" not in legacy.calls  # FeatureWorkflow rows are never asked
    await fetch_fleet(client, now=AT, marks_cache=cache)
    assert graph.calls.count("run_state") == 1


@pytest.mark.asyncio
async def test_failed_marks_query_is_an_error_row_and_retries_next_tick():
    graph = _Handle(summary=_summary("g"), error=RuntimeError("boom"))
    client = _Client({"g": ("GraphWorkflow", graph)})
    cache: dict = {}
    snap = await fetch_fleet(client, now=AT, marks_cache=cache)
    assert snap.closed_marks == {}
    assert any(e.run_id == "g" for e in snap.errors)
    assert snap.open_errors == []
    await fetch_fleet(client, now=AT, marks_cache=cache)
    assert graph.calls.count("run_state") == 2


@pytest.mark.asyncio
async def test_cache_is_pruned_to_the_current_closed_list():
    graph = _Handle(summary=_summary("g"), state=_state("g", {"intake": "done"}))
    client = _Client({"g": ("GraphWorkflow", graph)})
    cache: dict = {"gone": {"intake": "done"}}
    await fetch_fleet(client, now=AT, marks_cache=cache)
    assert set(cache) == {"g"}


@pytest.mark.asyncio
async def test_a_run_that_never_dispatched_has_no_marks_and_is_not_requeried():
    graph = _Handle(summary=_summary("g"), state=None)
    client = _Client({"g": ("GraphWorkflow", graph)})
    cache: dict = {}
    snap = await fetch_fleet(client, now=AT, marks_cache=cache)
    assert snap.closed_marks == {}
    await fetch_fleet(client, now=AT, marks_cache=cache)
    assert graph.calls.count("run_state") == 1


def test_default_poller_fetch_owns_a_marks_cache():
    poller = FleetPoller(lambda: None)
    assert poller._fetch.keywords["marks_cache"] is poller._marks_cache
```

The `_Client.list_workflows` also serves the open-run listing (`inbox.list_open_run_ids`), which issues a query without `!=` — this stub yields no open runs for it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_dashboard_fleet_marks.py -q`
Expected: FAIL (`fetch_fleet() got an unexpected keyword argument 'marks_cache'`).

- [ ] **Step 3: Implement in `src/sdlc/dashboard/fleet.py`**

Imports: `import functools`; extend `from ..core.models import (RunState, RunSummary,)` with `DotState`; add `from ..graph import close_marks`.

`FleetSnapshot`: after `open_errors` add

```python
    # E-75 §5.3: stage marks for CLOSED GraphWorkflow rows, derived once per
    # run from run_state and adjusted for the close (open rows carry theirs
    # on RunState.stage_marks). Absent key: linear strip fallback.
    closed_marks: dict[str, dict[str, DotState]] = Field(default_factory=dict)
```

Replace `_scan_closed` and `_closed_run_ids` with:

```python
async def _scan_closed(client, query: str, limit: int) -> list[tuple[str, str | None]]:
    runs: list[tuple[str, str | None]] = []
    async for wf in client.list_workflows(query):
        runs.append((wf.id, getattr(wf, "workflow_type", None)))
        if len(runs) >= limit:
            break
    return runs


async def _closed_runs(client, limit: int) -> list[tuple[str, str | None]]:
    global _ORDER_BY_SUPPORTED
    if _ORDER_BY_SUPPORTED:
        try:
            return await _scan_closed(client, _CLOSED_QUERY, limit)
        except Exception as e:  # noqa: BLE001 -- narrow retry, re-raise else
            if "ORDER BY" not in str(e):
                raise
            # Standard visibility (dev server): the clause is rejected
            # outright. Remember, so only the first fan-out pays the probe.
            _ORDER_BY_SUPPORTED = False
    return await _scan_closed(client, _CLOSED_QUERY_UNORDERED, limit)


_NO_MARKS: dict[str, DotState] = {}


async def _fetch_marks(client, run_id: str):
    """Never raises (the _fetch_closed pattern). {} when the run closed before
    dispatch started (run_state carries no marks)."""
    try:
        raw = await client.get_workflow_handle(run_id).query("run_state")
        state = RunState.model_validate(raw) if raw is not None else None
        if state is None or state.stage_marks is None:
            return _NO_MARKS
        return close_marks(state.stage_marks)
    except Exception as e:  # noqa: BLE001
        return e
```

In `fetch_fleet`, change the signature to

```python
async def fetch_fleet(
    client,
    *,
    now: datetime,
    closed_limit: int = CLOSED_LIMIT,
    marks_cache: dict[str, dict[str, DotState]] | None = None,
) -> FleetSnapshot:
```

replace `closed_ids = await _closed_run_ids(client, closed_limit)` with

```python
    closed = await _closed_runs(client, closed_limit)
    closed_ids = [run_id for run_id, _ in closed]
    open_id_set = set(open_ids)
    cache = marks_cache if marks_cache is not None else {}
    graph_closed = [r for r, t in closed if t == "GraphWorkflow" and r not in open_id_set]
    for stale in [k for k in cache if k not in graph_closed]:
        del cache[stale]  # bounded by closed_limit
    need_marks = [r for r in graph_closed if r not in cache]
```

change the gather to three legs:

```python
    open_results, closed_results, marks_results = await asyncio.gather(
        asyncio.gather(*(_fetch_open(client, r) for r in open_ids)),
        asyncio.gather(*(_fetch_closed(client, r) for r in closed_ids)),
        asyncio.gather(*(_fetch_marks(client, r) for r in need_marks)),
    )
```

delete the later `open_id_set = set(open_ids)` line (now computed above), and before `return snap` add:

```python
    for run_id, outcome in zip(need_marks, marks_results, strict=True):
        if isinstance(outcome, Exception):
            snap.errors.append(InboxError(run_id=run_id, error=f"stage marks: {outcome}"))
        else:
            cache[run_id] = outcome
    snap.closed_marks = {r: dict(cache[r]) for r in graph_closed if cache.get(r)}
```

`FleetPoller.__init__`: replace `self._fetch = fetch or fetch_fleet` with

```python
        self._marks_cache: dict[str, dict[str, DotState]] = {}
        self._fetch = fetch or functools.partial(fetch_fleet, marks_cache=self._marks_cache)
```

- [ ] **Step 4: Run the tests**

- `pytest tests/test_dashboard_fleet_marks.py tests/test_dashboard_fleet.py tests/test_dashboard_poller.py tests/test_dashboard_sse.py tests/test_fleet_capacity_wiring.py tests/graph_workflow/test_cutover_wiring.py -q` — PASS (existing stubs yield `SimpleNamespace(id=…)` without `workflow_type`: they get no marks, unchanged behaviour)

- [ ] **Step 5: Spec erratum (the clause travels with the code)**

In the spec's §5.3, directly after the paragraph beginning "Closed rows: when a GraphWorkflow row first appears closed", add:

```markdown
> **Erratum (E-75 plan, Task 9).** The fleet derives closed marks from one `run_state` query (which already carries `stage_marks` computed from the same view) adjusted by `run_view.close_marks`, pinned equal to recomputing with `execution_closed=True` (`tests/graph/test_run_view_projections.py`). Same one-query-per-run bound; no fleet-side topology or history read.
```

In D8, change "a closed run is queried at most once per process" to "a closed run is successfully queried at most once per process (a failed query is retried next tick)".

- [ ] **Step 6: Gates, then commit**

Message: `feat(dashboard): E-75 stage marks for closed graph runs in the fleet`. Add: `src/sdlc/dashboard/fleet.py`, `tests/test_dashboard_fleet_marks.py`, `docs/superpowers/specs/2026-09-17-graph-queries-design.md`.

---

### Task 10: Recorded run-graph fixtures (Python-side contract export)

**Files:**
- Modify: `scripts/dump_graph_fixtures.py`, `tests/test_graph_fixtures_fresh.py`
- Create (generated): `interfaces/dashboard/frontend/src/api/__fixtures__/graph/run_state/graph_response.recorded.json`, `.../run_state/graph_state.recorded.json`, `.../run_state/validation.recorded.json`

**Interfaces:**
- Consumes: `graph_response`, `project_graph_state`, `validation`, `with_executable` (Task 7); `SHIPPED`, `executable`, `resolved_roles` (`graph_catalog`).
- Produces: three recorded files keyed by scenario; no frontend code reads them in E-75 (spec §7.4: FINAL = the Python contract; the TS mirror stays PROVISIONAL until the canvas follow-up).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_graph_fixtures_fresh.py`:

```python
def test_run_state_recordings_cover_every_outcome_state():
    built = dump.build()
    states = built["run_state/graph_state.recorded.json"]
    assert {name: s["outcome"]["state"] for name, s in states.items()} == {
        "blocked_at_architecture": "running",
        "completed": "completed",
        "escalated_revise_exhausted": "escalated",
        "interrupted": "failed",
        "not_started": "running",
        "rejected_at_architecture": "rejected",
        "unrouted_fail": "failed",
    }
    assert {s["outcome"]["state"] for s in states.values()} == {
        "running", "completed", "rejected", "escalated", "failed"
    }
    assert built["run_state/graph_response.recorded.json"]["kind"] == "graph"
    severities = {i["severity"] for i in built["run_state/validation.recorded.json"]["issues"]}
    assert "not_executable" in severities
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_graph_fixtures_fresh.py -q`
Expected: FAIL (`KeyError: 'run_state/graph_state.recorded.json'`).

- [ ] **Step 3: Extend `scripts/dump_graph_fixtures.py`**

Docstring: add a paragraph — "`run_state/*.recorded.json` (E-75) are exports of the FINAL run-graph/run-state/validate projections, recorded from router steps over the shipped default graph. No frontend code reads them yet; the canvas follow-up swaps them in with the TS mirror." Add imports after `from sdlc.dashboard import graph_wire`:

```python
from datetime import UTC, datetime  # noqa: E402

from sdlc.core.models import PipelineConfig  # noqa: E402
from sdlc.graph import (  # noqa: E402
    NODE_TYPES,
    ActivationFacts,
    Emitted,
    GraphRouter,
    GraphRunView,
    PendingFact,
    UnroutedFailure,
    from_yaml,
    validate,
)
from sdlc.workflows.graph_catalog import SHIPPED, executable, resolved_roles  # noqa: E402

AT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
```

Add before `def build()`:

```python
def _run_state() -> dict[str, Any]:
    g = SHIPPED["default"]
    roles = resolved_roles(PipelineConfig())
    topology = validate(g, NODE_TYPES, roles=roles).topology
    assert topology is not None
    router = GraphRouter(topology)

    def emit(state, aid, port):
        return router.advance(
            state, Emitted(activation_id=aid, port=port, payload_ref=f"{aid}.{port}")
        ).state

    s = router.start().state
    s = emit(s, "intake#1", "ok")
    s = emit(s, "clarify#1", "requirements")
    at_gate = emit(s, "architect#1", "spec")
    assert at_gate.nodes["architecture"].status == "running"
    facts = {
        "intake#1": ActivationFacts(started_at=AT, ended_at=AT),
        "clarify#1": ActivationFacts(started_at=AT, ended_at=AT, cost_usd=0.31),
        "architect#1": ActivationFacts(started_at=AT, ended_at=AT, cost_usd=1.87),
        "architecture#1": ActivationFacts(started_at=AT),
    }
    blocked = GraphRunView(
        graph_sha=g.content_sha(),
        state=at_gate,
        activations=facts,
        pending=(PendingFact(key="architecture#1", activation_id="architecture#1", kind="gate"),),
    )
    rejected = GraphRunView(
        graph_sha=g.content_sha(),
        state=emit(at_gate, "architecture#1", "reject"),
        activations={**facts, "architecture#1": ActivationFacts(started_at=AT, ended_at=AT)},
        result="rejected:architecture",
    )
    done = at_gate
    for aid, port in (
        ("architecture#1", "approve"),
        ("planner#1", "plan"),
        ("plan#1", "approve"),
        ("plan_check#1", "ok"),
        ("code#1", "results"),
        ("analyze#1", "analysis"),
        ("merge#1", "pr"),
        ("deploy#1", "done"),
    ):
        done = emit(done, aid, port)
    assert done.outcome == "completed"
    completed = GraphRunView(
        graph_sha=g.content_sha(),
        state=done,
        activations={
            aid: ActivationFacts(started_at=AT, ended_at=AT)
            for aid in sorted({e.activation_id for e in done.emissions})
        },
        result="deployed:https://example.invalid/pr/1",
    )
    looping = at_gate
    for aid, port in (
        ("architecture#1", "revise"),
        ("architect#2", "spec"),
        ("architecture#2", "revise"),
        ("architect#3", "spec"),
    ):
        looping = emit(looping, aid, port)
    exhausted = emit(looping, "architecture#3", "revise")
    assert exhausted.outcome == "escalated"
    escalated = GraphRunView(
        graph_sha=g.content_sha(), state=exhausted, escalated_by="architecture#3"
    )
    failed = GraphRunView(
        graph_sha=g.content_sha(),
        state=emit(router.start().state, "intake#1", "fail"),
        activations={"intake#1": ActivationFacts(started_at=AT, ended_at=AT)},
        unrouted_failure=UnroutedFailure(activation_id="intake#1", error_type="ApplicationError"),
    )
    cases = {
        "not_started": (None, False, None),
        "blocked_at_architecture": (blocked, False, None),
        "rejected_at_architecture": (rejected, True, "completed"),
        "completed": (completed, True, "completed"),
        "escalated_revise_exhausted": (escalated, True, "completed"),
        "unrouted_fail": (failed, True, "failed"),
        "interrupted": (blocked, True, "terminated"),
    }
    states = {
        name: _dump(
            graph_wire.project_graph_state(
                view, g, topology, execution_closed=closed, close_status=status
            )
        )
        for name, (view, closed, status) in sorted(cases.items())
    }
    pre_code = from_yaml(PRE_CODE.read_text(encoding="utf-8"))
    validation = graph_wire.with_executable(
        graph_wire.validation(pre_code, roles=roles), executable(pre_code)
    )
    return {
        "run_state/graph_response.recorded.json": _dump(graph_wire.graph_response(g)),
        "run_state/graph_state.recorded.json": states,
        "run_state/validation.recorded.json": _dump(validation),
    }
```

In `build()`, before `return files`, add `files.update(_run_state())`.

- [ ] **Step 4: Generate and verify**

Run: `python scripts/dump_graph_fixtures.py` (writes the three new files; existing recordings must be byte-unchanged — check with `git status --short interfaces/`: only `run_state/` is new).
Run: `pytest tests/test_graph_fixtures_fresh.py -q` — PASS.
Run: `python scripts/check_ui.py` — PASS (no frontend file changed; confirms the new JSON does not disturb the frontend build). If this workstation cannot run the Node toolchain, say so in the task report rather than skipping silently.

- [ ] **Step 5: Gates, then commit**

Message: `test(dashboard): E-75 recorded run-graph and run-state wire fixtures`. Add (one per invocation): `scripts/dump_graph_fixtures.py`, `tests/test_graph_fixtures_fresh.py`, and each of the three generated JSON files.

---

### Task 11: Landing docs and CHECKPOINT

**Files:**
- Modify: `docs/roadmap/pipeline-as-data.md` (E-75 row, `:117`), `ROADMAP.md` (FR-1204 `:399`, FR-1205 `:400`), `ARCHITECTURE.md` (tree, `:804`), `docs/superpowers/specs/2026-09-14-graph-canvas-design.md` (§5.7 heading area)

Docs describe `main`; these land in the same merge as the code.

- [ ] **Step 1: Roadmap row** — replace the E-75 bullet in `docs/roadmap/pipeline-as-data.md` with:

```markdown
- [x] **E-75 — graph queries on the dashboard backend** → FR-1204. `GraphWorkflow` exposes a `graph_view` query (router state + per-activation timing, attributed cost and pendings, recorded in memory with no new commands); the dashboard serves `GET /runs/{id}/graph` (the pinned start input, read from history), `GET /runs/{id}/graph_state` and `POST /graphs/validate` (`executable()` problems as `not_executable`), and `RunState.stage_marks` renders `skipped` stages for graph runs. Graphs are stored content-addressed as `graphs/<sha>.yaml` (`sdlc/graph/store.py`), written at client start and backfilled on first read; no graph database.

  **Landed** (spec `docs/superpowers/specs/2026-09-17-graph-queries-design.md`, plan `docs/superpowers/plans/2026-09-17-graph-queries.md`). Backend-only: catalog capabilities stay `false`. **Follow-ups:** canvas run-mode wiring (flip `run_graph`/`validate`, amend `graph-types.ts` and fixtures, map `stage_marks` in `http.ts`); crew-child escalation attribution (E75-OQ-2); closed-run `run_summary` replay per fleet tick (E75-OQ-3); pricing harness/crew spend (E75-OQ-4). Durable `graph_sha` per run stays E-77.
```

- [ ] **Step 2: ROADMAP mirror** — FR-1204 line becomes:

```markdown
- [x] **FR-1204** dashboard graph queries beside the existing run queries — `graph_view` query, `/runs/{id}/graph`, `/runs/{id}/graph_state`, `/graphs/validate`; content-addressed `graphs/<sha>.yaml`, no graph DB (E-75, landed backend-only; canvas wiring is a follow-up).
```

In the FR-1205 line replace "live run state waits on E-75" with "live run state is served by E-75 and awaits the canvas run-mode follow-up".

- [ ] **Step 3: ARCHITECTURE tree** — `:804` dashboard line becomes `…; graph_wire + graph routes (E-76); run graph/state routes, run_graph source (E-75)`; add under the `graph/` package entries (beside `router.py`/`validate.py` if listed; otherwise add one line) `run_view.py  # graph_view facts + projections (E-75)` and `store.py, start.py  # graphs/<sha>.yaml + client start (E-75)`.

- [ ] **Step 4: E-76 spec pointer** — directly under the `### 5.7 Run graph and run state (PROVISIONAL, E-75 on E-74)` heading add:

```markdown
> **Superseded by E-75** (`2026-09-17-graph-queries-design.md` §7.4): `terminal` is replaced by `outcome`, `NodeRunState.status` adds `skipped`/`cancelled`, `PendingRef.node` is nullable. The TS mirror follows in the canvas run-mode follow-up.
```

- [ ] **Step 5: CHECKPOINT gates** (each command separately)

- `pytest -q` (whole fast tier) — PASS
- `pytest tests/graph_workflow/test_graph_view_dispatch.py -m temporal -q --timeout=300 --timeout-method=thread`
- `pytest tests/graph_workflow/test_graph_view_query.py -m temporal -q --timeout=300 --timeout-method=thread`
- `pytest tests/graph_workflow/test_graph_dispatch.py -m temporal -q --timeout=300 --timeout-method=thread`
- `pytest tests/replay/test_graph_golden.py -m temporal -q --timeout=300 --timeout-method=thread` (SG-1)
- `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`

- [ ] **Step 6: Commit, then STOP**

Message: `docs: E-75 landing — roadmap, architecture, canvas spec pointer`. Add each doc path separately. Then STOP and report to the orchestrator: branch head, per-task commits, gate results, and any deviation. The orchestrator fast-forwards `main`.

---

## Spec coverage map (self-review)

| spec | task |
|---|---|
| §1.1 boundary (E-77 owns `graph_sha`/`canonical_stage` completeness) | consumed as-is: Task 2 (`None` canonical stage contributes nothing), Task 11 docs |
| §2.1 R-Q2 (client start + history backfill) | Tasks 6, 8 |
| D1 placement + purity pins | Tasks 1, 2, 6 |
| D2 raw facts out, dashboard projects | Tasks 4, 5, 7 |
| D3 payload store never exposed | Task 1 model (no payload fields), Task 4 test (`boom` message absent) |
| D4 context variable, single set site | Tasks 3, 4, 6 (pin) |
| D5 replay neutrality | Tasks 3 (feature replay), 5 (golden), 11 |
| D6 graph source = start input | Task 8 |
| D7 capabilities stay false | Task 8 test, Task 10 |
| D8 closed runs cached | Task 8 (views), Task 9 (marks) |
| §4.2 result after retro (F3), escalated_by (F4), unrouted failure (F5) | Tasks 4, 5 |
| §4.3 cost scope + Σ invariant (F12), pending join (F2) | Task 3 |
| §5.1 status table incl. R1 | Task 2 |
| §5.2 outcome table incl. `interrupted`, `not_started`, budget `Halt` (E74-OQ-1, F11) | Tasks 2, 7 |
| §5.3 stage marks (E76-OQ-3), type-filtered closed marks, pruning, failed query retry (F8, N1, r3 advisory) | Tasks 2, 5, 9 |
| §6.1 store (F6, F7), start helper (R2, N3) | Task 6 |
| §6.2 backfill + retention note (F9) | Task 8 docstring |
| §7.1–§7.3 routes; E74-OQ-4 severity | Tasks 7, 8 |
| §7.4 wire amendments, recorded fixtures (F1, F10) | Tasks 7, 10 |
| §8 grace retention (FeatureWorkflow → `no_graph`, `stage_marks` None) | Tasks 1, 8, 9 |
| §9 testing list | every task's Step 1 |
| §11 docs on landing | Tasks 3 (AGENTS.md), 11 |

**Plan-level refinement:** spec §5.3 says the fleet "queries `graph_view` once" per first-closed GraphWorkflow row. Task 9 queries `run_state` once instead (it already carries `stage_marks` computed from the same view) and applies `close_marks`, which Task 2 pins as equal to recomputing with `execution_closed=True`. Same bound, same marks, no fleet-side topology or history read. Task 9 Step 5 lands the matching §5.3 erratum in the same commit (reviewer R1).

**Deliberately structural coverage (reviewer R2):** spec §9's "handler-internal gate attribution" runs the same `GateHost._gate` line Task 5 exercises for a gate node and the same `ACTIVATION` inheritance Task 4 proves for handler sub-tasks; no separate handler-internal-gate probe is added (it would need the notify schedule and gate settings in a probe workflow for no additional code path). The F3 retro window is pinned on `GraphWorkflow.run`'s source order (Task 5) because the live window is too short to poll reliably.

## Plan review dispositions

### Skeptic (`.workspace/tmp/e75-plan-skeptic.md`)

| finding | disposition |
|---|---|
| P1 history purged / empty input → 500 | **Adopted:** `RPCError NOT_FOUND` and empty payloads → `RunNotFound` → 404 (Task 8, test added). |
| P4 `graph_view` query failure → 500 | **Adopted differently:** `RunQueryFailed` → **502**, never cached. Not projected as `view=None`: that would render a live or finished run as idle/`not_started`, a false state. |
| P2 closed runs replay `run_summary` every tick | **Rejected for E-75:** pre-existing behaviour, accepted as deferral E75-OQ-3 at the user gate. Task 9 adds at most one `run_state` query per closed graph run per process. |
| P3 recordings miss `completed` and `escalated` | **Adopted:** both recorded from real router steps; the test asserts all five outcome states (Task 10). |
| P5 bystander test asserted no bystander | **Adopted:** renamed, plus a `G2` graph with a live bystander under rejection and escalation (Task 2). |
| P6 default store root inside a worktree | **Rejected, clarified:** spec F7 accepted the relative anchoring; `/graphs/` is anchored at each checkout root and every worktree is a checkout root, so a CLI run from a worktree leaves nothing untracked. |
| P7 equivalence at the rejection boundary | **Adopted:** equivalence cases over the `G2` rejected and escalated states with a cancelled bystander (Task 2). |

### Reviewer round 1 (`.workspace/tmp/e75-plan-reviewer-r1.md`, CHANGES REQUESTED)

| finding | disposition |
|---|---|
| R1 fleet refinement contradicts spec §5.3's letter | **Adopted:** §5.3 erratum + D8 wording land in Task 9's commit (Step 5). |
| R2 three §9 items not literally pinned | **Adopted:** budget `Halt` row and strip mark (Task 2); retro-order source pin (Task 5). **Accepted as structural:** handler-internal gate attribution (same code line; rationale in the coverage section). |
| R3 imprecise RED reason in Task 4 | **Adopted.** |
| Advisory: "no frontend file changes" wording | **Adopted:** "no frontend *source* changes". |
