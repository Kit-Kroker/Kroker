# Dashboard Backend (E-10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard frontend's mock API with a real FastAPI backend serving live fleet state from Temporal, closing the last unbuilt half of P2.

**Architecture:** One new query, `run_state()`, exposes run state `FeatureWorkflow` already holds. A pure `fleet.py` module fans out `run_state()` + `pending_decisions()` across open runs (and `run_summary()` across recent closed ones) into a single `FleetSnapshot`, driven by a lazy shared poller. A FastAPI router serves REST reads from that snapshot plus an SSE stream, and three write routes that reuse `channels/transport.submit` unchanged. The frontend's `http.ts` maps domain models onto its existing view model.

**Tech Stack:** Python 3.14, Pydantic v2, FastAPI + `TestClient`, Temporal (`temporalio`), pytest (`pytest -m temporal` for the one e2e), Vue 3 + Vite + vitest.

**Spec:** `docs/superpowers/specs/2026-08-18-dashboard-backend-design.md` — D0…D7 are this plan's subject. Read it before Task 1; every task cites the decision it implements.

## Global Constraints

Copied from the spec and from the landed code's own rules. Every task's requirements implicitly include this section.

- **Sandbox purity.** `models.py` and `pending.py` import inside the Temporal workflow sandbox: pure Pydantic, no I/O, no `temporalio`, no agents. Anything added to them obeys that. `fleet.py` and `api.py` are outside the sandbox and may import freely.
- **`fleet.py` imports no FastAPI.** The fan-out and poller must be testable without an HTTP client, the way `channels/transport.py` is testable without a CLI. If a task tempts you to import `fastapi` there, stop — it belongs in `api.py`.
- **`cost_usd_total` is `float | None`, never `0.0` on failure.** `RoleUsage.cost_usd` documents why (`models.py:702`): *"tokens are facts from the run; dollars are a lookup that can fail."* Summing `None` to `0.0` makes a pricing failure read as a free run — the FR-915 defect class this project keeps closing.
- **`GateDecision.decided_by` stays `Literal["human", "policy", "timeout"]`.** Operator identity goes in `reviewer`. `ReadinessOverride.approved_by` carries `decided_by` verbatim so `"policy"`/`"timeout"` stay legible as non-human; widening it to a free string breaks that. See `triage.py:115`.
- **Per-run error isolation.** One run's failed query becomes an `InboxError` entry, never an exception that aborts the fan-out. `inbox.py:83` states the rule: *"Never raises: an exception becomes the return value, so one run's failure can't take down asyncio.gather for the rest."*
- **The Temporal client is always built with `pydantic_data_converter`** (`cli.py:317`). Without it `RunState` and `PendingDecision` do not round-trip, and the failure looks like a schema bug rather than a client bug.
- **Localhost-bind, no auth** (D4). Do not add auth middleware, tokens, or CORS. The dev proxy handles origin; E-60 handles identity.
- **No new dependency.** FastAPI, `httpx`, `temporalio`, `pytest-asyncio` are already present. Do not add `sse-starlette` — the SSE endpoint is a plain generator returning `text/event-stream`.
- **Fields with no source are dropped, never faked** (D3). If a frontend field has no backend origin, delete it from `types.ts`; do not invent a value.

---

## File Structure

**Created**

| Path | Responsibility |
|---|---|
| `src/sdlc/dashboard/__init__.py` | Empty package marker, matching `board/__init__.py`. |
| `src/sdlc/dashboard/fleet.py` | `FleetSnapshot`, the fan-out, and `FleetPoller`. No FastAPI import. |
| `src/sdlc/dashboard/channel.py` | `DashboardChannel` — `Channel` impl stamping `reviewer`. |
| `src/sdlc/dashboard/api.py` | `create_router()` — REST reads, SSE, three write routes. |
| `tests/test_dashboard_fleet.py` | Fan-out aggregation, error isolation, closed runs. |
| `tests/test_dashboard_poller.py` | Snapshot freshness, inline fan-out, lazy start/stop. |
| `tests/test_dashboard_channel.py` | `reviewer` stamping; `decided_by` untouched. |
| `tests/test_dashboard_api.py` | Route shapes, 409, `confirmed:false`, `X-Actor`. |
| `tests/test_dashboard_sse.py` | Emit-on-change, suppress-identical, heartbeat. |
| `tests/test_run_state_query.py` | `run_state()` projection from workflow state. |
| `tests/test_dashboard_e2e.py` | `pytest -m temporal` — one real run, real query. |
| `scripts/dump_dashboard_fixtures.py` | Writes JSON fixtures from the Pydantic models. |
| `interfaces/dashboard/frontend/src/api/http.test.ts` | The mapper, fed by those fixtures. |

**Modified**

| Path | Change |
|---|---|
| `src/sdlc/models.py` | `RunState`; `title` + `repo_url` on `RunSummary`. |
| `src/sdlc/pending.py` | `opened_at` on the four variants and both builders. |
| `src/sdlc/workflows/feature.py` | Stash `self._idea`; `run_state()` query; populate the two new `RunSummary` fields. |
| `src/sdlc/channels/transport.py` | `match_key()`. |
| `interfaces/dashboard/api/main.py` | Compose board + dashboard routers. |
| `interfaces/dashboard/frontend/src/api/types.ts` | `subscribe`; `description`; drop three fields. |
| `interfaces/dashboard/frontend/src/api/http.ts` | The real provider. |
| `interfaces/dashboard/frontend/src/api/mock/index.ts` | `subscribe` over the existing timer. |
| `interfaces/dashboard/frontend/vite.config.ts` | Dev proxy for `/api`. |
| `ROADMAP.md`, `ARCHITECTURE.md` | The spec's §9 consequences. |

**Not touched:** `src/sdlc/board/` (D2 keeps it a separate factory), `workflows/gates.py` (the query lives on `FeatureWorkflow`, not `GateHost` — §4), `channels/contract.py` (extended by implementing its Protocol, never edited). If a task tempts you to edit `gates.py` or `contract.py`, stop: it means a contract drifted.

---

### Task 1: `opened_at` on the pending variants

Implements spec §4.1. Without this, inbox item age has no source.

**Files:**
- Modify: `src/sdlc/pending.py`
- Test: `tests/test_pending_opened_at.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ClarifyPending.opened_at: datetime | None`, `StageGatePending.opened_at`, `TaskEscalationPending.opened_at`, `MergeGatePending.opened_at`. Builders gain a keyword-only `opened_at: datetime | None = None`: `clarify_pending(open_questions, answered_ids, *, opened_at=None)` and `gate_pending(name, round, context, *, opened_at=None)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pending_opened_at.py`:

```python
"""opened_at on the pending variants (spec 4.1). E-9 already proves the value
exists at gate-open time (gates.py:118 passes it into NotifyInput); this
exposes it so a surface can render 'waiting 4h'."""

from datetime import datetime, timezone

from sdlc.models import OpenQuestion
from sdlc.pending import GateContext, clarify_pending, gate_pending

AT = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)


def test_gate_pending_records_opened_at():
    p = gate_pending("architecture", 1, None, opened_at=AT)
    assert p.opened_at == AT


def test_merge_gate_pending_records_opened_at():
    ctx = GateContext(verdict="approve")
    p = gate_pending("merge", 2, ctx, opened_at=AT)
    assert p.opened_at == AT


def test_task_escalation_pending_records_opened_at():
    ctx = GateContext(task_id="T01", analysis="a", attempts=3)
    p = gate_pending("task:T01", 1, ctx, opened_at=AT)
    assert p.opened_at == AT


def test_clarify_pending_records_opened_at_on_every_item():
    qs = [
        OpenQuestion(id="Q1", question="q1", why_it_matters="w"),
        OpenQuestion(id="Q2", question="q2", why_it_matters="w"),
    ]
    out = clarify_pending(qs, set(), opened_at=AT)
    assert [p.opened_at for p in out] == [AT, AT]


def test_opened_at_defaults_to_none_so_existing_callers_are_unaffected():
    assert gate_pending("architecture", 1, None).opened_at is None
    qs = [OpenQuestion(id="Q1", question="q", why_it_matters="w")]
    assert clarify_pending(qs, set())[0].opened_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pending_opened_at.py -v`
Expected: FAIL — `TypeError: gate_pending() got an unexpected keyword argument 'opened_at'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/pending.py`, add `from datetime import datetime` to the imports. Add this field to all four variant classes (`ClarifyPending`, `StageGatePending`, `TaskEscalationPending`, `MergeGatePending`):

```python
    opened_at: datetime | None = None
```

Then change the two builders to thread it through:

```python
def clarify_pending(
    open_questions: list[OpenQuestion],
    answered_ids: set[str],
    *,
    opened_at: datetime | None = None,
) -> list[ClarifyPending]:
    """One ClarifyPending per still-unanswered open question."""
    return [
        ClarifyPending(
            key=q.id,
            question=q.question,
            why_it_matters=q.why_it_matters,
            suggested_answer=q.suggested_answer,
            opened_at=opened_at,
        )
        for q in open_questions
        if q.id not in answered_ids
    ]


def gate_pending(
    name: str,
    round: int,
    context: GateContext | None,
    *,
    opened_at: datetime | None = None,
) -> PendingDecision:
    """Build the render variant a gate wait should surface. The gate name is
    the discriminator: 'merge' -> MergeGatePending, 'task:<id>' ->
    TaskEscalationPending, anything else -> StageGatePending."""
    key = gate_key(name, round)
    ctx = context or GateContext()
    if name == "merge":
        return MergeGatePending(
            key=key,
            gate=name,
            round=round,
            checks=ctx.checks,
            verdict=ctx.verdict,
            opened_at=opened_at,
        )
    if name.startswith("task:"):
        return TaskEscalationPending(
            key=key,
            gate=name,
            round=round,
            task_id=ctx.task_id or name.removeprefix("task:"),
            analysis=ctx.analysis or "",
            attempts=ctx.attempts or 0,
            opened_at=opened_at,
        )
    return StageGatePending(
        key=key, gate=name, round=round, spec_summary=ctx.spec_summary or "", opened_at=opened_at
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pending_opened_at.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Verify nothing else broke**

Run: `pytest tests/test_channel_contract.py tests/test_channel_inbox.py tests/test_channel_transport.py -v`
Expected: PASS — the default of `None` means every existing caller is unaffected.

- [ ] **Step 6: Wire the gate to pass it**

In `src/sdlc/workflows/gates.py`, in `_gate`, change the `gate_pending` call so the pending item records when it opened. Find:

```python
            pending = gate_pending(name, round, context)
```

Replace with:

```python
pending = gate_pending(name, round, context, opened_at=workflow.now())
```

`workflow.now()` is replay-deterministic and `_pending[key]` is written once per item, so this is safe inside the sandbox.

- [ ] **Step 7: Run the gate tests**

Run: `pytest tests/ -k "gate or pending" -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/pending.py src/sdlc/workflows/gates.py tests/test_pending_opened_at.py
git commit -m "feat(pending): record opened_at on pending decisions (E-10)"
```

---

### Task 2: `RunState` and the `RunSummary` additions

Implements spec §4 and D7's second paragraph.

**Files:**
- Modify: `src/sdlc/models.py` (add `RunState` after `RunSummary` at `:1169`; add two fields to `RunSummary`)
- Test: `tests/test_run_state_model.py` (create)

**Interfaces:**
- Consumes: `RoleUsage` (`models.py:699`), `GateDecision` (`models.py:814`).
- Produces:
  ```python
  class RunState(BaseModel):
      run_id: str
      title: str
      repo_url: str | None = None
      mode: str
      status: str
      current_stage: str | None = None
      started_at: datetime
      decisions: list[GateDecision] = []
      roles: list[RoleUsage] = []
      cost_usd_total: float | None = None
      budget_usd: float | None = None
      budget_crossings: int = 0
  ```
  and `RunSummary.title: str = ""`, `RunSummary.repo_url: str | None = None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_state_model.py`:

```python
"""RunState is RunSummary's live sibling: same field names where they
overlap, so the fleet view and the retro report cannot develop two
vocabularies for one concept (spec 4)."""

from datetime import datetime, timezone

from sdlc.models import GateDecision, GateOutcome, RoleUsage, RunState, RunSummary

AT = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)


def test_run_state_defaults_to_an_unpriced_run():
    s = RunState(run_id="feature-x", title="X", mode="greenfield", status="running", started_at=AT)
    assert s.cost_usd_total is None
    assert s.budget_usd is None
    assert s.decisions == []
    assert s.roles == []
    assert s.current_stage is None


def test_run_state_carries_decisions_and_roles():
    d = GateDecision(gate="architecture", round=1, outcome=GateOutcome.APPROVE, decided_by="human")
    u = RoleUsage(role="architect", model="m", calls=1, cost_usd=0.5)
    s = RunState(
        run_id="r",
        title="T",
        mode="brownfield",
        status="running",
        started_at=AT,
        decisions=[d],
        roles=[u],
        cost_usd_total=0.5,
        budget_usd=40.0,
    )
    assert s.decisions[0].gate == "architecture"
    assert s.roles[0].role == "architect"


def test_run_state_mirrors_run_summary_field_names_where_they_overlap():
    """A rename on either side must break this test, not the dashboard."""
    shared = {
        "run_id",
        "mode",
        "started_at",
        "cost_usd_total",
        "budget_usd",
        "budget_crossings",
        "roles",
        "title",
        "repo_url",
    }
    assert shared <= set(RunState.model_fields)
    assert shared <= set(RunSummary.model_fields)


def test_run_summary_carries_title_and_repo_url_for_closed_runs():
    """D7: a closed run renders from run_summary(); without these it would
    render as a bare workflow id."""
    s = RunSummary(
        run_id="feature-add-sso",
        mode="brownfield",
        outcome="deployed:ok",
        terminal_stage="retro",
        started_at=AT,
        ended_at=AT,
        duration_s=1.0,
        title="Add SSO",
        repo_url="git@example:acme/portal",
    )
    assert s.title == "Add SSO"
    assert s.repo_url == "git@example:acme/portal"


def test_run_summary_title_defaults_empty_so_existing_callers_are_unaffected():
    s = RunSummary(
        run_id="r",
        mode="greenfield",
        outcome="done",
        terminal_stage="retro",
        started_at=AT,
        ended_at=AT,
        duration_s=1.0,
    )
    assert s.title == ""
    assert s.repo_url is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_run_state_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'RunState' from 'sdlc.models'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/models.py`, add two fields to `RunSummary` (after `mode: str`):

```python
title: str = ""  # E-10: closed runs render from here
repo_url: str | None = None
```

Then add `RunState` immediately after the `RunSummary` class body:

```python
class RunState(BaseModel):
    """Live counterpart to RunSummary: what a run looks like mid-flight,
    exposed via the run_state() query (E-10).

    Field names mirror RunSummary where they overlap, deliberately -- the
    fleet view and the retro report describe the same run, and two
    vocabularies for one concept is how they come to disagree.

    cost_usd_total stays None rather than 0.0 when pricing failed: see
    RoleUsage.cost_usd. A pricing miss must never read as a free run.
    """

    run_id: str
    title: str
    repo_url: str | None = None
    mode: str
    status: str  # GateHost._status verbatim
    current_stage: str | None = None  # last STAGE_STARTED in _trace
    started_at: datetime
    decisions: list[GateDecision] = Field(default_factory=list)
    roles: list[RoleUsage] = Field(default_factory=list)
    cost_usd_total: float | None = None
    budget_usd: float | None = None
    budget_crossings: int = 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_run_state_model.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the full fast suite**

Run: `pytest`
Expected: PASS — both `RunSummary` fields default, so nothing existing changes.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py tests/test_run_state_model.py
git commit -m "feat(models): add RunState and RunSummary title/repo_url (E-10)"
```

---

### Task 3: the `run_state()` query

Implements spec D1. This is the only workflow change in the plan.

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (stash `_idea`; add the query; populate the two new `RunSummary` fields)
- Test: `tests/test_run_state_query.py` (create)

**Interfaces:**
- Consumes: `RunState` (Task 2). Workflow state: `self._status` (`gates.py:53`), `self._gate_decisions` (`gates.py:51`), `self._role_usage` (`feature.py:567`), `self._trace` (`feature.py:560`), `self._cfg` (`feature.py:553`), `self._budget_crossings` (`feature.py:569`).
- Produces: `FeatureWorkflow.run_state() -> RunState | None` (query name `"run_state"`), returning `None` before `run()` has stashed the brief.

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_state_query.py`. This tests the projection directly on an instance — no Temporal server needed, matching how the codebase unit-tests workflow helpers:

```python
"""run_state() projects state the run already holds (spec D1). No new
bookkeeping: every field is read from existing workflow state."""

from datetime import datetime, timezone

from sdlc.models import GateDecision, GateOutcome, IdeaBrief, PipelineConfig, ProjectMode, RoleUsage
from sdlc.observability.trace import RunEvent, RunEventKind
from sdlc.workflows.feature import FeatureWorkflow

AT = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)


def _wf(**overrides):
    """A FeatureWorkflow instance with state set directly. __init__ touches
    no Temporal API, so this is safe outside a workflow environment."""
    wf = FeatureWorkflow()
    wf._idea = overrides.pop(
        "idea",
        IdeaBrief(
            title="Add SSO",
            description="d",
            mode=ProjectMode.BROWNFIELD,
            repo_url="git@example:acme/portal",
        ),
    )
    wf._cfg = overrides.pop("cfg", PipelineConfig())
    wf._started_at = overrides.pop("started_at", AT)
    for k, v in overrides.items():
        setattr(wf, k, v)
    return wf


def test_run_state_is_none_before_the_brief_is_stashed():
    wf = FeatureWorkflow()
    assert wf.run_state() is None


def test_run_state_projects_title_repo_and_mode_from_the_brief():
    s = _wf().run_state()
    assert s.title == "Add SSO"
    assert s.repo_url == "git@example:acme/portal"
    assert s.mode == "brownfield"


def test_run_state_reports_status_verbatim():
    wf = _wf()
    wf._status = "awaiting:architecture"
    assert wf.run_state().status == "awaiting:architecture"


def test_current_stage_is_the_last_stage_started():
    wf = _wf(
        _trace=[
            RunEvent(seq=1, at=AT, kind=RunEventKind.STAGE_STARTED, stage="clarify"),
            RunEvent(seq=2, at=AT, kind=RunEventKind.STAGE_ENDED, stage="clarify"),
            RunEvent(seq=3, at=AT, kind=RunEventKind.STAGE_STARTED, stage="architecture"),
        ]
    )
    assert wf.run_state().current_stage == "architecture"


def test_current_stage_is_none_when_no_stage_has_started():
    assert _wf().run_state().current_stage is None


def test_decisions_are_returned_in_insertion_order():
    a = GateDecision(gate="architecture", round=1, outcome=GateOutcome.APPROVE, decided_by="human")
    m = GateDecision(gate="merge", round=1, outcome=GateOutcome.APPROVE, decided_by="policy")
    wf = _wf()
    wf._gate_decisions = {"architecture#1": a, "merge#1": m}
    assert [d.gate for d in wf.run_state().decisions] == ["architecture", "merge"]


def test_cost_total_sums_priced_roles():
    wf = _wf(
        _role_usage={
            "architect": RoleUsage(role="architect", model="m", cost_usd=1.5),
            "dev": RoleUsage(role="dev", model="m", cost_usd=2.25),
        }
    )
    assert wf.run_state().cost_usd_total == 3.75


def test_cost_total_is_none_when_no_role_was_ever_priced():
    """A pricing miss must never read as a free run (RoleUsage.cost_usd)."""
    wf = _wf(
        _role_usage={
            "architect": RoleUsage(role="architect", model="m", cost_usd=None),
        }
    )
    assert wf.run_state().cost_usd_total is None


def test_cost_total_sums_what_was_priced_when_some_roles_are_unpriced():
    wf = _wf(
        _role_usage={
            "architect": RoleUsage(role="architect", model="m", cost_usd=1.5),
            "dev": RoleUsage(role="dev", model="m", cost_usd=None),
        }
    )
    assert wf.run_state().cost_usd_total == 1.5


def test_budget_is_none_when_the_run_budget_is_off():
    cfg = PipelineConfig()
    cfg.run_budget_usd = 0.0
    assert _wf(cfg=cfg).run_state().budget_usd is None


def test_budget_is_reported_when_configured():
    cfg = PipelineConfig()
    cfg.run_budget_usd = 40.0
    assert _wf(cfg=cfg).run_state().budget_usd == 40.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_run_state_query.py -v`
Expected: FAIL — `AttributeError: 'FeatureWorkflow' object has no attribute 'run_state'`

- [ ] **Step 3: Add the stashed state**

In `src/sdlc/workflows/feature.py`, in `FeatureWorkflow.__init__`, add beside the existing `_cfg` stash (around `:553`):

```python
        # E-10: run_state() needs the brief and the start time, which are
        # run() parameters/locals everywhere else -- same reason _cfg is
        # stashed here rather than threaded.
        self._idea: IdeaBrief | None = None
        self._started_at: datetime | None = None
```

- [ ] **Step 4: Populate them in `run()`**

In `run()`, immediately after the two `model_validate` coercions (around `:1622`), add:

```python
        self._idea = idea
        self._started_at = workflow.now()
```

- [ ] **Step 5: Add the query**

Add beside the existing `run_summary` query (around `:821`):

```python
@workflow.query
def run_state(self) -> RunState | None:
    """Live run state for the dashboard fleet view (E-10).

    None until run() stashes the brief. Every field is read from state
    the run already holds -- this query adds no bookkeeping.
    """
    if self._idea is None or self._started_at is None:
        return None
    priced = [u.cost_usd for u in self._role_usage.values() if u.cost_usd is not None]
    budget = self._cfg.run_budget_usd if self._cfg and self._cfg.run_budget_usd > 0 else None
    stage = next(
        (e.stage for e in reversed(self._trace) if e.kind is RunEventKind.STAGE_STARTED), None
    )
    return RunState(
        run_id=workflow.info().workflow_id,
        title=self._idea.title,
        repo_url=self._idea.repo_url,
        mode=self._idea.mode.value,
        status=self._status,
        current_stage=stage,
        started_at=self._started_at,
        decisions=list(self._gate_decisions.values()),
        roles=list(self._role_usage.values()),
        # None, not 0.0: a pricing miss must never read as a free run.
        cost_usd_total=sum(priced) if priced else None,
        budget_usd=budget,
        budget_crossings=self._budget_crossings,
    )
```

Add `RunState` to the existing `from ..models import (...)` block inside `workflow.unsafe.imports_passed_through()`, and `datetime` to the imports if not already present.

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_run_state_query.py -v`
Expected: PASS (11 passed)

- [ ] **Step 7: Populate the new `RunSummary` fields**

Find where `_retro` builds the `RunSummary` (search `RunSummary(` in `feature.py`) and add to its constructor call:

```python
title = (idea.title,)
repo_url = (idea.repo_url,)
```

- [ ] **Step 8: Run the workflow suites**

Run: `pytest tests/ -k "feature or retro or run_summary" -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_run_state_query.py
git commit -m "feat(workflow): add run_state() query for the fleet view (E-10)"
```

---

### Task 4: `match_key()` on the transport

Implements spec §6's first bullet. Lives in `transport.py` because that module's job is being written once per surface (`transport.py:6`).

**Files:**
- Modify: `src/sdlc/channels/transport.py`
- Test: `tests/test_channel_transport.py` (extend)

**Interfaces:**
- Consumes: `PendingDecision` (`pending.py`), `NoMatch` (`transport.py:50`).
- Produces: `match_key(pendings: Sequence[PendingDecision], key: str) -> PendingDecision`, raising `NoMatch` when absent. And `resolve_key(handle, key) -> PendingDecision` (async), the `resolve()` sibling.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_channel_transport.py`:

```python
from sdlc.channels.transport import match_key


def test_match_key_finds_the_item_by_its_resolution_key():
    """The dashboard operator clicked a specific item, so it addresses the
    key directly -- Selector's ambiguity resolution is a CLI concern that
    here would only add a way to hit the wrong item (spec 6)."""
    q1 = ClarifyPending(key="Q1", question="q1", why_it_matters="w")
    arch = StageGatePending(key="architecture#1", gate="architecture", round=1, spec_summary="s")
    assert match_key([q1, arch], "architecture#1") is arch
    assert match_key([q1, arch], "Q1") is q1


def test_match_key_raises_no_match_and_lists_what_is_pending():
    q1 = ClarifyPending(key="Q1", question="q1", why_it_matters="w")
    with pytest.raises(NoMatch) as e:
        match_key([q1], "merge#1")
    assert "merge#1" in e.value.message
    assert "Q1" in e.value.message


def test_match_key_raises_no_match_on_an_empty_pending_list():
    with pytest.raises(NoMatch):
        match_key([], "merge#1")
```

Add `match_key` to the existing `from sdlc.channels.transport import ...` line, and make sure `pytest`, `NoMatch`, `ClarifyPending` and `StageGatePending` are imported at the top of the file (add any that are missing).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_channel_transport.py -k match_key -v`
Expected: FAIL — `ImportError: cannot import name 'match_key'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/sdlc/channels/transport.py`, directly after `match()`:

```python
def match_key(pendings: Sequence[PendingDecision], key: str) -> PendingDecision:
    """Resolve a pending item by its exact resolution key, or raise NoMatch.

    match()'s sibling for surfaces that already hold the key -- the dashboard
    operator clicked a specific item, so Selector's reply_kind narrowing and
    ambiguity resolution would only introduce a way to hit the wrong one.
    Keys are unique by construction (question id, or gate_key(gate, round)),
    so there is no Ambiguous case here.
    """
    for d in pendings:
        if d.key == key:
            return d
    head = f"no pending item with key '{key}' on this run"
    if pendings:
        head += f"\ncurrently pending:\n{_listing(pendings)}"
    raise NoMatch(head, candidates=list(pendings))


async def resolve_key(handle, key: str) -> PendingDecision:
    """resolve()'s sibling: fetch what is pending and address one by key."""
    return match_key(await fetch_pending(handle), key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_channel_transport.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/channels/transport.py tests/test_channel_transport.py
git commit -m "feat(channels): add match_key/resolve_key for key-addressed surfaces (E-10)"
```

---

### Task 5: `DashboardChannel`

Implements spec §6's second bullet, as corrected: identity goes in `reviewer`, not `decided_by`.

**Files:**
- Create: `src/sdlc/dashboard/__init__.py`, `src/sdlc/dashboard/channel.py`
- Test: `tests/test_dashboard_channel.py` (create)

**Interfaces:**
- Consumes: `default_render`, `default_translate`, `Channel`, `Reply`, `SignalCall`, `RenderedDecision` (`channels/contract.py`).
- Produces: `DashboardChannel(actor: str)` implementing the `Channel` protocol.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_channel.py`:

```python
"""DashboardChannel stamps operator identity onto GateDecision.reviewer.

NOT decided_by: that is Literal["human","policy","timeout"] (models.py:818)
and ReadinessOverride.approved_by carries it verbatim so "policy" and
"timeout" stay legible as non-human. reviewer is the established home for a
self-asserted identity -- triage.py:115 does exactly this.
"""

from sdlc.channels.contract import Reply
from sdlc.dashboard.channel import DashboardChannel
from sdlc.models import GateOutcome
from sdlc.pending import ClarifyPending, StageGatePending

ARCH = StageGatePending(key="architecture#1", gate="architecture", round=1, spec_summary="s")
Q1 = ClarifyPending(key="Q1", question="q", why_it_matters="w")


def test_translate_stamps_the_actor_onto_reviewer():
    ch = DashboardChannel(actor="human:mika")
    call = ch.translate(ARCH, Reply(outcome=GateOutcome.APPROVE, text="ok"))
    assert call.decision.reviewer == "human:mika"


def test_translate_leaves_decided_by_as_human():
    ch = DashboardChannel(actor="human:mika")
    call = ch.translate(ARCH, Reply(outcome=GateOutcome.APPROVE))
    assert call.decision.decided_by == "human"


def test_translate_preserves_gate_and_round_from_the_pending_item():
    ch = DashboardChannel(actor="human:sam")
    call = ch.translate(ARCH, Reply(outcome=GateOutcome.REVISE, text="split"))
    assert (call.decision.gate, call.decision.round) == ("architecture", 1)
    assert call.decision.guidance == "split"


def test_translate_of_a_clarify_reply_is_untouched_by_the_actor():
    """answer_question carries no identity field; stamping must not crash."""
    ch = DashboardChannel(actor="human:mika")
    call = ch.translate(Q1, Reply(text="OIDC"))
    assert call.signal == "answer_question"
    assert call.question_id == "Q1"
    assert call.answer == "OIDC"


def test_render_delegates_to_the_default():
    ch = DashboardChannel(actor="human:mika")
    assert ch.render(ARCH).reply_kind == "gate"
    assert ch.render(Q1).reply_kind == "text"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_channel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.dashboard'`

- [ ] **Step 3: Write minimal implementation**

Create empty `src/sdlc/dashboard/__init__.py`. Create `src/sdlc/dashboard/channel.py`:

```python
"""The dashboard's Channel adapter (E-10).

contract.py states that "a surface MAY override render for richer
presentation"; this uses that extension point to carry operator identity
without adding a parameter to the pure default_translate.

The identity lands on GateDecision.reviewer, NEVER on decided_by:
decided_by is Literal["human","policy","timeout"] and ReadinessOverride
.approved_by carries it verbatim, so a free-string actor there would
destroy the one signal that keeps "policy" legible as non-human.
triage.py:115 sets reviewer for exactly this reason (FR-1004).
"""

from __future__ import annotations

from ..channels.contract import (
    RenderedDecision,
    Reply,
    SignalCall,
    default_render,
    default_translate,
)
from ..pending import PendingDecision


class DashboardChannel:
    """Channel impl carrying a self-asserted operator identity (OQ-11)."""

    def __init__(self, actor: str) -> None:
        self.actor = actor

    def render(self, d: PendingDecision) -> RenderedDecision:
        return default_render(d)

    def translate(self, d: PendingDecision, reply: Reply) -> SignalCall:
        call = default_translate(d, reply)
        if call.decision is not None:
            call.decision.reviewer = self.actor
        return call
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_channel.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Verify it satisfies the Channel protocol**

Run: `python -c "from sdlc.channels.contract import Channel; from sdlc.dashboard.channel import DashboardChannel; assert isinstance(DashboardChannel('a'), Channel); print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/dashboard/ tests/test_dashboard_channel.py
git commit -m "feat(dashboard): add DashboardChannel stamping reviewer identity (E-10)"
```

---

### Task 6: the fan-out

Implements spec §5.1.

**Files:**
- Create: `src/sdlc/dashboard/fleet.py`
- Test: `tests/test_dashboard_fleet.py` (create)

**Interfaces:**
- Consumes: `RunInbox`, `InboxError`, `list_open_run_ids` (`channels/inbox.py`), `RunState`, `RunSummary` (Task 2), `fetch_pending` (`channels/transport.py`).
- Produces:
  ```python
  class FleetSnapshot(BaseModel):
      at: datetime
      total_open_runs: int = 0
      runs: list[RunState] = []
      closed: list[RunSummary] = []
      inbox: list[RunInbox] = []
      errors: list[InboxError] = []

  CLOSED_LIMIT = 20
  async def fetch_fleet(client, *, now: datetime,
                        closed_limit: int = CLOSED_LIMIT) -> FleetSnapshot
  ```

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_fleet.py`:

```python
"""The fleet fan-out (spec 5.1). Generalizes inbox.py's pattern: one run's
failed query becomes an errors[] entry, never an exception that aborts the
page (inbox.py:83)."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from sdlc.dashboard.fleet import FleetSnapshot, fetch_fleet
from sdlc.models import RunState, RunSummary
from sdlc.pending import ClarifyPending, StageGatePending

AT = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)

ARCH = StageGatePending(key="architecture#1", gate="architecture", round=1, spec_summary="s")
Q1 = ClarifyPending(key="Q1", question="q", why_it_matters="w")


def _state(run_id, **kw):
    return RunState(
        run_id=run_id,
        title=kw.pop("title", "T"),
        mode=kw.pop("mode", "greenfield"),
        status=kw.pop("status", "running"),
        started_at=AT,
        **kw,
    )


def _summary(run_id):
    return RunSummary(
        run_id=run_id,
        mode="greenfield",
        outcome="deployed:ok",
        terminal_stage="retro",
        started_at=AT,
        ended_at=AT,
        duration_s=1.0,
        title="Closed one",
    )


class _Handle:
    """Scripts one response per query name, or raises."""

    def __init__(self, *, state=None, pending=None, summary=None, error=None):
        self._r = {"run_state": state, "pending_decisions": pending or [], "run_summary": summary}
        self._error = error

    async def query(self, name):
        if self._error is not None:
            raise self._error
        v = self._r[name]
        if isinstance(v, list):
            return [i.model_dump(mode="json") for i in v]
        return v.model_dump(mode="json") if v is not None else None


class _Client:
    def __init__(self, open_handles, closed_handles=None):
        self._open = open_handles
        self._closed = closed_handles or {}

    async def list_workflows(self, query):
        ids = self._open if "Running" in query else self._closed
        for run_id in ids:
            yield SimpleNamespace(id=run_id)

    def get_workflow_handle(self, run_id):
        return {**self._open, **self._closed}[run_id]


@pytest.mark.asyncio
async def test_fetch_fleet_aggregates_state_and_pending_per_run():
    client = _Client(
        {
            "run-a": _Handle(state=_state("run-a"), pending=[ARCH]),
            "run-b": _Handle(state=_state("run-b"), pending=[]),
        }
    )
    snap = await fetch_fleet(client, now=AT)
    assert snap.total_open_runs == 2
    assert {r.run_id for r in snap.runs} == {"run-a", "run-b"}
    # a run with nothing pending is dropped from the inbox, not from runs
    assert [i.run_id for i in snap.inbox] == ["run-a"]


@pytest.mark.asyncio
async def test_one_failing_run_becomes_an_error_not_an_exception():
    client = _Client(
        {
            "run-a": _Handle(state=_state("run-a"), pending=[Q1]),
            "run-bad": _Handle(error=RuntimeError("workflow not found")),
        }
    )
    snap = await fetch_fleet(client, now=AT)
    assert [r.run_id for r in snap.runs] == ["run-a"]
    assert [e.run_id for e in snap.errors] == ["run-bad"]
    assert "workflow not found" in snap.errors[0].error


@pytest.mark.asyncio
async def test_total_open_runs_counts_every_run_including_failed_ones():
    """'no runs listed' and 'checked 2, none had anything' must stay
    distinguishable (Inbox.total_open_runs' documented reason)."""
    client = _Client(
        {
            "run-a": _Handle(state=_state("run-a")),
            "run-bad": _Handle(error=RuntimeError("boom")),
        }
    )
    snap = await fetch_fleet(client, now=AT)
    assert snap.total_open_runs == 2


@pytest.mark.asyncio
async def test_closed_runs_are_rendered_from_run_summary():
    client = _Client(
        {"run-a": _Handle(state=_state("run-a"))}, {"run-old": _Handle(summary=_summary("run-old"))}
    )
    snap = await fetch_fleet(client, now=AT)
    assert [c.run_id for c in snap.closed] == ["run-old"]
    assert snap.closed[0].title == "Closed one"


@pytest.mark.asyncio
async def test_closed_runs_are_capped():
    closed = {f"run-{i}": _Handle(summary=_summary(f"run-{i}")) for i in range(5)}
    client = _Client({}, closed)
    snap = await fetch_fleet(client, now=AT, closed_limit=2)
    assert len(snap.closed) == 2


@pytest.mark.asyncio
async def test_a_closed_run_whose_summary_is_none_is_skipped_not_errored():
    """run_summary() returns None on a run that terminated before retro."""
    client = _Client({}, {"run-old": _Handle(summary=None)})
    snap = await fetch_fleet(client, now=AT)
    assert snap.closed == []
    assert snap.errors == []


@pytest.mark.asyncio
async def test_empty_fleet_is_an_empty_snapshot_not_an_error():
    snap = await fetch_fleet(_Client({}), now=AT)
    assert snap == FleetSnapshot(at=AT)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_fleet.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.dashboard.fleet'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/dashboard/fleet.py`:

```python
"""Fleet fan-out and snapshot for the dashboard backend (E-10).

Imports no FastAPI: the fan-out and the poller are where the interesting
failures live, so they must be testable without an HTTP client -- the same
reason channels/transport.py is testable without a CLI.

Generalizes channels/inbox.py's pattern to two queries per handle, and adds
a capped second pass over recently CLOSED runs. That second pass is why the
dashboard needs no database (spec D7): Temporal keeps closed workflows
queryable for its retention period, so Temporal is the store. The bound is
real -- history reaches back only as far as that retention.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from pydantic import BaseModel, Field, TypeAdapter

from ..channels.inbox import InboxError, RunInbox, list_open_run_ids
from ..models import RunState, RunSummary
from ..pending import PendingDecision

CLOSED_LIMIT = 20

_CLOSED_QUERY = "WorkflowType='FeatureWorkflow' AND ExecutionStatus!='Running'"

_PENDING_LIST = TypeAdapter(list[PendingDecision])


class FleetSnapshot(BaseModel):
    """One fan-out's result. Everything the dashboard serves derives from
    this -- both REST reads and every SSE event."""

    at: datetime
    total_open_runs: int = 0
    runs: list[RunState] = Field(default_factory=list)
    closed: list[RunSummary] = Field(default_factory=list)
    inbox: list[RunInbox] = Field(default_factory=list)
    errors: list[InboxError] = Field(default_factory=list)


async def _fetch_open(client, run_id: str):
    """Never raises: an exception becomes the return value, so one run's
    failure can't take down asyncio.gather for the rest (inbox.py:83)."""
    try:
        handle = client.get_workflow_handle(run_id)
        raw_state, raw_pending = await asyncio.gather(
            handle.query("run_state"), handle.query("pending_decisions")
        )
        state = RunState.model_validate(raw_state) if raw_state is not None else None
        return state, _PENDING_LIST.validate_python(raw_pending or [])
    except Exception as e:  # noqa: BLE001 -- captured into errors[]
        return e


async def _fetch_closed(client, run_id: str):
    try:
        handle = client.get_workflow_handle(run_id)
        raw = await handle.query("run_summary")
        # None is ordinary: a run that terminated before retro has no
        # summary. That is a skip, not an error.
        return RunSummary.model_validate(raw) if raw is not None else None
    except Exception as e:  # noqa: BLE001
        return e


async def _closed_run_ids(client, limit: int) -> list[str]:
    ids: list[str] = []
    async for wf in client.list_workflows(_CLOSED_QUERY):
        ids.append(wf.id)
        if len(ids) >= limit:
            break
    return ids


async def fetch_fleet(client, *, now: datetime, closed_limit: int = CLOSED_LIMIT) -> FleetSnapshot:
    """Discover open and recently-closed runs and fan out over both."""
    open_ids = await list_open_run_ids(client)
    closed_ids = await _closed_run_ids(client, closed_limit)

    open_results, closed_results = await asyncio.gather(
        asyncio.gather(*(_fetch_open(client, r) for r in open_ids)),
        asyncio.gather(*(_fetch_closed(client, r) for r in closed_ids)),
    )

    snap = FleetSnapshot(at=now, total_open_runs=len(open_ids))
    for run_id, outcome in zip(open_ids, open_results):
        if isinstance(outcome, Exception):
            snap.errors.append(InboxError(run_id=run_id, error=str(outcome)))
            continue
        state, pending = outcome
        if state is not None:
            snap.runs.append(state)
        if pending:
            # A run with nothing pending is dropped from the inbox, not from
            # runs -- it is still live, it just owes no decision.
            snap.inbox.append(RunInbox(run_id=run_id, pending=pending))

    for run_id, outcome in zip(closed_ids, closed_results):
        if isinstance(outcome, Exception):
            snap.errors.append(InboxError(run_id=run_id, error=str(outcome)))
        elif outcome is not None:
            snap.closed.append(outcome)
    return snap
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_fleet.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Confirm the no-FastAPI rule holds**

Run: `python -c "import ast,sys; src=open('src/sdlc/dashboard/fleet.py').read(); assert 'fastapi' not in src.lower(); print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/dashboard/fleet.py tests/test_dashboard_fleet.py
git commit -m "feat(dashboard): add the fleet fan-out and snapshot (E-10)"
```

---

### Task 7: the lazy poller

Implements spec D6 and §5.2.

**Files:**
- Modify: `src/sdlc/dashboard/fleet.py` (append `FleetPoller`)
- Test: `tests/test_dashboard_poller.py` (create)

**Interfaces:**
- Consumes: `fetch_fleet`, `FleetSnapshot` (Task 6).
- Produces:
  ```python
  class FleetPoller:
      def __init__(self, client_factory, *, interval: float = 2.0,
                   grace_s: float = 30.0, clock=None, fetch=None)
      async def snapshot(self) -> FleetSnapshot
      @contextlib.asynccontextmanager
      def subscribe(self)  # yields an asyncio.Queue[FleetSnapshot]
      @property
      def running(self) -> bool
      async def aclose(self) -> None
  ```

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_poller.py`:

```python
"""FleetPoller: lazy start, grace-period stop, and a REST read whose
correctness never depends on the poller being up (spec D6)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from sdlc.dashboard.fleet import FleetPoller, FleetSnapshot

AT = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)


class _Clock:
    def __init__(self):
        self.t = AT

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += timedelta(seconds=seconds)


def _poller(clock=None, **kw):
    clock = clock or _Clock()
    calls = []

    async def fake_fetch(client, *, now, closed_limit=20):
        calls.append(now)
        return FleetSnapshot(at=now, total_open_runs=len(calls))

    p = FleetPoller(
        lambda: None,
        clock=clock,
        fetch=fake_fetch,
        interval=kw.pop("interval", 0.01),
        grace_s=kw.pop("grace_s", 0.05),
    )
    p.calls = calls
    return p


@pytest.mark.asyncio
async def test_snapshot_fans_out_inline_when_there_is_no_cached_snapshot():
    p = _poller()
    snap = await p.snapshot()
    assert snap.total_open_runs == 1
    assert len(p.calls) == 1


@pytest.mark.asyncio
async def test_snapshot_reuses_a_fresh_cached_snapshot():
    clock = _Clock()
    p = _poller(clock)
    await p.snapshot()
    await p.snapshot()
    assert len(p.calls) == 1


@pytest.mark.asyncio
async def test_snapshot_refetches_a_stale_snapshot():
    """Older than 2 x interval is stale, so REST correctness never depends
    on the poller running."""
    clock = _Clock()
    p = _poller(clock, interval=1.0)
    await p.snapshot()
    clock.advance(3.0)
    await p.snapshot()
    assert len(p.calls) == 2


@pytest.mark.asyncio
async def test_poller_is_not_running_before_anyone_subscribes():
    p = _poller()
    assert p.running is False


@pytest.mark.asyncio
async def test_subscribing_starts_the_poller_and_delivers_snapshots():
    p = _poller()
    async with p.subscribe() as q:
        assert p.running is True
        snap = await asyncio.wait_for(q.get(), timeout=2)
        assert isinstance(snap, FleetSnapshot)


@pytest.mark.asyncio
async def test_poller_stops_after_the_grace_period_once_all_unsubscribe():
    p = _poller(grace_s=0.02)
    async with p.subscribe() as q:
        await asyncio.wait_for(q.get(), timeout=2)
    for _ in range(100):
        if not p.running:
            break
        await asyncio.sleep(0.01)
    assert p.running is False


@pytest.mark.asyncio
async def test_a_second_subscriber_keeps_the_poller_alive():
    p = _poller(grace_s=0.02)
    async with p.subscribe() as q1:
        await asyncio.wait_for(q1.get(), timeout=2)
        async with p.subscribe() as q2:
            await asyncio.wait_for(q2.get(), timeout=2)
        await asyncio.sleep(0.05)
        assert p.running is True
    await p.aclose()


@pytest.mark.asyncio
async def test_aclose_stops_the_poller_immediately():
    p = _poller(grace_s=10.0)
    async with p.subscribe() as q:
        await asyncio.wait_for(q.get(), timeout=2)
    await p.aclose()
    assert p.running is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_poller.py -v`
Expected: FAIL — `ImportError: cannot import name 'FleetPoller'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/dashboard/fleet.py`:

```python
import contextlib
from datetime import timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FleetPoller:
    """One shared fan-out multiplexed to every subscriber (spec D5/D6).

    Why shared: a per-request fan-out costs N_clients x N_runs because each
    browser tab polls independently. One poller costs N_runs regardless of
    how many tabs are open.

    Why lazy: an operator tool left open overnight should stop querying
    Temporal when nobody is watching. It starts on the first subscriber or
    a cold read and stops grace_s after the last unsubscribe.

    Why snapshot() can still fan out inline: REST correctness must never
    depend on the poller being up.

    `clock` and `fetch` are injectable for tests only; production uses the
    module defaults.
    """

    def __init__(
        self,
        client_factory,
        *,
        interval: float = 2.0,
        grace_s: float = 30.0,
        clock=None,
        fetch=None,
    ) -> None:
        self._client_factory = client_factory
        self._interval = interval
        self._grace_s = grace_s
        self._clock = clock or _utcnow
        self._fetch = fetch or fetch_fleet
        self._client = None
        self._snapshot: FleetSnapshot | None = None
        self._subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._stop_handle: asyncio.TimerHandle | None = None
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _client_or_connect(self):
        if self._client is None:
            self._client = self._client_factory()
            if asyncio.iscoroutine(self._client):
                self._client = await self._client
        return self._client

    async def _fan_out(self) -> FleetSnapshot:
        client = await self._client_or_connect()
        snap = await self._fetch(client, now=self._clock())
        self._snapshot = snap
        return snap

    def _fresh(self) -> bool:
        if self._snapshot is None:
            return False
        age = (self._clock() - self._snapshot.at).total_seconds()
        return age < 2 * self._interval

    async def snapshot(self) -> FleetSnapshot:
        """The cached snapshot when fresh, otherwise an inline fan-out."""
        async with self._lock:
            if self._fresh():
                return self._snapshot
            return await self._fan_out()

    async def _loop(self) -> None:
        while True:
            try:
                async with self._lock:
                    snap = await self._fan_out()
                for q in list(self._subscribers):
                    q.put_nowait(snap)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 -- a poll failure must
                pass  # never kill the loop; next tick retries
            await asyncio.sleep(self._interval)

    def _cancel_pending_stop(self) -> None:
        if self._stop_handle is not None:
            self._stop_handle.cancel()
            self._stop_handle = None

    def _schedule_stop(self) -> None:
        loop = asyncio.get_running_loop()
        self._cancel_pending_stop()
        self._stop_handle = loop.call_later(
            self._grace_s, lambda: asyncio.ensure_future(self._stop_if_idle())
        )

    async def _stop_if_idle(self) -> None:
        if not self._subscribers:
            await self.aclose()

    @contextlib.asynccontextmanager
    async def subscribe(self):
        """Yields a queue receiving every new snapshot while subscribed."""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        self._cancel_pending_stop()
        if not self.running:
            self._task = asyncio.create_task(self._loop())
        try:
            yield q
        finally:
            self._subscribers.discard(q)
            if not self._subscribers:
                self._schedule_stop()

    async def aclose(self) -> None:
        """Stop the poll loop now. Idempotent."""
        self._cancel_pending_stop()
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
```

Move the `import asyncio` and `from datetime import datetime` lines to the top of the file if the appended code duplicates them.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_poller.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/dashboard/fleet.py tests/test_dashboard_poller.py
git commit -m "feat(dashboard): add the lazy shared fleet poller (E-10)"
```

---

### Task 8: the REST routes

Implements spec §6's three routes plus the two reads.

**Files:**
- Create: `src/sdlc/dashboard/api.py`
- Test: `tests/test_dashboard_api.py` (create)

**Interfaces:**
- Consumes: `FleetPoller`, `FleetSnapshot` (Tasks 6–7), `DashboardChannel` (Task 5), `resolve_key` (Task 4), `submit`, `SubmitResult` (`channels/transport.py`), `NoMatch` (`transport.py:50`).
- Produces:
  ```python
  class AnswerBody(BaseModel):  key: str; text: str
  class DecideBody(BaseModel):  key: str; outcome: GateOutcome; text: str = ""
  class StartBody(BaseModel):   title: str; description: str = ""
                                mode: ProjectMode; repo: str | None = None
  def create_router(poller: FleetPoller,
                    starter: Callable | None = None) -> APIRouter
  ```
  Routes: `GET /runs`, `GET /runs/{run_id}`, `GET /inbox`, `GET /events`,
  `POST /runs`, `POST /runs/{run_id}/answer`, `POST /runs/{run_id}/decide`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_api.py`:

```python
"""Dashboard route shapes, error codes, and identity handling."""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sdlc.channels.transport import SubmitResult
from sdlc.dashboard.api import create_router
from sdlc.dashboard.fleet import FleetSnapshot
from sdlc.models import RunState
from sdlc.pending import ClarifyPending, StageGatePending

AT = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
ARCH = StageGatePending(key="architecture#1", gate="architecture", round=1, spec_summary="s")
Q1 = ClarifyPending(key="Q1", question="q", why_it_matters="w")
UNCONFIRMED = StageGatePending(key="unconfirmed#1", gate="unconfirmed", round=1, spec_summary="s")


class _FakePoller:
    def __init__(self, snap):
        self._snap = snap

    async def snapshot(self):
        return self._snap


@pytest.fixture
def snap():
    return FleetSnapshot(
        at=AT,
        total_open_runs=1,
        runs=[
            RunState(
                run_id="feature-add-sso",
                title="Add SSO",
                mode="brownfield",
                status="awaiting:architecture",
                started_at=AT,
            )
        ],
    )


@pytest.fixture
def submitted():
    return []


@pytest.fixture
def client(snap, submitted, monkeypatch):
    pendings = {ARCH.key: ARCH, Q1.key: Q1, UNCONFIRMED.key: UNCONFIRMED}

    async def fake_resolve_key(handle, key):
        if key not in pendings:
            from sdlc.channels.transport import NoMatch

            raise NoMatch(f"no pending item with key '{key}' on this run")
        return pendings[key]

    async def fake_submit(handle, pending, reply, channel=None):
        call = channel.translate(pending, reply)
        submitted.append(call)
        if pending.key == "unconfirmed#1":
            return SubmitResult(confirmed=False, message="still pending")
        return SubmitResult(confirmed=True, message="approved")

    import sdlc.dashboard.api as mod

    monkeypatch.setattr(mod, "resolve_key", fake_resolve_key)
    monkeypatch.setattr(mod, "submit", fake_submit)
    monkeypatch.setattr(mod, "_handle", lambda poller, run_id: object())

    app = FastAPI()
    app.include_router(create_router(_FakePoller(snap)))
    return TestClient(app)


def test_get_runs_returns_the_snapshot_runs(client):
    r = client.get("/runs")
    assert r.status_code == 200
    assert [x["run_id"] for x in r.json()] == ["feature-add-sso"]


def test_get_run_returns_one_run(client):
    r = client.get("/runs/feature-add-sso")
    assert r.status_code == 200
    assert r.json()["title"] == "Add SSO"


def test_get_run_404s_on_an_unknown_id(client):
    assert client.get("/runs/nope").status_code == 404


def test_get_inbox_returns_the_snapshot_inbox_and_errors(client):
    r = client.get("/inbox")
    assert r.status_code == 200
    assert r.json()["total_open_runs"] == 1


def test_decide_stamps_the_actor_onto_reviewer(client, submitted):
    r = client.post(
        "/runs/feature-add-sso/decide",
        json={"key": "architecture#1", "outcome": "approve", "text": "ok"},
        headers={"X-Actor": "human:mika"},
    )
    assert r.status_code == 200
    assert submitted[0].decision.reviewer == "human:mika"


def test_decide_leaves_decided_by_as_human(client, submitted):
    client.post(
        "/runs/feature-add-sso/decide",
        json={"key": "architecture#1", "outcome": "approve"},
        headers={"X-Actor": "human:mika"},
    )
    assert submitted[0].decision.decided_by == "human"


def test_decide_defaults_the_actor_when_no_header_is_sent(client, submitted):
    client.post(
        "/runs/feature-add-sso/decide", json={"key": "architecture#1", "outcome": "approve"}
    )
    assert submitted[0].decision.reviewer == "human:unknown"


def test_decide_404s_when_the_key_is_not_pending(client):
    r = client.post("/runs/feature-add-sso/decide", json={"key": "merge#9", "outcome": "approve"})
    assert r.status_code == 404


def test_decide_returns_the_submit_result_verbatim(client):
    r = client.post(
        "/runs/feature-add-sso/decide", json={"key": "architecture#1", "outcome": "approve"}
    )
    assert r.json() == {"confirmed": True, "message": "approved"}


def test_answer_routes_a_clarify_key_to_the_answer_question_signal(client, submitted):
    r = client.post("/runs/feature-add-sso/answer", json={"key": "Q1", "text": "OIDC"})
    assert r.status_code == 200
    assert submitted[0].signal == "answer_question"
    assert submitted[0].question_id == "Q1"
    assert submitted[0].answer == "OIDC"


def test_an_unconfirmed_submit_is_reported_as_200_not_an_error(client):
    """confirmed=False is informational: the dominant cause is another
    surface winning the race, which is FR-302 working as designed
    (transport._message). It must never surface as an HTTP error."""
    r = client.post(
        "/runs/feature-add-sso/decide", json={"key": "unconfirmed#1", "outcome": "approve"}
    )
    assert r.status_code == 200
    assert r.json() == {"confirmed": False, "message": "still pending"}
```

Then add the start-run tests to the same file:

```python
class _AlreadyStarted(Exception):
    pass


@pytest.fixture
def start_client(snap):
    started = []

    async def starter(idea, cfg, wf_id):
        # The route maps any "already started" failure to 409; this stands in
        # for temporalio's WorkflowAlreadyStartedError without importing it.
        if wf_id == "feature-taken":
            raise _AlreadyStarted("Workflow already started")
        started.append((idea, wf_id))
        return wf_id

    app = FastAPI()
    app.include_router(create_router(_FakePoller(snap), starter=starter))
    c = TestClient(app)
    c.started = started
    return c


def test_start_run_builds_the_workflow_id_from_the_title(start_client):
    r = start_client.post(
        "/runs",
        json={
            "title": "Add SSO to portal",
            "description": "d",
            "mode": "brownfield",
            "repo": "git@example:acme/portal",
        },
    )
    assert r.status_code == 200
    assert r.json()["run_id"] == "feature-add-sso-to-portal"
    idea, wf_id = start_client.started[0]
    assert idea.title == "Add SSO to portal"
    assert idea.repo_url == "git@example:acme/portal"


def test_start_run_409s_on_a_duplicate_id(start_client):
    r = start_client.post(
        "/runs", json={"title": "taken", "description": "d", "mode": "greenfield"}
    )
    assert r.status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.dashboard.api'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/dashboard/api.py`:

```python
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
from typing import Callable

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..channels.contract import Reply
from ..channels.transport import NoMatch, resolve_key, submit
from ..cli import slug
from ..models import GateOutcome, IdeaBrief, PipelineConfig, ProjectMode
from ..worker import TASK_QUEUE
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


def _handle(poller: FleetPoller, run_id: str):
    """The workflow handle for a run. Indirected so tests can stub it."""
    client = poller._client
    if client is None:
        raise HTTPException(503, "no Temporal client connected")
    return client.get_workflow_handle(run_id)


async def _default_starter(idea: IdeaBrief, cfg: PipelineConfig, wf_id: str) -> str:
    raise HTTPException(503, "no starter configured")


def create_router(poller: FleetPoller, starter: Callable | None = None) -> APIRouter:
    router = APIRouter()
    start_run = starter or _default_starter

    async def _reply(run_id: str, key: str, reply: Reply, actor: str):
        handle = _handle(poller, run_id)
        try:
            pending = await resolve_key(handle, key)
        except NoMatch as e:
            raise HTTPException(404, e.message) from e
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
            async with poller.subscribe() as q:
                while True:
                    try:
                        snap = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_S)
                    except asyncio.TimeoutError:
                        # Keeps idle connections alive through proxies and
                        # makes a dead poller detectable.
                        yield ": heartbeat\n\n"
                        continue
                    body = snap.model_dump_json()
                    payload = json.loads(body)
                    payload.pop("at", None)
                    fingerprint = json.dumps(payload, sort_keys=True)
                    if fingerprint == last:
                        continue  # nothing changed but the clock
                    last = fingerprint
                    yield f"data: {body}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @router.post("/runs/{run_id}/answer")
    async def answer(
        run_id: str,
        body: AnswerBody,
        x_actor: str = Header(default="human:unknown", alias="X-Actor"),
    ):
        return await _reply(run_id, body.key, Reply(text=body.text), x_actor)

    @router.post("/runs/{run_id}/decide")
    async def decide(
        run_id: str,
        body: DecideBody,
        x_actor: str = Header(default="human:unknown", alias="X-Actor"),
    ):
        return await _reply(
            run_id, body.key, Reply(outcome=body.outcome, text=body.text or None), x_actor
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_api.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/dashboard/api.py tests/test_dashboard_api.py
git commit -m "feat(dashboard): add REST routes over the fleet snapshot (E-10)"
```

---

### Task 9: the SSE stream

Implements spec §5.2's third bullet. Task 8 wrote the endpoint; this proves its three behaviors.

**Files:**
- Test: `tests/test_dashboard_sse.py` (create)
- Modify: `src/sdlc/dashboard/api.py` only if a test fails.

**Interfaces:**
- Consumes: `create_router` (Task 8), `FleetPoller` (Task 7).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_sse.py`:

```python
"""SSE: emit on change, suppress identical snapshots, heartbeat when idle."""

import contextlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sdlc.dashboard.api import create_router
from sdlc.dashboard.fleet import FleetSnapshot

AT = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)


class _ScriptedPoller:
    """Yields a fixed list of snapshots to one subscriber, then idles."""

    def __init__(self, snaps):
        self._snaps = list(snaps)

    async def snapshot(self):
        return self._snaps[0]

    @contextlib.asynccontextmanager
    async def subscribe(self):
        import asyncio

        q = asyncio.Queue()
        for s in self._snaps:
            q.put_nowait(s)
        yield q


def _client(snaps):
    app = FastAPI()
    app.include_router(create_router(_ScriptedPoller(snaps)))
    return TestClient(app)


def _events(client, want: int):
    """Read `want` data: frames off the stream, then stop."""
    out = []
    with client.stream("GET", "/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: "):
                out.append(line[len("data: ") :])
                if len(out) >= want:
                    break
    return out


def test_stream_emits_a_snapshot_as_a_data_frame():
    snap = FleetSnapshot(at=AT, total_open_runs=1)
    [frame] = _events(_client([snap]), 1)
    assert FleetSnapshot.model_validate_json(frame).total_open_runs == 1


def test_stream_suppresses_a_snapshot_that_differs_only_by_its_clock():
    """The poller re-fans-out every interval; an unchanged fleet must not
    produce a frame just because `at` moved."""
    a = FleetSnapshot(at=AT, total_open_runs=1)
    same = FleetSnapshot(at=AT + timedelta(seconds=2), total_open_runs=1)
    changed = FleetSnapshot(at=AT + timedelta(seconds=4), total_open_runs=2)
    frames = _events(_client([a, same, changed]), 2)
    assert [FleetSnapshot.model_validate_json(f).total_open_runs for f in frames] == [1, 2]


def test_stream_sends_a_heartbeat_comment_when_idle(monkeypatch):
    import sdlc.dashboard.api as mod

    monkeypatch.setattr(mod, "HEARTBEAT_S", 0.01)
    client = _client([])
    with client.stream("GET", "/events") as r:
        for line in r.iter_lines():
            if line.startswith(":"):
                assert "heartbeat" in line
                return
    pytest.fail("no heartbeat frame")
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_dashboard_sse.py -v`
Expected: PASS if Task 8's endpoint is correct. If `test_stream_sends_a_heartbeat_comment_when_idle` fails because `HEARTBEAT_S` was captured at import, change the endpoint to read the module global at call time:

```python
snap = await asyncio.wait_for(q.get(), timeout=globals()["HEARTBEAT_S"])
```

- [ ] **Step 3: Re-run until green**

Run: `pytest tests/test_dashboard_sse.py -v`
Expected: PASS (3 passed)

- [ ] **Step 4: Commit**

```bash
git add tests/test_dashboard_sse.py src/sdlc/dashboard/api.py
git commit -m "test(dashboard): pin SSE emit-on-change and heartbeat (E-10)"
```

---

### Task 10: the composed entrypoint

Implements spec D2. Makes `interfaces/dashboard/api/main.py` stop lying.

**Files:**
- Modify: `interfaces/dashboard/api/main.py`
- Test: `tests/test_dashboard_entrypoint.py` (create)

**Interfaces:**
- Consumes: `sdlc.board.api.create_app`, `create_router` (Task 8), `FleetPoller` (Task 7).
- Produces: `interfaces.dashboard.api.main.app` — a `FastAPI` app serving the board's routes at their existing paths and the dashboard's under `/api`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_entrypoint.py`:

```python
"""D2: two routers, one process. The board's existing paths must not move --
any agent client hitting /projects/* keeps working."""

from interfaces.dashboard.api.main import app


def _paths():
    return {r.path for r in app.routes}


def test_board_routes_keep_their_existing_paths():
    assert "/projects" in _paths()
    assert "/projects/{project}/tasks" in _paths()


def test_dashboard_routes_are_served_under_api():
    p = _paths()
    assert "/api/runs" in p
    assert "/api/inbox" in p
    assert "/api/events" in p


def test_dashboard_write_routes_are_present():
    p = _paths()
    assert "/api/runs/{run_id}/answer" in p
    assert "/api/runs/{run_id}/decide" in p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_entrypoint.py -v`
Expected: FAIL — `/api/runs` not in paths

- [ ] **Step 3: Write minimal implementation**

Replace `interfaces/dashboard/api/main.py` entirely:

```python
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
        os.environ.get("TEMPORAL_HOST", "localhost:7233"), data_converter=pydantic_data_converter
    )


poller = FleetPoller(_connect)


async def _start(idea: IdeaBrief, cfg: PipelineConfig, wf_id: str) -> str:
    client = await poller._client_or_connect()
    handle = await client.start_workflow(
        FeatureWorkflow.run, args=[idea, cfg, None], id=wf_id, task_queue=TASK_QUEUE
    )
    return handle.id


app.include_router(create_router(poller, starter=_start), prefix="/api")


@app.on_event("shutdown")
async def _shutdown() -> None:
    await poller.aclose()


__all__ = ["app"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_entrypoint.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the whole fast suite**

Run: `pytest`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add interfaces/dashboard/api/main.py tests/test_dashboard_entrypoint.py
git commit -m "feat(dashboard): compose board and dashboard routers in one app (E-10)"
```

---

### Task 11: the temporal e2e

Implements spec §8's fourth bullet — the one part no fake can prove.

**Files:**
- Test: `tests/test_dashboard_e2e.py` (create)

**Interfaces:**
- Consumes: `run_state()` (Task 3), `fetch_fleet` (Task 6).
- Produces: nothing.

- [ ] **Step 1: Read the existing e2e pattern**

Read `tests/test_assessment_workflow_e2e.py` to copy this repo's `WorkflowEnvironment.start_time_skipping` + worker-registration fixture shape. Do not invent a new harness.

- [ ] **Step 2: Write the failing test**

Create `tests/test_dashboard_e2e.py`, following the fixture shape you just read:

```python
"""E-10 e2e: run_state() answers against a real workflow, and fetch_fleet
aggregates it through a real client. The one part no fake can prove.

Deliberately narrow. run() stashes _idea and _started_at before its first
activity, so the query is answerable from the first completed workflow task
-- no activity fakes are needed and none are registered. Driving a full
pipeline is test_e2e_greenfield.py's job, not this test's.

Marked temporal: each such test spawns its own dev-server subprocess
(pyproject's addopts excludes them from the default run)."""

from datetime import datetime, timezone

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.dashboard.fleet import fetch_fleet
from sdlc.models import IdeaBrief, PipelineConfig, ProjectMode, RunState
from sdlc.workflows.feature import FeatureWorkflow

pytestmark = pytest.mark.temporal


@pytest.mark.asyncio
async def test_run_state_answers_on_a_live_run():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue="dash-e2e", workflows=[FeatureWorkflow], activities=[]
        ):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run,
                args=[
                    IdeaBrief(title="Add SSO", description="d", mode=ProjectMode.GREENFIELD),
                    PipelineConfig(),
                    None,
                ],
                id="feature-add-sso",
                task_queue="dash-e2e",
            )
            try:
                state = await handle.query("run_state", result_type=RunState)
                assert state is not None
                assert state.title == "Add SSO"
                assert state.run_id == "feature-add-sso"
                # Nothing has been priced yet, and None must not become 0.0.
                assert state.cost_usd_total is None

                snap = await fetch_fleet(env.client, now=datetime.now(timezone.utc))
                assert "feature-add-sso" in {r.run_id for r in snap.runs}
            finally:
                await handle.cancel()
```

- [ ] **Step 3: Run it**

Run: `pytest tests/test_dashboard_e2e.py -m temporal -v`
Expected: PASS (1 passed)

If the query times out, the cause is `run()` reaching an activity before stashing `_idea` — check that Task 3 Step 4 placed the two assignments immediately after the `model_validate` coercions, ahead of any `execute_activity` call.

- [ ] **Step 4: Commit**

```bash
git add tests/test_dashboard_e2e.py
git commit -m "test(dashboard): e2e run_state() over a real workflow (E-10)"
```

---

### Task 12: the frontend provider

Implements spec §7.

**Files:**
- Modify: `interfaces/dashboard/frontend/src/api/types.ts`, `src/api/http.ts`, `src/api/mock/index.ts`, `vite.config.ts`
- Create: `scripts/dump_dashboard_fixtures.py`, `src/api/http.test.ts`

**Interfaces:**
- Consumes: the JSON shapes of `RunState`, `FleetSnapshot`, `PendingDecision`.
- Produces: `createHttpApi(baseUrl?: string): DashboardApi`; `DashboardApi.subscribe(cb: (s: FleetState) => void): () => void`.

- [ ] **Step 1: Write the fixture dumper**

Create `scripts/dump_dashboard_fixtures.py`:

```python
"""Dump JSON fixtures from the Pydantic models so the TS mapper is tested
against real shapes (spec 8, contract drift guard).

    python scripts/dump_dashboard_fixtures.py

D3 chose hand-written adaptation over codegen, so nothing structurally
prevents http.ts drifting from the models. These fixtures make drift break
a test instead of a page.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sdlc.dashboard.fleet import FleetSnapshot
from sdlc.gate import CheckClass, CheckResult
from sdlc.models import GateDecision, GateOutcome, RoleUsage, RunState, RunSummary
from sdlc.pending import ClarifyPending, MergeGatePending, StageGatePending, TaskEscalationPending
from sdlc.channels.inbox import RunInbox

OUT = Path("interfaces/dashboard/frontend/src/api/__fixtures__")
AT = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)


def main() -> None:
    snap = FleetSnapshot(
        at=AT + timedelta(hours=2),
        total_open_runs=2,
        runs=[
            RunState(
                run_id="feature-add-sso",
                title="Add SSO to customer portal",
                repo_url="git@github.com:acme/portal",
                mode="brownfield",
                status="awaiting:architecture",
                current_stage="architecture",
                started_at=AT,
                decisions=[
                    GateDecision(
                        gate="clarify",
                        round=1,
                        outcome=GateOutcome.APPROVE,
                        decided_by="human",
                        reviewer="human:mika",
                        comments="all suggestions accepted",
                        decided_at=AT,
                    )
                ],
                roles=[RoleUsage(role="architect", model="m", calls=2, cost_usd=3.12)],
                cost_usd_total=3.12,
                budget_usd=40.0,
            ),
            RunState(
                run_id="feature-unpriced",
                title="Unpriced run",
                mode="greenfield",
                status="running",
                current_stage="code",
                started_at=AT,
                cost_usd_total=None,
                budget_usd=None,
            ),
        ],
        closed=[
            RunSummary(
                run_id="feature-dark-mode",
                mode="brownfield",
                outcome="deployed:ok",
                terminal_stage="retro",
                started_at=AT,
                ended_at=AT + timedelta(hours=3),
                duration_s=10800.0,
                title="Dark mode for settings pages",
                repo_url="git@github.com:acme/portal",
                cost_usd_total=7.88,
            )
        ],
        inbox=[
            RunInbox(
                run_id="feature-add-sso",
                pending=[
                    ClarifyPending(
                        key="Q1",
                        question="Which identity protocol?",
                        why_it_matters="no auth abstraction exists",
                        suggested_answer="OIDC",
                        opened_at=AT,
                    ),
                    StageGatePending(
                        key="architecture#1",
                        gate="architecture",
                        round=1,
                        spec_summary="Adds MeteringService",
                        opened_at=AT,
                    ),
                    MergeGatePending(
                        key="merge#1",
                        gate="merge",
                        round=1,
                        verdict="MergeVerdict 0.91 - approve",
                        opened_at=AT,
                        checks=[
                            CheckResult(
                                name="lint",
                                passed=True,
                                classification=CheckClass.ABSOLUTE,
                                detail="clean",
                            ),
                            CheckResult(
                                name="diff coverage",
                                passed=False,
                                classification=CheckClass.ADVISORY,
                                detail="0.68 - target 0.80",
                            ),
                        ],
                    ),
                    TaskEscalationPending(
                        key="task:T07#1",
                        gate="task:T07",
                        round=1,
                        task_id="T07",
                        attempts=3,
                        analysis="test_retry_budget flakes",
                        opened_at=AT,
                    ),
                ],
            )
        ],
    )

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fleet-snapshot.json").write_text(
        json.dumps(json.loads(snap.model_dump_json()), indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUT / 'fleet-snapshot.json'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `python scripts/dump_dashboard_fixtures.py`
Expected: `wrote interfaces/dashboard/frontend/src/api/__fixtures__/fleet-snapshot.json`

- [ ] **Step 3: Update `types.ts`**

In `interfaces/dashboard/frontend/src/api/types.ts`:

Delete `stageNote: string` and `skipCtx: boolean` from `Run`; delete `confidence: string` from `ClarifyItem`. Change `cost: number` to `cost: number | null` and `budget: number` to `budget: number | null`. Add `description: string` to `StartRunInput`. Then add the subscription to `DashboardApi`:

```typescript
export interface FleetState {
  runs: Run[]
  inbox: InboxItem[]
  errors: { runId: string; error: string }[]
}

export interface DashboardApi {
  listRuns(): Promise<Run[]>
  getRun(id: string): Promise<Run | undefined>
  listInbox(): Promise<InboxItem[]>
  answerClarify(id: string, answer: string): Promise<void>
  decideGate(id: string, outcome: GateOutcome, comment: string): Promise<void>
  overrideMerge(id: string, approve: boolean, justification: string): Promise<void>
  resolveEscalation(id: string, retry: boolean, guidance: string): Promise<void>
  startRun(input: StartRunInput): Promise<Run>
  subscribe(cb: (s: FleetState) => void): () => void
}
```

- [ ] **Step 4: Write the failing mapper test**

Create `interfaces/dashboard/frontend/src/api/http.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import snapshot from './__fixtures__/fleet-snapshot.json'
import { mapSnapshot } from './http'

const NOW = new Date('2026-08-18T11:00:00Z')

describe('mapSnapshot', () => {
  it('maps a live run onto the view model', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    const sso = runs.find((r) => r.id === 'feature-add-sso')!
    expect(sso.title).toBe('Add SSO to customer portal')
    expect(sso.mode).toBe('brownfield')
    expect(sso.repo).toBe('git@github.com:acme/portal')
    expect(sso.cost).toBe(3.12)
    expect(sso.budget).toBe(40)
  })

  it('maps an awaiting status to blocked', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-add-sso')!.status).toBe('blocked')
  })

  it('maps a running status to running', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-unpriced')!.status).toBe('running')
  })

  it('keeps an unpriced run null rather than zero', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-unpriced')!.cost).toBeNull()
  })

  it('derives stageIdx from current_stage', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    // CANONICAL_STAGES: intake, constitution, context, requirements,
    // research, clarify, architecture -> index 6
    expect(runs.find((r) => r.id === 'feature-add-sso')!.stageIdx).toBe(6)
  })

  it('formats age from started_at', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-add-sso')!.age).toBe('2h 00m')
  })

  it('renders a closed run as done', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    const closed = runs.find((r) => r.id === 'feature-dark-mode')!
    expect(closed.status).toBe('done')
    expect(closed.title).toBe('Dark mode for settings pages')
  })

  it('maps each pending variant to its inbox item type', () => {
    const { inbox } = mapSnapshot(snapshot as never, NOW)
    expect(inbox.map((i) => i.type)).toEqual([
      'clarify', 'gate', 'override', 'escalation',
    ])
  })

  it('carries the merge gate check table onto the override item', () => {
    const { inbox } = mapSnapshot(snapshot as never, NOW)
    const override = inbox.find((i) => i.type === 'override')!
    expect(override.checks).toEqual([
      { name: 'lint', kind: 'ABSOLUTE', ok: true, detail: 'clean' },
      { name: 'diff coverage', kind: 'ADVISORY', ok: false, detail: '0.68 - target 0.80' },
    ])
  })

  it('uses the pending key as the inbox item id', () => {
    const { inbox } = mapSnapshot(snapshot as never, NOW)
    expect(inbox.map((i) => i.id)).toEqual([
      'Q1', 'architecture#1', 'merge#1', 'task:T07#1',
    ])
  })

  it('computes inbox age from opened_at', () => {
    const { inbox } = mapSnapshot(snapshot as never, NOW)
    expect(inbox[0].age).toBe('2h 00m')
  })
})
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `cd interfaces/dashboard/frontend && npm test -- http.test.ts`
Expected: FAIL — `mapSnapshot` is not exported from `./http`

- [ ] **Step 6: Write the provider**

Replace `interfaces/dashboard/frontend/src/api/http.ts`:

```typescript
import type {
  ClarifyItem, DashboardApi, Decision, EscalationItem, FleetState, GateItem,
  GateOutcome, InboxItem, OverrideItem, Run, StartRunInput, Status,
} from './types'

// Mirrors sdlc/benchmarks/heatmap.py CANONICAL_STAGES. StageDots maps active
// stages back onto its fixed strip, so this list is the join key between the
// dashboard and the benchmark axis.
const CANONICAL_STAGES = [
  'intake', 'constitution', 'context', 'requirements', 'research',
  'clarify', 'architecture', 'planning', 'code', 'review', 'adversary',
  'handoff', 'deep_review', 'analyze', 'qa', 'quality_gate', 'deploy',
  'retro',
]

function age(fromIso: string | null | undefined, now: Date): string {
  if (!fromIso) return ''
  const ms = now.getTime() - new Date(fromIso).getTime()
  const mins = Math.max(0, Math.floor(ms / 60000))
  const d = Math.floor(mins / 1440)
  if (d > 0) return `${d}d ${Math.floor((mins % 1440) / 60)}h`
  const h = Math.floor(mins / 60)
  return `${h}h ${String(mins % 60).padStart(2, '0')}m`
}

function hhmm(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}

function liveStatus(status: string): Status {
  return status.startsWith('awaiting:') ? 'blocked' : 'running'
}

function closedStatus(outcome: string): Status {
  return outcome.startsWith('rejected') || outcome.startsWith('failed')
    ? 'failed'
    : 'done'
}

function blocker(status: string, pendingCount: number): string {
  if (!status.startsWith('awaiting:')) return ''
  const gate = status.slice('awaiting:'.length)
  return pendingCount > 1 ? `${gate} gate — ${pendingCount} items` : `${gate} gate`
}

function decisions(raw: any[]): Decision[] {
  return (raw ?? []).map((d) => ({
    ts: hhmm(d.decided_at),
    gate: `${d.gate} r${d.round}`,
    outcome: d.outcome as GateOutcome,
    comment: d.comments ?? '',
    decider: d.reviewer ?? d.decided_by,
  }))
}

function mapRun(s: any, pendingCount: number, now: Date): Run {
  return {
    id: s.run_id,
    title: s.title,
    mode: s.mode,
    repo: s.repo_url ?? '',
    stageIdx: Math.max(0, CANONICAL_STAGES.indexOf(s.current_stage ?? '')),
    status: liveStatus(s.status),
    blocker: blocker(s.status, pendingCount),
    cost: s.cost_usd_total,
    budget: s.budget_usd,
    age: age(s.started_at, now),
    decisions: decisions(s.decisions),
  }
}

function mapClosed(s: any, now: Date): Run {
  return {
    id: s.run_id,
    title: s.title,
    mode: s.mode,
    repo: s.repo_url ?? '',
    stageIdx: Math.max(0, CANONICAL_STAGES.indexOf(s.terminal_stage ?? '')),
    status: closedStatus(s.outcome),
    blocker: '',
    cost: s.cost_usd_total,
    budget: s.budget_usd,
    age: age(s.started_at, now),
    decisions: [],
  }
}

function mapPending(runId: string, p: any, now: Date): InboxItem {
  const base = { id: p.key, runId, round: p.round ?? 1, age: age(p.opened_at, now) }
  if (p.kind === 'clarify') {
    return {
      ...base, type: 'clarify', title: p.question, body: p.why_it_matters,
      suggestion: p.suggested_answer ?? '',
    } as ClarifyItem
  }
  if (p.kind === 'merge_gate') {
    return {
      ...base, type: 'override', gate: 'merge',
      title: `Merge gate — round ${p.round}`,
      body: 'Merging requires an audited human override (FR-106).',
      verdict: p.verdict ?? '',
      checks: (p.checks ?? []).map((c: any) => ({
        // CheckClass is lowercase on the wire ("absolute"); CheckRow.kind is
        // uppercase. Normalize here, not by widening the TS union.
        name: c.name, ok: c.passed, detail: c.detail,
        kind: String(c.classification).toUpperCase(),
      })),
    } as OverrideItem
  }
  if (p.kind === 'task_escalation') {
    return {
      ...base, type: 'escalation',
      title: `${p.task_id} — resolver exhausted (${p.attempts})`,
      body: `Task ${p.task_id} could not be closed by the fix loop.`,
      analysis: p.analysis ?? '',
    } as EscalationItem
  }
  return {
    ...base, type: 'gate', gate: p.gate,
    title: `${p.gate} (round ${p.round})`, body: p.spec_summary ?? '',
  } as GateItem
}

export function mapSnapshot(snap: any, now: Date = new Date()): FleetState {
  const pendingByRun = new Map<string, any[]>()
  for (const r of snap.inbox ?? []) pendingByRun.set(r.run_id, r.pending)

  const runs = [
    ...(snap.runs ?? []).map((s: any) =>
      mapRun(s, (pendingByRun.get(s.run_id) ?? []).length, now)),
    ...(snap.closed ?? []).map((s: any) => mapClosed(s, now)),
  ]
  const inbox: InboxItem[] = []
  for (const r of snap.inbox ?? []) {
    for (const p of r.pending) inbox.push(mapPending(r.run_id, p, now))
  }
  const errors = (snap.errors ?? []).map((e: any) => ({
    runId: e.run_id, error: e.error,
  }))
  return { runs, inbox, errors }
}

export function createHttpApi(baseUrl = '/api'): DashboardApi {
  const json = async (path: string, init?: RequestInit) => {
    const r = await fetch(`${baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
    if (!r.ok) throw new Error(`${init?.method ?? 'GET'} ${path}: ${r.status}`)
    return r.status === 204 ? null : r.json()
  }

  const snapshot = async (): Promise<FleetState> =>
    mapSnapshot(await json('/inbox'))

  const find = async (id: string) =>
    (await snapshot()).inbox.find((i) => i.id === id)

  const decide = async (id: string, outcome: GateOutcome, text: string) => {
    const it = await find(id)
    if (!it) return
    await json(`/runs/${encodeURIComponent(it.runId)}/decide`, {
      method: 'POST', body: JSON.stringify({ key: id, outcome, text }),
    })
  }

  return {
    async listRuns() { return (await snapshot()).runs },
    async getRun(id) { return (await snapshot()).runs.find((r) => r.id === id) },
    async listInbox() { return (await snapshot()).inbox },

    async answerClarify(id, answer) {
      const it = await find(id)
      if (!it) return
      await json(`/runs/${encodeURIComponent(it.runId)}/answer`, {
        method: 'POST', body: JSON.stringify({ key: id, text: answer }),
      })
    },
    decideGate: (id, outcome, comment) => decide(id, outcome, comment),
    overrideMerge: (id, approve, justification) =>
      decide(id, approve ? 'approve' : 'revise', justification),
    resolveEscalation: (id, retry, guidance) =>
      decide(id, retry ? 'approve' : 'reject', guidance),

    async startRun(input: StartRunInput) {
      const { run_id } = await json('/runs', {
        method: 'POST',
        body: JSON.stringify({
          title: input.title, description: input.description,
          mode: input.mode, repo: input.repo,
        }),
      })
      const run = (await snapshot()).runs.find((r) => r.id === run_id)
      if (!run) throw new Error(`started ${run_id} but it is not in the fleet`)
      return run
    },

    subscribe(cb) {
      const es = new EventSource(`${baseUrl}/events`)
      es.onmessage = (e) => cb(mapSnapshot(JSON.parse(e.data)))
      return () => es.close()
    },
  }
}
```

- [ ] **Step 7: Run the mapper test**

Run: `cd interfaces/dashboard/frontend && npm test -- http.test.ts`
Expected: PASS (11 passed)

- [ ] **Step 8: Add `subscribe` to the mock**

In `interfaces/dashboard/frontend/src/api/mock/index.ts`, add to the returned `api` object (before `dispose`):

```typescript
    subscribe(cb: (s: FleetState) => void) {
      // The mock already faked liveness with this timer; a push-shaped
      // contract is simply more honest about what it was doing.
      const t = setInterval(() => {
        runs = tickCosts(runs)
        cb({ runs: clone(runs), inbox: clone(inbox), errors: [] })
      }, 4000)
      return () => clearInterval(t)
    },
```

Add `FleetState` to the file's type import list.

- [ ] **Step 9: Add the dev proxy**

In `interfaces/dashboard/frontend/vite.config.ts`, add to the `defineConfig` object:

```typescript
  server: {
    proxy: {
      // One origin (D2): the backend serves board + dashboard on 8500.
      '/api': { target: 'http://127.0.0.1:8500', changeOrigin: true },
    },
  },
```

- [ ] **Step 10: Typecheck and run the whole frontend suite**

Run: `cd interfaces/dashboard/frontend && npm run typecheck && npm test`
Expected: PASS. Fix any component referencing the three deleted fields (`stageNote`, `skipCtx`, `confidence`) by removing that usage — do not reintroduce the fields.

- [ ] **Step 11: Commit**

```bash
git add interfaces/dashboard/frontend scripts/dump_dashboard_fixtures.py
git commit -m "feat(dashboard): wire the http provider to the real backend (E-10)"
```

---

### Task 13: roadmap and architecture deltas

Implements spec §9. These are part of the change, not follow-ups.

**Files:**
- Modify: `ROADMAP.md`, `ARCHITECTURE.md`, and the spec's Status line.

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Correct P2's stale brownfield claim**

In `ROADMAP.md:95`, replace the P2 sub-line with:

```markdown
  Cross-harness review ✅, fix loops ✅, notifications ✅ (E-9), and brownfield ✅ (E-84, 2026-08-15; `CapabilityMap` via E-47a/b/c) all landed. The dashboard backend landed 2026-08-18 (**E-10**, §9.2) — `interfaces/dashboard/api/main.py` now composes the board and dashboard routers, and the frontend's `http` provider serves live Temporal state. **Every part is built; the exit criterion — *first brownfield feature merged via PR* — is a demonstration that has not been run.**
```

- [ ] **Step 2: Flip E-10 and narrow E-75**

In `ROADMAP.md:445`, replace E-10's line with:

```markdown
- [x] **E-10** FastAPI dashboard backend as a channel adapter, replacing the Vue frontend's mock API (FR-601, US-6, ADR-8). *Landed 2026-08-18.* `run_state()` — one query over state the run already held — plus `sdlc/dashboard/{fleet,api,channel}.py`: a lazy shared poller fanning out `run_state()` + `pending_decisions()` across open runs and `run_summary()` across the 20 most recent closed ones, served as REST reads plus an SSE stream. Three write routes, not five: `pending.py`'s four variants already collapse to two FR-302 signals. Spec `docs/superpowers/specs/2026-08-18-dashboard-backend-design.md`.
```

In `ROADMAP.md:1251`, replace E-75's first sentence with:

```markdown
- [ ] **E-75 — graph queries on the dashboard backend** → FR-1204. **Superseded in part 2026-08-18:** E-10 built the backend, so this narrows to adding `graph_state()` and `graph()` beside the existing queries once `GraphWorkflow` exists. The "dashboard backend remains" half of P2 is closed; what is left here is graph-shaped run state, which needs E-74 first. The only storage is still content-addressed `graphs/<sha>.yaml`.
```

- [ ] **Step 3: Record the ADR-8 exception**

In `ROADMAP.md:331`, replace the ADR-8 line with:

```markdown
- [ ] ⚠️ **ADR-8** Interfaces as stateless shells — true for CLI. **Two documented exceptions, both deliberate:** the agent board API (E-78) serves durable cross-run state no live workflow holds (ADR-21); and the dashboard backend (E-10) holds an in-process fleet poller and subscriber set — not durable state, but not a stateless shell either. The poller exists because a per-request fan-out costs `N_clients × N_runs` while one shared poller costs `N_runs`. ARCHITECTURE.md §8 scopes the claim accordingly.
```

- [ ] **Step 4: Restate OQ-11**

In `ROADMAP.md`, in the OQ-11 entry (around `:1287`), append:

```markdown
  **2026-08-18 (E-10):** a *second* unauthenticated surface now serves, and this
  one can start runs and approve merge gates. Operator identity is the
  self-asserted `X-Actor` header landing on `GateDecision.reviewer` — never on
  `decided_by`, which stays `Literal["human","policy","timeout"]` so
  `ReadinessOverride.approved_by` keeps distinguishing a machine approval from a
  human one. Localhost-bind remains the whole containment.
```

- [ ] **Step 5: Flip FR-601 and US-6**

In `ROADMAP.md:172`, replace FR-601's line:

```markdown
- [x] **FR-601** dashboard fleet/spine/inbox — Vue 3 frontend over a FastAPI backend serving live Temporal state (E-10, 2026-08-18). Closed runs render from `run_summary()` within Temporal's retention window; older history would need a store (OQ-13).
```

In `ROADMAP.md:312`, replace US-6's line:

```markdown
- [x] **US-6** stakeholder one-screen fleet view — `GET /api/runs` plus the `/api/events` SSE stream (E-10).
```

- [ ] **Step 6: Amend ARCHITECTURE.md §8**

Find §8's "stateless shells" claim and extend the existing exception sentence to name both surfaces, matching the ROADMAP wording from Step 3. Keep it to two sentences.

- [ ] **Step 7: Update the spec's Status line**

In `docs/superpowers/specs/2026-08-18-dashboard-backend-design.md`, change the Status row to:

```markdown
| Status | Implemented 2026-08-18 (plan `docs/superpowers/plans/2026-08-18-dashboard-backend.md`) |
```

- [ ] **Step 8: Verify the whole suite**

Run: `pytest`
Expected: PASS

Run: `cd interfaces/dashboard/frontend && npm run typecheck && npm test`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add ROADMAP.md ARCHITECTURE.md docs/superpowers/specs/2026-08-18-dashboard-backend-design.md
git commit -m "docs: record E-10 deltas, ADR-8's second exception, and OQ-11 (E-10)"
```

---

## Verification

After Task 13, before opening a PR:

- [ ] `pytest` — full fast suite green
- [ ] `pytest -m temporal -k dashboard` — the e2e green
- [ ] `cd interfaces/dashboard/frontend && npm run typecheck && npm test` — green
- [ ] Manual smoke: start Temporal + a worker, run `uvicorn interfaces.dashboard.api.main:app --host 127.0.0.1 --port 8500`, then `curl 127.0.0.1:8500/api/runs` and `curl 127.0.0.1:8500/projects` — both answer, confirming D2's composition
- [ ] `curl -N 127.0.0.1:8500/api/events` — emits a snapshot, then heartbeats
