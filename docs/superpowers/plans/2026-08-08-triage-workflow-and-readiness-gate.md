# E-42 — `TriageWorkflow` + Readiness Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire E-41's seven deterministic hygiene signals into a durable
`TriageWorkflow` that pins a commit, computes the readiness verdict, and gates
on it through the existing human-in-the-loop machinery (FR-901, FR-903, ADR-18).

**Architecture:** `FeatureWorkflow`'s gate mechanics are extracted into a
`GateHost` mixin so a second workflow can host a gate without restating FR-302's
first-decision-wins invariant. `TriageWorkflow(GateHost)` resolves a commit,
fans out the signal activities in one `asyncio.gather`, feeds the results to the
untouched `compute_readiness`, and opens a `readiness` gate when the verdict is
not `READY`. No LLM call anywhere in this feature.

**Tech Stack:** Python 3.14, Temporal (`temporalio`), Pydantic v2, pytest.

**Spec:** `docs/superpowers/specs/2026-08-08-triage-workflow-and-readiness-gate-design.md`

## Global Constraints

- `src/sdlc/triage/models.py` must **never** import `models.py`, `activities.py`,
  or `temporalio`. It imports Pydantic and `..measurement` only. A dependency
  there would appear as a reviewable import.
- `src/sdlc/workflows/gates.py` must never import `feature.py` or `triage.py`.
- Workflow-sandbox imports go inside `with workflow.unsafe.imports_passed_through():`.
- `compute_readiness` (`src/sdlc/triage/models.py:96`) is the **only** producer
  of a `Verdict`. No task adds a second path to one.
- No task may synthesize `Measurement.measured(0.0)` on a failure or skip path.
  Unmeasured is `Measurement.not_collected(<reason>)`, always with a reason.
- All operator-facing CLI strings are ASCII — the Windows console cannot print
  non-ASCII.
- Run tests with `python -m pytest ... -p no:warnings` — the suite emits many
  `PydanticAIDeprecationWarning`s that bury the summary line.
- Commit after every task. Do not amend.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/sdlc/models.py` | **Modify** — add `GateSettings` + `PipelineConfig.gate_settings()` |
| `src/sdlc/workflows/gates.py` | **Create** — `GateHost` mixin: gate mechanics + HITL signal/query surface |
| `src/sdlc/workflows/feature.py` | **Modify** — inherit `GateHost`, delete moved members, override 3 hooks, refit 9 call sites |
| `src/sdlc/triage/models.py` | **Modify** — add `ReadinessOverride`, add `RepoTriage.override` |
| `src/sdlc/triage/registry.py` | **Modify** — add `SignalSpec.readiness_keys` |
| `src/sdlc/triage/activities.py` | **Modify** — add `TriagePinInput`, `TriagePin`, `triage_resolve_commit` |
| `src/sdlc/workflows/triage.py` | **Create** — `TriageInput`, `TriageWorkflow` |
| `src/sdlc/worker.py` | **Modify** — register `TriageWorkflow` + `triage_resolve_commit` |
| `src/sdlc/cli.py` | **Modify** — `sdlc triage` and `sdlc triage show` |

---

### Task 1: `GateSettings` — the three fields a gate reads

**Files:**
- Modify: `src/sdlc/models.py` (add class near `GateConfig` at line 53; add method to `PipelineConfig` at line 925)
- Test: `tests/test_gate_settings.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `GateSettings(gates: dict[str, GateConfig], default_gate_policy: GatePolicy, gate_timeout_hours: int)` and `PipelineConfig.gate_settings() -> GateSettings`. Task 2 depends on both.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gate_settings.py`:

```python
"""E-42 D3: the three fields a durable HITL gate reads, extracted so GateHost
does not depend on the feature pipeline's PipelineConfig."""

from __future__ import annotations

from sdlc.models import GateConfig, GatePolicy, GateSettings, PipelineConfig


def test_gate_settings_defaults_are_conservative():
    s = GateSettings()
    assert s.gates == {}
    assert s.default_gate_policy is GatePolicy.HARD
    assert s.gate_timeout_hours == 48


def test_pipeline_config_projects_its_three_gate_fields():
    cfg = PipelineConfig()
    s = cfg.gate_settings()
    assert s.gates == cfg.gates
    assert s.default_gate_policy is cfg.default_gate_policy
    assert s.gate_timeout_hours == cfg.gate_timeout_hours


def test_projection_does_not_alias_the_config_dict():
    """A workflow handed GateSettings must not be able to mutate the config
    it was projected from."""
    cfg = PipelineConfig()
    s = cfg.gate_settings()
    s.gates["invented"] = GateConfig(policy=GatePolicy.OFF)
    assert "invented" not in cfg.gates


def test_unnamed_gate_falls_back_to_default_policy():
    """TriageInput ships an empty GateSettings, so `readiness` is unnamed and
    must resolve to HARD (spec section 7)."""
    s = GateSettings()
    assert s.gates.get("readiness") is None
    assert s.default_gate_policy is GatePolicy.HARD
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gate_settings.py -q -p no:warnings`
Expected: FAIL — `ImportError: cannot import name 'GateSettings' from 'sdlc.models'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/models.py`, immediately after the `GateConfig` class:

```python
class GateSettings(BaseModel):
    """The three fields a durable HITL gate reads (E-42 D3).

    Extracted so GateHost does not depend on PipelineConfig: a triage run has
    roles, memory, research and deploy config it will never use, and taking the
    whole object would drag all of it into triage's input contract.
    """

    gates: dict[str, GateConfig] = Field(default_factory=dict)
    default_gate_policy: GatePolicy = GatePolicy.HARD
    gate_timeout_hours: int = 48
```

In `PipelineConfig`, add:

```python
def gate_settings(self) -> GateSettings:
    """Project the three gate fields. `gates` is copied, not aliased --
    a workflow handed these must not be able to mutate the config."""
    return GateSettings(
        gates=dict(self.gates),
        default_gate_policy=self.default_gate_policy,
        gate_timeout_hours=self.gate_timeout_hours,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gate_settings.py -q -p no:warnings`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/models.py tests/test_gate_settings.py
git commit -m "feat(models): GateSettings projects the three fields a gate reads (E-42)"
```

---

### Task 2: Extract the `GateHost` mixin

This is the only task that touches `feature.py`. It must land atomically —
there is no intermediate state where the tree is green with the members half
moved.

**Files:**
- Create: `src/sdlc/workflows/gates.py`
- Modify: `src/sdlc/workflows/feature.py` (remove moved members; inherit; override 3 hooks; refit 9 `self._gate(` call sites at lines 1216, 1332, 1341, 1462, 1678, 1899, 2425, 2459, 2498, 2538)
- Modify: `tests/test_pending_wiring.py:30-39` (re-point source assertions)
- Test: `tests/test_gate_host.py` (create)

**Interfaces:**
- Consumes: `GateSettings` from Task 1.
- Produces: `class GateHost` with `_gate(name, settings, auto_decision=None, round=1, context=None, confidence=None, default_policy=None) -> GateDecision`, the `_pending` / `_gate_decisions` / `_status` state, the `submit_gate_decision` signal, the `status` / `pending_gate` / `pending_decisions` queries, and three no-op hooks: `_on_gate_awaited(name, round)`, `_on_gate_decided(name, round, policy, decision)`, `_on_notified(gate, reason, notifier, delivered, error)`. Tasks 6 and 7 subclass it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gate_host.py`:

```python
"""E-42 D2: the gate is shared code, not duplicated code. Writing FR-302's
first-decision-wins rule twice is the failure shape
2026-07-16-registry-drives-every-role was written about."""

from __future__ import annotations

import datetime as dt
import inspect

import pytest

from sdlc.models import GateDecision, GateOutcome, GatePolicy, GateSettings
from sdlc.pending import StageGatePending
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.gates import GateHost


def test_feature_workflow_inherits_the_shared_gate():
    assert issubclass(FeatureWorkflow, GateHost)


def test_gate_takes_settings_not_pipeline_config():
    sig = inspect.signature(GateHost._gate)
    assert "settings" in sig.parameters
    assert "cfg" not in sig.parameters
    # E-6/E-7 callers still pass these.
    assert "context" in sig.parameters
    assert "auto_decision" in sig.parameters
    assert "default_policy" in sig.parameters


def test_hooks_are_no_ops_on_the_base():
    """Triage overrides none of them. A base that emitted or retained would
    force gates.py to import RunEventKind and the memory activities."""
    for name in ("_on_gate_awaited", "_on_gate_decided", "_on_notified"):
        assert inspect.iscoroutinefunction(getattr(GateHost, name)), name


@pytest.fixture
def frozen_now(monkeypatch):
    """submit_gate_decision stamps decided_at with workflow.now(), which
    raises outside a workflow. tests/test_pending_wiring.py already does this;
    the module object is shared (both files do `from temporalio import
    workflow`), so patching it once covers gates.py and feature.py alike."""
    from sdlc.workflows import gates as g

    monkeypatch.setattr(g.workflow, "now", lambda: dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))


def test_first_decision_for_a_round_wins(frozen_now):
    """FR-302. decided_by is a Literal["human","policy","timeout"], so the two
    decisions are told apart by their comments, not by an invented name."""
    host = GateHost()
    host.submit_gate_decision(
        GateDecision(
            gate="readiness",
            round=1,
            outcome=GateOutcome.APPROVE,
            decided_by="human",
            comments="first",
        )
    )
    host.submit_gate_decision(
        GateDecision(
            gate="readiness",
            round=1,
            outcome=GateOutcome.REJECT,
            decided_by="human",
            comments="second",
        )
    )
    kept = host._gate_decisions["readiness#1"]
    assert kept.comments == "first"
    assert kept.outcome is GateOutcome.APPROVE


def test_submit_pops_only_that_round_from_pending(frozen_now):
    host = GateHost()
    host._pending["readiness#1"] = StageGatePending(
        key="readiness#1", gate="readiness", round=1, spec_summary="s"
    )
    host._pending["readiness#2"] = StageGatePending(
        key="readiness#2", gate="readiness", round=2, spec_summary="s"
    )
    host.submit_gate_decision(
        GateDecision(gate="readiness", round=1, outcome=GateOutcome.APPROVE, decided_by="human")
    )
    assert "readiness#1" not in host._pending
    assert "readiness#2" in host._pending


def test_pending_decisions_query_returns_the_registry():
    host = GateHost()
    p = StageGatePending(key="readiness#1", gate="readiness", round=1, spec_summary="s")
    host._pending[p.key] = p
    assert host.pending_decisions() == [p]


def test_gate_settings_reaches_the_host_unchanged():
    s = GateSettings(default_gate_policy=GatePolicy.OFF, gate_timeout_hours=1)
    assert s.default_gate_policy is GatePolicy.OFF
    assert s.gate_timeout_hours == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gate_host.py -q -p no:warnings`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.workflows.gates'`

- [ ] **Step 3: Create `src/sdlc/workflows/gates.py`**

Move the bodies verbatim from `feature.py` — do not rewrite them. The only
edits are `cfg` → `settings` in `_gate`, and replacing the four `self._emit`
and one `self._retain` calls with hook calls.

```python
"""GateHost -- durable human-in-the-loop gate mechanics (FR-301/302/303).

Extracted from FeatureWorkflow (E-42 D2) so a second workflow can host a gate
without restating "first decision for (gate, round) wins". Duplicating that
rule is the failure shape 2026-07-16-registry-drives-every-role was written
about: an invariant that holds only while two copies happen to agree.

What this owns: policy resolution, (gate, round) identity, the notification
schedule, the timeout decision, and the four HITL handlers. What it does NOT
own: what a workflow *does* with a decided gate. That is three no-op hooks --
FeatureWorkflow emits a RunEvent and retains a memory; TriageWorkflow does
neither, and a base that did either would force this module to import
RunEventKind and the memory activities.

Signals and queries defined here register on every subclass: temporalio
collects them with inspect.getmembers, which walks the MRO
(temporalio/workflow/_definition.py:288). Only @workflow.run must be defined
on the concrete class (_definition.py:128).
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..models import (
        GateConfig,
        GateDecision,
        GateOutcome,
        GatePolicy,
        GateSettings,
        TimeoutAction,
        gate_key,
    )
    from ..notify.activities import notify
    from ..notify.contract import NotifyInput, NotifyReason, Results
    from ..notify.schedule import build_schedule
    from ..pending import GateContext, PendingDecision, gate_pending

# E-9: delivery is best-effort and must never delay a gate. A single attempt:
# the notify activity already attempts every configured route internally, and
# the short schedule_to_start fails fast when no worker registered notify
# rather than hanging the gate forever.
NOTIFY_ACT = dict(
    start_to_close_timeout=timedelta(seconds=30),
    schedule_to_start_timeout=timedelta(seconds=5),
    retry_policy=RetryPolicy(maximum_attempts=1),
)


class GateHost:
    """Mixin. Subclasses must call super().__init__() and define their own
    @workflow.run."""

    def __init__(self) -> None:
        self._gate_decisions: dict[str, GateDecision] = {}
        # E-6: structured pending-decision registry, keyed by resolution key
        # (question id, or gate_key(gate, round)). Rendered by sdlc.channels.
        self._pending: dict[str, PendingDecision] = {}
        self._status: str = "starting"

    # ------------------------- hooks (no-op) ---------------------------

    async def _on_gate_awaited(self, name: str, round: int) -> None:
        """A gate has opened and is now waiting on a human."""

    async def _on_gate_decided(
        self, name: str, round: int, policy: GatePolicy, decision: GateDecision
    ) -> None:
        """A gate has been decided, by a human, a policy, or a timeout."""

    async def _on_notified(
        self, gate: str, reason: NotifyReason, notifier: str, delivered: bool, error: str = ""
    ) -> None:
        """One notification route reported its delivery outcome."""

    # -------------------- signals / queries (HITL) ----------------------

    @workflow.signal
    def submit_gate_decision(self, decision: GateDecision) -> None:
        # Idempotent per (gate, round): first decision for a round wins.
        key = gate_key(decision.gate, decision.round)
        if key not in self._gate_decisions:
            decision.decided_at = workflow.now()
            self._gate_decisions[key] = decision
        # _pending means "not yet decided" for every variant (E-7).
        self._pending.pop(key, None)

    @workflow.query
    def status(self) -> str:
        return self._status

    @workflow.query
    def pending_gate(self) -> str | None:
        return self._status if self._status.startswith("awaiting:") else None

    @workflow.query
    def pending_decisions(self) -> list[PendingDecision]:
        """Structured items a human currently owes a decision on (E-6).
        Empty when nothing is awaiting. Rendered by sdlc.channels."""
        return list(self._pending.values())

    # ---------------------------- mechanics -----------------------------

    async def _notify(self, pending, reason, opened_at, deadline) -> None:
        """Fire-and-forget delivery. A transport failure can never block,
        fail, or delay a gate -- but it is reported through _on_notified, not
        swallowed, because a notification that failed to deliver must be
        visible (spec 6, ROADMAP 9.6)."""
        gate = getattr(pending, "gate", None) or pending.key
        try:
            out: Results = await workflow.execute_activity(
                notify,
                NotifyInput(
                    run_id=workflow.info().workflow_id,
                    pending=pending,
                    reason=reason,
                    opened_at=opened_at,
                    now=workflow.now(),
                    deadline=deadline,
                ),
                **NOTIFY_ACT,
            )
        except Exception as e:  # noqa: BLE001
            await self._on_notified(gate, reason, "unresolved", False, str(e)[:200])
            return
        for r in out.results:
            await self._on_notified(gate, reason, r.notifier, r.delivered, (r.error or "")[:200])

    async def _wait_for_decision(self, key, pending, schedule, expires):
        """Wait for the gate's signal, firing each notification as its
        deadline passes. Returns the decision, or None when the gate expired
        undecided. Exits the instant the signal lands, so there is nothing to
        cancel -- the reason this is a loop rather than a detached
        coroutine."""
        opened_at = schedule[0][0]
        decided = lambda: key in self._gate_decisions  # noqa: E731
        for at, reason in schedule:
            try:
                await workflow.wait_condition(decided, timeout=at - workflow.now())
                return self._gate_decisions[key]
            except TimeoutError:
                await self._notify(pending, reason, opened_at, expires)
        if expires is None:  # HOLD: wait without a deadline
            await workflow.wait_condition(decided)
            return self._gate_decisions[key]
        return None

    async def _gate(
        self,
        name: str,
        settings: GateSettings,
        auto_decision: GateDecision | None = None,
        round: int = 1,
        context: GateContext | None = None,
        confidence: float | None = None,
        default_policy: GatePolicy | None = None,
    ) -> GateDecision:
        """Durable HITL gate with policy-based auto-approval."""
        gate_cfg = settings.gates.get(
            name, GateConfig(policy=default_policy or settings.default_gate_policy)
        )
        policy = gate_cfg.policy
        key = gate_key(name, round)

        if policy == GatePolicy.OFF:
            decision = GateDecision(
                gate=name, round=round, outcome=GateOutcome.APPROVE, decided_by="policy"
            )
        elif policy == GatePolicy.SOFT and auto_decision and auto_decision.approved:
            decision = auto_decision
        else:
            pending = gate_pending(name, round, context)
            self._pending[key] = pending
            self._status = f"awaiting:{name}"
            await self._on_gate_awaited(name, round)
            schedule, expires = build_schedule(
                gate_cfg, settings.gate_timeout_hours, workflow.now()
            )
            try:
                decided = await self._wait_for_decision(key, pending, schedule, expires)
                if decided is not None:
                    decision = decided
                else:
                    # Expired undecided. HOLD never reaches here -- its
                    # schedule has no final deadline, so _wait_for_decision
                    # waits without one.
                    decision = GateDecision(
                        gate=name,
                        round=round,
                        decided_by="timeout",
                        outcome=(
                            GateOutcome.APPROVE
                            if gate_cfg.on_timeout is TimeoutAction.APPROVE
                            else GateOutcome.REJECT
                        ),
                        comments=f"no decision within {settings.gate_timeout_hours}h",
                    )
            finally:
                self._status = "running"
                self._pending.pop(key, None)

        await self._on_gate_decided(name, round, policy, decision)
        return decision
```

- [ ] **Step 4: Refit `feature.py`**

1. Declare the mixin and chain `__init__`:

```python
@workflow.defn
class FeatureWorkflow(GateHost):
    def __init__(self) -> None:
        super().__init__()
        self._question_answers: dict[str, str] = {}
        self._memory_watermark: str | None = None
        # E-42: cfg is threaded as a parameter everywhere else; the gate hooks
        # run inside GateHost and cannot receive it, so run() stashes it here.
        self._cfg: PipelineConfig | None = None
        ...  # every other field unchanged
```

Delete from `__init__`: `self._gate_decisions`, `self._pending`, `self._status`
(now owned by the base).

2. Delete these members from `FeatureWorkflow`: `_gate`, `_wait_for_decision`,
   `_notify`, `submit_gate_decision`, `status`, `pending_gate`,
   `pending_decisions`, and the module-level `NOTIFY_ACT`. Keep
   `answer_question` — clarify is a feature-pipeline concept.

3. Add the three hook overrides:

```python
async def _on_gate_awaited(self, name: str, round: int) -> None:
    self._emit(RunEventKind.GATE_AWAITED, stage=name, gate=name, round=str(round))


async def _on_gate_decided(
    self, name: str, round: int, policy: GatePolicy, decision: GateDecision
) -> None:
    self._emit(
        RunEventKind.GATE_DECIDED,
        stage=name,
        gate=name,
        round=str(round),
        policy=policy.value,
        decided_by=decision.decided_by,
        approved=("true" if decision.approved else "false"),
    )
    cfg = self._cfg
    if cfg is None:
        return
    await self._retain(
        cfg,
        MemoryKind.GATE_FEEDBACK,
        cfg.memory.project_bank,
        text=f"gate {name}#{round}: {decision.outcome.value}"
        f"{' — ' + decision.comments if decision.comments else ''}",
        metadata={"gate": name, "round": str(round), "run_id": workflow.info().workflow_id},
    )


async def _on_notified(
    self, gate: str, reason: NotifyReason, notifier: str, delivered: bool, error: str = ""
) -> None:
    self._emit(
        RunEventKind.GATE_NOTIFIED,
        stage=gate,
        gate=gate,
        reason=reason.value,
        notifier=notifier,
        delivered="true" if delivered else "false",
        **({"error": error} if error else {}),
    )
```

> **Behaviour note — the `confidence` field.** Today `_gate` folds
> `confidence=...` into the `GATE_DECIDED` event. The hook signature does not
> carry it, so pass it through `GateContext` is *not* an option (context is
> render-only). Keep the existing behaviour by having `_gate` stash it:
> add `self._last_gate_confidence: float | None = None` in `GateHost.__init__`,
> set it at the top of `_gate` from the `confidence` parameter, and read it in
> `FeatureWorkflow._on_gate_decided`:
>
> ```python
>         conf = self._last_gate_confidence
>         self._emit(
>             RunEventKind.GATE_DECIDED, stage=name,
>             gate=name, round=str(round), policy=policy.value,
>             decided_by=decision.decided_by,
>             approved=("true" if decision.approved else "false"),
>             **({"confidence": str(conf)} if conf is not None else {}))
> ```
>
> This preserves `RunSummary.gates[].confidence`, which SC-6's calibration
> compare reads. Losing it would be a silent regression in a field the
> benchmark aggregates.

4. Add `self._cfg = cfg` as the first statement of `FeatureWorkflow.run()`.

5. Refit all 9 `self._gate(` call sites — lines 1216, 1332, 1341, 1462, 1678,
   1899, 2425, 2459, 2498, 2538 — changing the second positional argument
   `cfg` to `cfg.gate_settings()`. Example:

```python
        decision = await self._gate(
            "budget", cfg.gate_settings(), round=self._budget_crossings,
            ...
```

6. Fix imports: add `from .gates import GateHost` (inside the
   `imports_passed_through` block); `NotifyReason` stays imported for the hook
   signature; `NotifyInput` / `Results` / `notify` / `build_schedule` /
   `gate_pending` / `TimeoutAction` / `GateConfig` may now be unused in
   `feature.py` — remove any that `ruff` flags, leave the rest.

- [ ] **Step 5: Re-point the source-text assertions**

`tests/test_pending_wiring.py:30-39` asserts on `feature.py`'s source text.
Two of those strings now live in `gates.py`. Replace the test body with:

```python
GATES_SRC = pathlib.Path("src/sdlc/workflows/gates.py")


def test_gate_surface_wires_pending_population():
    """E-42: the query and the pending registry moved to GateHost; the
    clarify half stayed in FeatureWorkflow."""
    gates = GATES_SRC.read_text(encoding="utf-8")
    assert "def pending_decisions(" in gates
    assert "gate_pending(" in gates
    assert "self._pending" in gates
    assert "self._pending.pop(" in gates

    feature = SRC.read_text(encoding="utf-8")
    assert "clarify_pending(" in feature
```

- [ ] **Step 6: Run the full gate suite to verify nothing regressed**

Run:
```bash
python -m pytest tests/ -q -p no:warnings -k "gate or pending or notif or budget or channel"
```
Expected: all pass. These are the FR-301/302/303 regression proof —
`test_gate_decision`, `test_gate_notifications`, `test_gate_timeout_action`,
`test_gate_revision_loop`, `test_soft_gate_auto_approval`, `test_budget_gate`,
`test_tool_approval_gate`, `test_merge_gate_wiring`, `test_pending_wiring`,
`test_channel_transport`.

- [ ] **Step 7: Run the new test and the whole suite**

Run: `python -m pytest tests/test_gate_host.py -q -p no:warnings`
Expected: 7 passed

Run: `python -m pytest tests/ -q -p no:warnings; echo "exit=$?"`
Expected: `exit=0`

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/workflows/gates.py src/sdlc/workflows/feature.py tests/test_gate_host.py tests/test_pending_wiring.py
git commit -m "refactor(gates): extract GateHost so a second workflow can host a gate (E-42)"
```

---

### Task 3: `ReadinessOverride` on the triage artifact

**Files:**
- Modify: `src/sdlc/triage/models.py` (add class after `Readiness`; add field to `RepoTriage`)
- Test: `tests/test_triage_override.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `ReadinessOverride(approved_by: Literal["human","policy","timeout"], reviewer: str | None, reason: str, decided_at: datetime, gate_round: int)` and `RepoTriage.override: ReadinessOverride | None`. Task 7 constructs it.

> **Read this before writing the model.** `GateDecision.decided_by`
> (`models.py:697`) is `Literal["human", "policy", "timeout"]` — the *class* of
> decider, not a principal. The operator's identity is the separate, optional,
> self-asserted `GateDecision.reviewer`, which is the gap FR-1004 exists to
> close. `ReadinessOverride` mirrors both and hides neither.

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_override.py`:

```python
"""FR-903 (E-42 D1): an audited human decision to proceed despite a verdict
that is not READY, recorded ON the artifact so E-45 need not re-ask."""

from __future__ import annotations

import datetime as dt

from sdlc.measurement import Measurement
from sdlc.triage.models import (
    Readiness,
    ReadinessOverride,
    RepoTriage,
    Verdict,
)


def _not_ready() -> Readiness:
    return Readiness(
        buildable=Measurement.measured(0.0),
        runnable=Measurement.measured(0.0),
        tests_present=Measurement.measured(1.0),
        structure_discernible=Measurement.measured(1.0),
        verdict=Verdict.NOT_READY,
    )


def test_repo_triage_defaults_to_no_override():
    t = RepoTriage(repo_dir="/r", commit_sha="abc", readiness=_not_ready())
    assert t.override is None


def test_override_records_the_class_of_approver_verbatim():
    """'policy' and 'timeout' must stay legible as non-human (spec section 7)."""
    o = ReadinessOverride(
        approved_by="policy",
        reason="gate off",
        decided_at=dt.datetime(2026, 8, 8, tzinfo=dt.timezone.utc),
        gate_round=1,
    )
    t = RepoTriage(repo_dir="/r", commit_sha="abc", readiness=_not_ready(), override=o)
    assert t.override.approved_by == "policy"
    assert t.override.reviewer is None
    assert t.override.gate_round == 1


def test_approved_by_rejects_a_principal():
    """decided_by is a class of decider, not a name. An identity that looked
    like an approval class would make 'a human approved' unfalsifiable."""
    import pytest

    with pytest.raises(Exception):
        ReadinessOverride(
            approved_by="alice",
            reason="r",
            decided_at=dt.datetime(2026, 8, 8, tzinfo=dt.timezone.utc),
            gate_round=1,
        )


def test_reviewer_carries_the_self_asserted_identity():
    """FR-1004's gap, mirrored rather than hidden."""
    o = ReadinessOverride(
        approved_by="human",
        reviewer="alice",
        reason="ok",
        decided_at=dt.datetime(2026, 8, 8, tzinfo=dt.timezone.utc),
        gate_round=1,
    )
    assert o.approved_by == "human"
    assert o.reviewer == "alice"


def test_triage_models_stays_pure():
    """The module must not import models.py, activities.py or temporalio --
    a dependency there would appear as a reviewable import."""
    import pathlib

    src = pathlib.Path("src/sdlc/triage/models.py").read_text(encoding="utf-8")
    assert "temporalio" not in src
    assert "from ..models" not in src
    assert "from ..activities" not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_triage_override.py -q -p no:warnings`
Expected: FAIL — `ImportError: cannot import name 'ReadinessOverride'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/triage/models.py`, add `from datetime import datetime` to the
imports (`Literal` is already imported), then after the `Readiness` class:

```python
class ReadinessOverride(BaseModel):
    """FR-903: an audited decision to proceed despite a verdict that is not
    READY (E-42 D1).

    Local and pure -- this module must not import models.py, so GateDecision
    cannot appear here; TriageWorkflow maps one to the other.

    `approved_by` carries GateDecision.decided_by VERBATIM: it is the CLASS of
    decider, so "policy" (gate OFF) and "timeout" (on_timeout=APPROVE) stay
    legible as non-human on the face of the artifact. `reviewer` is the
    operator identity -- optional and self-asserted, the gap FR-1004 exists to
    close. Mirrored rather than hidden: a bundle claiming a named human
    approved a not-ready repository, on a field anyone can set, would be worse
    than one that says "human" and leaves the principal unproven.
    """

    approved_by: Literal["human", "policy", "timeout"]
    reviewer: str | None = None
    reason: str
    decided_at: datetime
    gate_round: int
```

And on `RepoTriage`:

```python
    override: ReadinessOverride | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_triage_override.py -q -p no:warnings`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/triage/models.py tests/test_triage_override.py
git commit -m "feat(triage): ReadinessOverride records who approved, verbatim (E-42)"
```

---

### Task 4: `SignalSpec.readiness_keys`

**Files:**
- Modify: `src/sdlc/triage/registry.py`
- Test: `tests/test_triage_registry_readiness_keys.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `SignalSpec.readiness_keys: tuple[str, ...]`. Task 6 reads it to
  synthesize precise `not_collected` metrics for a skipped or failed signal.

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_registry_readiness_keys.py`:

```python
"""E-42 D8a: which readiness dimensions a signal owes is DECLARED, so a
skipped or failed signal can report not_collected for exactly those keys
instead of leaving them unreported."""

from __future__ import annotations

from sdlc.triage.models import (
    M_BUILDABLE,
    M_RUNNABLE,
    M_STRUCTURE,
    M_TESTS_PRESENT,
    READINESS_KEYS,
)
from sdlc.triage.registry import SIGNALS


def test_build_probe_owns_buildable_and_runnable():
    assert SIGNALS["build_probe"].readiness_keys == (M_BUILDABLE, M_RUNNABLE)


def test_baseline_owns_tests_present():
    assert SIGNALS["baseline"].readiness_keys == (M_TESTS_PRESENT,)


def test_scaffold_owns_structure_discernible():
    """E-41b moved this dimension off baseline; the declaration must agree."""
    assert SIGNALS["scaffold"].readiness_keys == (M_STRUCTURE,)


def test_signals_owning_nothing_declare_nothing():
    for sid in ("secrets", "dependencies", "misconfig", "outliers"):
        assert SIGNALS[sid].readiness_keys == (), sid


def test_every_readiness_key_has_exactly_one_owner():
    """FR-902's one-implementation rule, now declarative. compute_readiness
    still detects a duplicate at runtime -- that is the backstop against this
    declaration drifting, not the only statement of the rule."""
    owners: dict[str, str] = {}
    for spec in SIGNALS.values():
        for key in spec.readiness_keys:
            assert key not in owners, f"{key} claimed by {owners.get(key)} and {spec.id}"
            owners[key] = spec.id
    assert set(owners) == set(READINESS_KEYS)


def test_the_declaration_matches_what_the_signals_actually_report():
    """The drift guard. A static declaration that no test compares against
    real output is a second registry waiting to disagree with the first --
    which is the whole failure mode E-42 D2 exists to avoid.

    The three owning signals expose PURE evaluate/interpret functions, so this
    needs no repository and no Temporal: call them and read the metric keys.
    """
    from sdlc.triage.signals import baseline, build_probe, scaffold

    probe = build_probe.interpret(False, None, None, None, None)
    assert set(probe.metrics) == set(SIGNALS["build_probe"].readiness_keys)

    base = baseline.evaluate([], "", None)
    assert set(base.metrics) & set(READINESS_KEYS) == set(SIGNALS["baseline"].readiness_keys)

    scaf = scaffold.evaluate([], {}, None, None)
    assert set(scaf.metrics) & set(READINESS_KEYS) == set(SIGNALS["scaffold"].readiness_keys)
```

> Read each `evaluate`/`interpret` signature before writing this test —
> `build_probe.interpret(marker_found, install, build, test, verdict)` is
> confirmed from `activities.py:381`, but check `baseline.evaluate` and
> `scaffold.evaluate` in their own modules and pass whatever "empty repository"
> arguments they require. The assertion, not the argument list, is the point.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_triage_registry_readiness_keys.py -q -p no:warnings`
Expected: FAIL — `AttributeError: 'SignalSpec' object has no attribute 'readiness_keys'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/triage/registry.py`, extend the model and the four affected entries:

```python
from .models import M_BUILDABLE, M_RUNNABLE, M_STRUCTURE, M_TESTS_PRESENT


class SignalSpec(BaseModel):
    id: str
    version: int
    activity: str  # the @activity.defn name in triage/activities.py
    # E-42 D8a: the readiness dimensions this signal owes. Declared so a
    # skipped or failed signal reports not_collected for exactly these keys
    # rather than leaving the dimension unreported.
    readiness_keys: tuple[str, ...] = ()
```

Then on the entries:

```python
    baseline.SIGNAL_ID: SignalSpec(
        id=baseline.SIGNAL_ID, version=baseline.VERSION,
        activity="triage_baseline",
        readiness_keys=(M_TESTS_PRESENT,)),
    ...
    build_probe.SIGNAL_ID: SignalSpec(
        id=build_probe.SIGNAL_ID, version=build_probe.VERSION,
        activity="triage_build_probe",
        readiness_keys=(M_BUILDABLE, M_RUNNABLE)),
    ...
    scaffold.SIGNAL_ID: SignalSpec(
        id=scaffold.SIGNAL_ID, version=scaffold.VERSION,
        activity="triage_scaffold",
        readiness_keys=(M_STRUCTURE,)),
```

`secrets`, `dependencies`, `misconfig`, `outliers` keep the `()` default.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_triage_registry_readiness_keys.py -q -p no:warnings`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/triage/registry.py tests/test_triage_registry_readiness_keys.py
git commit -m "feat(triage): SignalSpec declares which readiness keys it owes (E-42)"
```

---

### Task 5: `triage_resolve_commit` — pin the commit once

**Files:**
- Modify: `src/sdlc/triage/activities.py` (add near `TriageSignalInput`, line 39)
- Test: `tests/test_triage_resolve_commit.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `TriagePinInput(repo_dir: str, commit: str = "HEAD")`,
  `TriagePin(commit_sha: str, toolchain: str | None)`, and the activity
  `triage_resolve_commit(inp: TriagePinInput) -> TriagePin`. Task 6 calls it first.

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_resolve_commit.py`:

```python
"""E-42 D7: the commit is pinned ONCE, by an activity that also detects the
toolchain. All seven signals then read the same tree, so every evidence
citation resolves at the same path@sha."""

from __future__ import annotations

import subprocess

import pytest

from sdlc.triage.activities import (
    TriagePin,
    TriagePinInput,
    triage_resolve_commit,
)


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    _git(["init", "-q"], d)
    _git(["config", "user.email", "t@t.t"], d)
    _git(["config", "user.name", "t"], d)
    (d / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (d / "app.py").write_text("print(1)\n", encoding="utf-8")
    _git(["add", "."], d)
    _git(["commit", "-qm", "init"], d)
    return d


async def test_resolves_head_to_a_concrete_sha(repo):
    pin = await triage_resolve_commit(TriagePinInput(repo_dir=str(repo)))
    assert isinstance(pin, TriagePin)
    assert len(pin.commit_sha) == 40
    assert all(c in "0123456789abcdef" for c in pin.commit_sha)


async def test_detects_the_toolchain_from_the_marker(repo):
    pin = await triage_resolve_commit(TriagePinInput(repo_dir=str(repo)))
    assert pin.toolchain == "python"


async def test_no_marker_is_a_finding_not_an_error(tmp_path):
    d = tmp_path / "bare"
    d.mkdir()
    _git(["init", "-q"], d)
    _git(["config", "user.email", "t@t.t"], d)
    _git(["config", "user.name", "t"], d)
    (d / "README").write_text("hi\n", encoding="utf-8")
    _git(["add", "."], d)
    _git(["commit", "-qm", "init"], d)
    pin = await triage_resolve_commit(TriagePinInput(repo_dir=str(d)))
    assert pin.toolchain is None


async def test_unresolvable_commit_raises(repo):
    """D8: there is no honest artifact describing a tree we cannot read."""
    with pytest.raises(RuntimeError, match="does not resolve"):
        await triage_resolve_commit(TriagePinInput(repo_dir=str(repo), commit="deadbeef"))
```

> If `pytest-asyncio` is not configured for bare `async def` tests in this
> repo, check `tests/conftest.py` for the existing convention and follow it —
> do not add a new async plugin configuration.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_triage_resolve_commit.py -q -p no:warnings`
Expected: FAIL — `ImportError: cannot import name 'TriagePinInput'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/triage/activities.py`:

```python
@dataclass
class TriagePinInput:
    repo_dir: str
    commit: str = "HEAD"  # an UNRESOLVED ref -- see TriagePin


@dataclass
class TriagePin:
    commit_sha: str
    toolchain: str | None


@activity.defn
async def triage_resolve_commit(inp: TriagePinInput) -> TriagePin:
    """E-42 D7. Resolve the ref to a concrete sha and detect the toolchain in
    one call: RepoTriage.toolchain needs an answer and every signal detects the
    adapter independently anyway.

    Deliberately NOT never-raising, unlike the signal activities: a commit that
    does not resolve is not a not_collected dimension, it is the absence of the
    tree the whole artifact claims to describe.
    """
    proc = _git(["rev-parse", "--verify", f"{inp.commit}^{{commit}}"], cwd=inp.repo_dir)
    if proc.returncode != 0:
        raise RuntimeError(
            f"commit {inp.commit!r} does not resolve in {inp.repo_dir}: {proc.stderr.strip()}"
        )
    commit_sha = proc.stdout.strip()

    found = detect_with_marker_from_paths(tracked_paths(inp.repo_dir, commit_sha))
    return TriagePin(commit_sha=commit_sha, toolchain=found[0].kind.value if found else None)
```

> `detect_with_marker_from_paths` returns `(adapter, marker) | None`
> (`toolchain/adapters.py:202`). The adapter's identifier is
> `kind: ToolchainKind`, a `str` Enum whose only member today is
> `PYTHON = "python"` (`adapters.py:23`) — hence `.kind.value`, not `.name`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_triage_resolve_commit.py -q -p no:warnings`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/triage/activities.py tests/test_triage_resolve_commit.py
git commit -m "feat(triage): triage_resolve_commit pins the sha and detects the toolchain (E-42)"
```

---

### Task 6: `TriageWorkflow` — pin, fan out, compute the verdict

No gate yet. This task delivers a workflow that returns a complete `RepoTriage`.

**Files:**
- Create: `src/sdlc/workflows/triage.py`
- Test: `tests/test_triage_workflow.py` (create)

**Interfaces:**
- Consumes: `GateHost` (Task 2), `SignalSpec.readiness_keys` (Task 4),
  `TriagePinInput` / `TriagePin` / `triage_resolve_commit` (Task 5).
- Produces: `TriageInput(repo_dir, commit, build_probe, advisory_source, gates, max_gate_rounds)`,
  `TriageWorkflow` with `@workflow.run async def run(self, inp: TriageInput) -> RepoTriage`,
  the `triage()` query, and the module function
  `skipped_signal(signal_id: str, reason: str) -> SignalResult`. Task 7 adds the gate.

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_workflow.py`:

```python
"""E-42: TriageWorkflow pins a commit, fans out the signals, and computes the
verdict. The pure helpers are tested directly; sequencing is tested through
the workflow, following tests/test_deployment_workflow.py."""

from __future__ import annotations

from sdlc.measurement import CollectionState, Measurement
from sdlc.triage.models import (
    M_BUILDABLE,
    M_RUNNABLE,
    SignalResult,
    Verdict,
    compute_readiness,
)
from sdlc.workflows.triage import TriageInput, skipped_signal


def test_skipped_signal_reports_its_owed_keys_as_not_collected():
    """D6/D8a: the skip is named, and the dimension is not merely absent."""
    r = skipped_signal("build_probe", "build probe not run (--no-build-probe)")
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert set(r.metrics) == {M_BUILDABLE, M_RUNNABLE}
    for m in r.metrics.values():
        assert m.state is CollectionState.NOT_COLLECTED
        # Measurement's field is `reason` (measurement.py:37), not `detail`,
        # and NOT_COLLECTED without one does not construct.
        assert "--no-build-probe" in m.reason


def test_skipped_signal_owing_nothing_carries_no_metrics():
    r = skipped_signal("secrets", "secrets activity failed: TimeoutError")
    assert r.metrics == {}
    assert r.collected.state is CollectionState.NOT_COLLECTED


def test_skipped_signal_carries_no_findings():
    """SignalResult's validator rejects findings on a NOT_COLLECTED result --
    those would be findings from a run that did not happen."""
    assert skipped_signal("secrets", "why").findings == []


def test_a_skipped_build_probe_forces_indeterminate():
    """D6: no change to compute_readiness is needed."""
    signals = [
        skipped_signal("build_probe", "build probe not run (--no-build-probe)"),
        SignalResult(
            signal="baseline",
            version=2,
            collected=Measurement.measured(1.0),
            metrics={"tests_present": Measurement.measured(3.0)},
        ),
    ]
    assert compute_readiness(signals).verdict is Verdict.INDETERMINATE


def test_triage_input_defaults():
    inp = TriageInput(repo_dir="/r")
    assert inp.commit == "HEAD"
    assert inp.build_probe is True  # D6: on by default
    assert inp.advisory_source == "none"  # E-41a: declared egress, opt-in
    assert inp.gates.gates == {}  # so `readiness` falls back to HARD
    assert inp.max_gate_rounds == 2
```

> `skipped_signal` reads `SIGNALS[signal_id].version`, so these tests do not
> hardcode a signal's version number anywhere except the hand-built
> `SignalResult` above — keep it that way, or a version bump in E-46 breaks
> tests that have nothing to do with it.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_triage_workflow.py -q -p no:warnings`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.workflows.triage'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/workflows/triage.py`:

```python
"""TriageWorkflow (E-42) -- Tier 0's assess half.

Deterministic by construction: no model call, no proposer, no confidence.
It pins a commit, fans out E-41's hygiene signals, and hands the results to
compute_readiness, which stays the only producer of a Verdict.

Operator-run only. triage_build_probe executes the triaged repository's own
code as the worker user with network access (NFR-9); E-57 and E-21 are what
remove that debt.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from pydantic import BaseModel, Field
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..measurement import Measurement
    from ..models import GateSettings
    from ..triage.activities import (
        TriageDependencyInput,
        TriagePin,
        TriagePinInput,
        TriageProbeInput,
        TriageSignalInput,
        triage_baseline,
        triage_build_probe,
        triage_dependencies,
        triage_misconfig,
        triage_outliers,
        triage_resolve_commit,
        triage_scaffold,
        triage_secrets,
    )
    from ..triage.models import RepoTriage, SignalResult, compute_readiness
    from ..triage.registry import SIGNALS
    from .gates import GateHost

# Read-only and idempotent -- retrying is free.
PIN_ACT = dict(
    start_to_close_timeout=timedelta(minutes=2), retry_policy=RetryPolicy(maximum_attempts=3)
)
# Deterministic given a tree and a sha; the retry covers FS/git blips only.
SIGNAL_ACT = dict(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=2)
)
# The only signal doing network I/O (E-41a's AdvisorySource).
DEPS_ACT = dict(
    start_to_close_timeout=timedelta(minutes=15), retry_policy=RetryPolicy(maximum_attempts=3)
)
# ONE attempt, per triage_build_probe's own docstring: a ten-minute timeout
# retried three times is a thirty-minute triage, and a deterministic build
# failure does not become a success on attempt two.
PROBE_ACT = dict(
    start_to_close_timeout=timedelta(minutes=40), retry_policy=RetryPolicy(maximum_attempts=1)
)


class TriageInput(BaseModel):
    repo_dir: str
    commit: str = "HEAD"  # resolved to a sha by D7's activity
    build_probe: bool = True  # D6
    advisory_source: str = "none"  # E-41a: declared egress, off by default
    gates: GateSettings = Field(default_factory=GateSettings)
    max_gate_rounds: int = 2  # D9's bound on the REVISE loop


def skipped_signal(signal_id: str, reason: str) -> SignalResult:
    """A SignalResult for a signal that did not run -- skipped (D6) or failed
    (D8). Its owed readiness keys come from the registry declaration (D8a), so
    the dimension reports WHY it is unmeasured instead of falling through to
    compute_readiness's generic 'no signal reported <key>'.

    Never Measurement.measured(0.0): a run that did not happen has no value.
    """
    spec = SIGNALS[signal_id]
    return SignalResult(
        signal=signal_id,
        version=spec.version,
        collected=Measurement.not_collected(reason),
        metrics={key: Measurement.not_collected(reason) for key in spec.readiness_keys},
    )


@workflow.defn
class TriageWorkflow(GateHost):
    def __init__(self) -> None:
        super().__init__()
        self._triage: RepoTriage | None = None

    @workflow.query
    def triage(self) -> RepoTriage | None:
        """The artifact; None until the fan-out completes (D11)."""
        return self._triage

    async def _one(self, signal_id: str, activity, arg, opts) -> SignalResult:
        """Run one signal. A timeout, a lost worker, or an exhausted retry
        becomes not_collected for THIS signal while every other one still
        reports -- the workflow-side half of E-41 spec D3, which the activity's
        own try/except cannot keep."""
        try:
            return await workflow.execute_activity(activity, arg, **opts)
        except Exception as e:  # noqa: BLE001
            return skipped_signal(
                signal_id, f"{signal_id} activity failed: {type(e).__name__}: {e}"[:300]
            )

    async def _fan_out(self, inp: TriageInput, commit_sha: str) -> list[SignalResult]:
        sig = TriageSignalInput(repo_dir=inp.repo_dir, commit_sha=commit_sha)
        jobs = [
            self._one("baseline", triage_baseline, sig, SIGNAL_ACT),
            self._one("secrets", triage_secrets, sig, SIGNAL_ACT),
            self._one("scaffold", triage_scaffold, sig, SIGNAL_ACT),
            self._one("misconfig", triage_misconfig, sig, SIGNAL_ACT),
            self._one("outliers", triage_outliers, sig, SIGNAL_ACT),
            self._one(
                "dependencies",
                triage_dependencies,
                TriageDependencyInput(
                    repo_dir=inp.repo_dir,
                    commit_sha=commit_sha,
                    advisory_source=inp.advisory_source,
                ),
                DEPS_ACT,
            ),
        ]
        if inp.build_probe:
            jobs.append(
                self._one(
                    "build_probe",
                    triage_build_probe,
                    TriageProbeInput(repo_dir=inp.repo_dir, commit_sha=commit_sha),
                    PROBE_ACT,
                )
            )
        results = list(await asyncio.gather(*jobs))
        if not inp.build_probe:
            results.append(skipped_signal("build_probe", "build probe not run (--no-build-probe)"))
        return results

    async def _assess(self, inp: TriageInput) -> RepoTriage:
        pin: TriagePin = await workflow.execute_activity(
            triage_resolve_commit,
            TriagePinInput(repo_dir=inp.repo_dir, commit=inp.commit),
            **PIN_ACT,
        )
        self._status = "running"
        signals = await self._fan_out(inp, pin.commit_sha)
        return RepoTriage(
            repo_dir=inp.repo_dir,
            commit_sha=pin.commit_sha,
            toolchain=pin.toolchain,
            readiness=compute_readiness(signals),
            signals=signals,
        )

    @workflow.run
    async def run(self, inp: TriageInput) -> RepoTriage:
        self._triage = await self._assess(inp)
        self._status = f"triaged:{self._triage.readiness.verdict.value}"
        return self._triage
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_triage_workflow.py -q -p no:warnings`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/triage.py tests/test_triage_workflow.py
git commit -m "feat(triage): TriageWorkflow pins, fans out, and computes the verdict (E-42)"
```

---

### Task 7: The readiness gate

**Files:**
- Modify: `src/sdlc/workflows/triage.py` (add the gate to `run`, add `_readiness_summary`)
- Test: `tests/test_triage_readiness_gate.py` (create)

**Interfaces:**
- Consumes: `GateHost._gate` (Task 2), `ReadinessOverride` (Task 3), `TriageWorkflow._assess` (Task 6).
- Produces: `_readiness_summary(t: RepoTriage) -> str` and the gated `run()`.
  Task 8 drives it from the CLI.

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_readiness_gate.py`:

```python
"""FR-903 (E-42 section 7): the gate that stands between a triaged repo and
Tier 2, and the override that records a decision to proceed anyway."""

from __future__ import annotations

import datetime as dt

from sdlc.measurement import Measurement
from sdlc.models import GateDecision, GateOutcome
from sdlc.triage.models import (
    Readiness,
    RepoTriage,
    TriageFinding,
    FixClass,
    SignalResult,
    Verdict,
)
from sdlc.workflows.triage import _readiness_summary, override_from


def _triage(verdict=Verdict.NOT_READY) -> RepoTriage:
    return RepoTriage(
        repo_dir="/r",
        commit_sha="a" * 40,
        readiness=Readiness(
            buildable=Measurement.measured(0.0),
            runnable=Measurement.measured(0.0),
            tests_present=Measurement.measured(0.0),
            structure_discernible=Measurement.measured(1.0),
            verdict=verdict,
        ),
        signals=[
            SignalResult(
                signal="secrets",
                version=2,
                collected=Measurement.measured(1.0),
                findings=[
                    TriageFinding(
                        signal="secrets",
                        rule="committed_env",
                        severity="critical",
                        detail="tracked .env",
                        path=".env",
                        fix_class=FixClass.JUDGEMENT,
                    )
                ],
            )
        ],
    )


def test_summary_names_the_verdict_and_the_blocking_dimensions():
    s = _readiness_summary(_triage())
    assert "not_ready" in s
    assert "buildable" in s and "runnable" in s and "tests_present" in s
    # A dimension that passed is not listed as blocking.
    assert "structure_discernible" not in s


def test_summary_counts_findings_by_severity():
    assert "critical: 1" in _readiness_summary(_triage())


def test_summary_is_ascii():
    """The Windows console cannot print non-ASCII."""
    _readiness_summary(_triage()).encode("ascii")


def test_override_records_decided_by_verbatim():
    """All three approval classes record an override -- one rule, no special
    cases -- and 'policy'/'timeout' stay legible as non-human."""
    for who in ("human", "policy", "timeout"):
        d = GateDecision(
            gate="readiness",
            round=1,
            outcome=GateOutcome.APPROVE,
            decided_by=who,
            comments="ship it",
            decided_at=dt.datetime(2026, 8, 8, tzinfo=dt.timezone.utc),
        )
        o = override_from(d)
        assert o.approved_by == who
        assert o.reason == "ship it"
        assert o.gate_round == 1


def test_override_carries_the_reviewer_when_present():
    d = GateDecision(
        gate="readiness",
        round=1,
        outcome=GateOutcome.APPROVE,
        decided_by="human",
        reviewer="alice",
        comments="ok",
        decided_at=dt.datetime(2026, 8, 8, tzinfo=dt.timezone.utc),
    )
    assert override_from(d).reviewer == "alice"


def test_override_from_a_rejection_is_none():
    d = GateDecision(gate="readiness", round=1, outcome=GateOutcome.REJECT, decided_by="human")
    assert override_from(d) is None


def test_override_from_a_revise_is_none():
    """REVISE is not an approval -- GateDecision.approved is APPROVE-only."""
    d = GateDecision(gate="readiness", round=1, outcome=GateOutcome.REVISE, decided_by="human")
    assert override_from(d) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_triage_readiness_gate.py -q -p no:warnings`
Expected: FAIL — `ImportError: cannot import name '_readiness_summary'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/sdlc/workflows/triage.py` (module level, above the workflow):

```python
def _readiness_summary(t: RepoTriage) -> str:
    """ASCII render for the gate's pending item. Names the verdict, the
    dimensions that blocked it, and the finding counts by severity."""
    r = t.readiness
    dims = {
        "buildable": r.buildable,
        "runnable": r.runnable,
        "tests_present": r.tests_present,
        "structure_discernible": r.structure_discernible,
    }
    blocking = []
    for name, m in dims.items():
        if m.state is not CollectionState.MEASURED:
            blocking.append(f"  {name}: not measured ({m.reason})")
        elif (m.value or 0.0) <= 0:
            blocking.append(f"  {name}: 0")
    counts: dict[str, int] = {}
    for s in t.signals:
        for f in s.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
    order = ("critical", "high", "medium", "low")
    tally = ", ".join(f"{sev}: {counts[sev]}" for sev in order if sev in counts) or "none"
    return (
        f"verdict: {r.verdict.value}\n"
        f"commit: {t.commit_sha}\n"
        f"toolchain: {t.toolchain or 'unknown'}\n"
        f"blocking:\n" + ("\n".join(blocking) or "  none") + "\n"
        f"findings ({tally})"
    )


def override_from(decision: GateDecision) -> ReadinessOverride | None:
    """FR-903. Every APPROVE records an override -- one rule, no special
    cases -- with approved_by carrying decided_by VERBATIM, so "policy"
    (gate OFF) and "timeout" (on_timeout=APPROVE) stay legible as non-human.
    E-45 may narrow its admission rule to human approvals; what this refuses
    to do is discard the distinction."""
    if not decision.approved:
        return None
    return ReadinessOverride(
        approved_by=decision.decided_by,  # Literal["human","policy","timeout"]
        reviewer=decision.reviewer,  # self-asserted identity (FR-1004)
        reason=decision.comments or "",
        decided_at=decision.decided_at or workflow.now(),
        gate_round=decision.round,
    )
```

Add imports: `CollectionState` from `..measurement`, `GateDecision` /
`GateOutcome` from `..models`, `ReadinessOverride` from `..triage.models`,
`GateContext` from `..pending`.

Replace `run`:

```python
@workflow.run
async def run(self, inp: TriageInput) -> RepoTriage:
    for round in range(1, inp.max_gate_rounds + 1):
        self._triage = await self._assess(inp)
        verdict = self._triage.readiness.verdict
        if verdict is Verdict.READY:
            self._status = "triaged:ready"
            return self._triage

        decision = await self._gate(
            "readiness",
            inp.gates,
            round=round,
            context=GateContext(spec_summary=_readiness_summary(self._triage)),
        )

        if decision.outcome is GateOutcome.REVISE:
            # D9: the operator fixed something. Re-resolve and look again
            # -- round 2 legitimately describes a different commit.
            continue
        if decision.approved:
            self._triage.override = override_from(decision)
            self._status = f"triaged:{verdict.value}+override"
        else:
            self._status = "blocked:readiness"
        return self._triage

    # D9: rounds exhausted. One final gate decides proceed-anyway vs stop;
    # no auto_decision is passed, so a SOFT policy also waits.
    self._triage = await self._assess(inp)
    verdict = self._triage.readiness.verdict
    if verdict is Verdict.READY:
        self._status = "triaged:ready"
        return self._triage
    decision = await self._gate(
        "readiness",
        inp.gates,
        round=inp.max_gate_rounds + 1,
        context=GateContext(spec_summary=_readiness_summary(self._triage)),
    )
    if decision.approved:
        self._triage.override = override_from(decision)
        self._status = f"triaged:{verdict.value}+override"
    else:
        self._status = "blocked:readiness"
    return self._triage
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_triage_readiness_gate.py -q -p no:warnings`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/triage.py tests/test_triage_readiness_gate.py
git commit -m "feat(triage): readiness gate records an audited override (FR-903, E-42)"
```

---

### Task 8: Worker registration, CLI verb, and the end-to-end proof

**Files:**
- Modify: `src/sdlc/worker.py` (imports at line 57; workflow list; activity list at line 119)
- Modify: `src/sdlc/cli.py` (module docstring; `main`'s subparsers; dispatch)
- Test: `tests/test_triage_cli_wiring.py` (create)
- Test: `tests/test_triage_workflow_e2e.py` (create)

**Interfaces:**
- Consumes: everything from Tasks 1-7.
- Produces: the operator path. Nothing downstream depends on it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_triage_cli_wiring.py`:

```python
"""E-42 section 8: the operator path. approve/reject/status need NO changes --
channels/transport.py resolves signals and queries BY NAME and imports nothing
workflow-specific, so the gate surface GateHost gave TriageWorkflow is already
reachable. This test is that claim, checked rather than asserted."""

from __future__ import annotations

import pathlib

from sdlc.workflows.gates import GateHost
from sdlc.workflows.triage import TriageWorkflow


def test_triage_workflow_has_the_hitl_surface():
    for name in ("submit_gate_decision", "status", "pending_decisions", "pending_gate"):
        assert hasattr(TriageWorkflow, name), name
    assert issubclass(TriageWorkflow, GateHost)


def test_transport_stays_workflow_agnostic():
    src = pathlib.Path("src/sdlc/channels/transport.py").read_text(encoding="utf-8")
    assert "FeatureWorkflow" not in src
    assert "TriageWorkflow" not in src


def test_worker_registers_the_triage_workflow_and_pin_activity():
    src = pathlib.Path("src/sdlc/worker.py").read_text(encoding="utf-8")
    assert "TriageWorkflow" in src
    assert "triage_resolve_commit" in src


def test_cli_exposes_the_triage_verb():
    src = pathlib.Path("src/sdlc/cli.py").read_text(encoding="utf-8")
    assert '"triage"' in src or "'triage'" in src
    assert "--no-build-probe" in src
```

Create `tests/test_triage_workflow_e2e.py`:

```python
"""Sequencing through the workflow, following tests/test_deployment_workflow.py
and the WorkflowEnvironment pattern in tests/test_board_workflow.py."""

from __future__ import annotations

import uuid

import pytest
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from temporalio import activity

from sdlc.measurement import Measurement
from sdlc.models import GateDecision, GateOutcome
from sdlc.triage.activities import (
    TriageDependencyInput,
    TriagePin,
    TriagePinInput,
    TriageProbeInput,
    TriageSignalInput,
)
from sdlc.triage.models import SignalResult, Verdict
from sdlc.workflows.triage import TriageInput, TriageWorkflow

TASK_QUEUE = "triage-test"


def _ok(signal: str, version: int, metrics=None) -> SignalResult:
    return SignalResult(
        signal=signal, version=version, collected=Measurement.measured(0.0), metrics=metrics or {}
    )


@activity.defn(name="triage_resolve_commit")
async def fake_pin(inp: TriagePinInput) -> TriagePin:
    return TriagePin(commit_sha="a" * 40, toolchain="python")


@activity.defn(name="triage_baseline")
async def fake_baseline(inp: TriageSignalInput) -> SignalResult:
    return _ok("baseline", 2, {"tests_present": Measurement.measured(3.0)})


@activity.defn(name="triage_scaffold")
async def fake_scaffold(inp: TriageSignalInput) -> SignalResult:
    return _ok("scaffold", 1, {"structure_discernible": Measurement.measured(1.0)})


@activity.defn(name="triage_build_probe")
async def fake_probe(inp: TriageProbeInput) -> SignalResult:
    return _ok(
        "build_probe",
        1,
        {"buildable": Measurement.measured(1.0), "runnable": Measurement.measured(1.0)},
    )


@activity.defn(name="triage_secrets")
async def fake_secrets(inp: TriageSignalInput) -> SignalResult:
    return _ok("secrets", 2)


@activity.defn(name="triage_misconfig")
async def fake_misconfig(inp: TriageSignalInput) -> SignalResult:
    return _ok("misconfig", 1)


@activity.defn(name="triage_outliers")
async def fake_outliers(inp: TriageSignalInput) -> SignalResult:
    return _ok("outliers", 1)


@activity.defn(name="triage_dependencies")
async def fake_deps(inp: TriageDependencyInput) -> SignalResult:
    return _ok("dependencies", 1)


ACTIVITIES = [
    fake_pin,
    fake_baseline,
    fake_scaffold,
    fake_probe,
    fake_secrets,
    fake_misconfig,
    fake_outliers,
    fake_deps,
]


async def test_ready_repo_opens_no_gate():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=[TriageWorkflow], activities=ACTIVITIES
        ):
            handle = await env.client.start_workflow(
                TriageWorkflow.run,
                TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            result = await handle.result()
    assert result.readiness.verdict is Verdict.READY
    assert result.override is None
    assert result.commit_sha == "a" * 40
    assert result.toolchain == "python"


async def test_not_ready_opens_a_gate_that_approve_overrides():
    """Swap the build probe for one reporting an unbuildable repo."""

    @activity.defn(name="triage_build_probe")
    async def broken(inp: TriageProbeInput) -> SignalResult:
        return _ok(
            "build_probe",
            1,
            {"buildable": Measurement.measured(0.0), "runnable": Measurement.measured(0.0)},
        )

    acts = [a for a in ACTIVITIES if a is not fake_probe] + [broken]
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=[TriageWorkflow], activities=acts
        ):
            handle = await env.client.start_workflow(
                TriageWorkflow.run,
                TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

            async def pending():
                return await handle.query(TriageWorkflow.pending_decisions)

            while not await pending():
                await env.sleep(1)
            items = await pending()
            assert items[0].gate == "readiness"
            assert items[0].round == 1
            assert "not_ready" in items[0].spec_summary

            await handle.signal(
                TriageWorkflow.submit_gate_decision,
                GateDecision(
                    gate="readiness",
                    round=1,
                    outcome=GateOutcome.APPROVE,
                    decided_by="human",
                    reviewer="alice",
                    comments="known, accepted",
                ),
            )
            result = await handle.result()

    assert result.readiness.verdict is Verdict.NOT_READY
    assert result.override is not None
    assert result.override.approved_by == "human"
    assert result.override.reviewer == "alice"
    assert result.override.reason == "known, accepted"


async def test_revise_re_runs_the_fan_out_at_round_two():
    """D9: 'I just deleted the committed .env -- look again.' The second round
    re-resolves the commit, so it legitimately describes a different tree."""
    shas = iter(["a" * 40, "b" * 40])

    @activity.defn(name="triage_resolve_commit")
    async def moving_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=next(shas), toolchain="python")

    @activity.defn(name="triage_build_probe")
    async def broken(inp: TriageProbeInput) -> SignalResult:
        return _ok(
            "build_probe",
            1,
            {"buildable": Measurement.measured(0.0), "runnable": Measurement.measured(0.0)},
        )

    acts = [a for a in ACTIVITIES if a not in (fake_probe, fake_pin)] + [broken, moving_pin]
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=[TriageWorkflow], activities=acts
        ):
            handle = await env.client.start_workflow(
                TriageWorkflow.run,
                TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

            while not await handle.query(TriageWorkflow.pending_decisions):
                await env.sleep(1)
            await handle.signal(
                TriageWorkflow.submit_gate_decision,
                GateDecision(
                    gate="readiness",
                    round=1,
                    outcome=GateOutcome.REVISE,
                    decided_by="human",
                    comments="removed the .env",
                ),
            )

            items = []
            while not items or items[0].round != 2:
                await env.sleep(1)
                items = await handle.query(TriageWorkflow.pending_decisions)
            assert items[0].gate == "readiness"

            await handle.signal(
                TriageWorkflow.submit_gate_decision,
                GateDecision(
                    gate="readiness", round=2, outcome=GateOutcome.APPROVE, decided_by="human"
                ),
            )
            result = await handle.result()

    assert result.commit_sha == "b" * 40  # re-resolved, not the round-1 sha
    assert result.override.gate_round == 2


async def test_the_triage_query_serves_the_artifact():
    """D11: the workflow result plus this query ARE the record -- there is no
    durable store until a consumer needs one."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=[TriageWorkflow], activities=ACTIVITIES
        ):
            handle = await env.client.start_workflow(
                TriageWorkflow.run,
                TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            await handle.result()
            served = await handle.query(TriageWorkflow.triage)
    assert served is not None
    assert served.commit_sha == "a" * 40
    assert served.readiness.verdict is Verdict.READY


async def test_a_human_approves_through_the_channel_transport():
    """Spec section 5: channels/transport.py resolves signals and queries BY
    NAME and imports nothing workflow-specific, so `sdlc approve --gate
    readiness` reaches a TriageWorkflow with no change to the channel layer.
    Checked here through the transport itself, not by grepping for a string."""
    from sdlc.channels.contract import Reply
    from sdlc.channels.transport import Selector, resolve, submit

    @activity.defn(name="triage_build_probe")
    async def broken(inp: TriageProbeInput) -> SignalResult:
        return _ok(
            "build_probe",
            1,
            {"buildable": Measurement.measured(0.0), "runnable": Measurement.measured(0.0)},
        )

    acts = [a for a in ACTIVITIES if a is not fake_probe] + [broken]
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=[TriageWorkflow], activities=acts
        ):
            handle = await env.client.start_workflow(
                TriageWorkflow.run,
                TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            while not await handle.query(TriageWorkflow.pending_decisions):
                await env.sleep(1)
            # transport.py:143,149 -- resolve narrows the selector to one
            # pending item, submit translates the reply to its signal.
            pending = await resolve(handle, Selector(reply_kind="gate", name="readiness"))
            out = await submit(handle, pending, Reply(outcome=GateOutcome.APPROVE, text="accepted"))
            assert out.confirmed
            result = await handle.result()
    assert result.override is not None
    assert result.override.reason == "accepted"


async def test_reject_leaves_no_override():
    @activity.defn(name="triage_build_probe")
    async def broken(inp: TriageProbeInput) -> SignalResult:
        return _ok(
            "build_probe",
            1,
            {"buildable": Measurement.measured(0.0), "runnable": Measurement.measured(0.0)},
        )

    acts = [a for a in ACTIVITIES if a is not fake_probe] + [broken]
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=[TriageWorkflow], activities=acts
        ):
            handle = await env.client.start_workflow(
                TriageWorkflow.run,
                TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            while not await handle.query(TriageWorkflow.pending_decisions):
                await env.sleep(1)
            await handle.signal(
                TriageWorkflow.submit_gate_decision,
                GateDecision(
                    gate="readiness",
                    round=1,
                    outcome=GateOutcome.REJECT,
                    decided_by="human",
                    reviewer="alice",
                ),
            )
            result = await handle.result()
    assert result.override is None
    assert await handle.query(TriageWorkflow.status) == "blocked:readiness"


async def test_a_failed_signal_does_not_fail_the_run():
    """D8: the other six still report."""

    @activity.defn(name="triage_secrets")
    async def boom(inp: TriageSignalInput) -> SignalResult:
        raise RuntimeError("worker died")

    acts = [a for a in ACTIVITIES if a is not fake_secrets] + [boom]
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=[TriageWorkflow], activities=acts
        ):
            handle = await env.client.start_workflow(
                TriageWorkflow.run,
                TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            result = await handle.result()
    by_id = {s.signal: s for s in result.signals}
    assert by_id["secrets"].collected.state is CollectionState.NOT_COLLECTED
    assert "worker died" in by_id["secrets"].collected.reason
    assert len(by_id) == 7  # the other six reported
    assert result.readiness.verdict is Verdict.READY  # unaffected dimensions


async def test_skipping_the_build_probe_yields_indeterminate():
    """D6: no gate is opened by the OFF policy, but the artifact still says
    the readiness dimensions were never measured, and why."""
    acts = [a for a in ACTIVITIES if a is not fake_probe]
    gates = GateSettings(gates={"readiness": GateConfig(policy=GatePolicy.OFF)})
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=[TriageWorkflow], activities=acts
        ):
            handle = await env.client.start_workflow(
                TriageWorkflow.run,
                TriageInput(repo_dir="/r", build_probe=False, gates=gates),
                id=f"triage-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            result = await handle.result()
    assert result.readiness.verdict is Verdict.INDETERMINATE
    probe = {s.signal: s for s in result.signals}["build_probe"]
    assert "--no-build-probe" in probe.collected.reason
    assert result.readiness.buildable.state is CollectionState.NOT_COLLECTED
    # OFF still records an override -- and says it was the policy, not a human.
    assert result.override is not None
    assert result.override.approved_by == "policy"
    assert result.override.reviewer is None


async def test_a_soft_policy_still_waits_for_a_human():
    """D10: triage produces no confidence, so a SOFT gate has nothing to
    auto-approve WITH. It degrades to HARD by _gate's existing logic -- no
    special case, but asserted so a future reader does not 'fix' it."""

    @activity.defn(name="triage_build_probe")
    async def broken(inp: TriageProbeInput) -> SignalResult:
        return _ok(
            "build_probe",
            1,
            {"buildable": Measurement.measured(0.0), "runnable": Measurement.measured(0.0)},
        )

    acts = [a for a in ACTIVITIES if a is not fake_probe] + [broken]
    gates = GateSettings(gates={"readiness": GateConfig(policy=GatePolicy.SOFT)})
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=[TriageWorkflow], activities=acts
        ):
            handle = await env.client.start_workflow(
                TriageWorkflow.run,
                TriageInput(repo_dir="/r", gates=gates),
                id=f"triage-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            while not await handle.query(TriageWorkflow.pending_decisions):
                await env.sleep(1)
            # It waited rather than auto-approving: that is the assertion.
            assert await handle.query(TriageWorkflow.status) == "awaiting:readiness"
            await handle.signal(
                TriageWorkflow.submit_gate_decision,
                GateDecision(
                    gate="readiness", round=1, outcome=GateOutcome.REJECT, decided_by="human"
                ),
            )
            await handle.result()
```

Add to that file's imports:

```python
from sdlc.measurement import CollectionState, Measurement
from sdlc.models import (
    GateConfig,
    GateDecision,
    GateOutcome,
    GatePolicy,
    GateSettings,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_triage_cli_wiring.py tests/test_triage_workflow_e2e.py -q -p no:warnings`
Expected: FAIL — worker/CLI assertions fail; e2e fails to find `TriageWorkflow` registered.

- [ ] **Step 3: Register in `worker.py`**

Add to the imports near line 57:

```python
from .triage.activities import (
    triage_baseline,
    triage_build_probe,
    triage_dependencies,
    triage_misconfig,
    triage_outliers,
    triage_resolve_commit,
    triage_scaffold,
    triage_secrets,
)
from .workflows.triage import TriageWorkflow
```

Add `TriageWorkflow` to the `workflows=[...]` list and `triage_resolve_commit`
to the activity list beside the seven signals at line 119.

- [ ] **Step 4: Add the CLI verb**

In `src/sdlc/cli.py`, extend the module docstring:

```
  python -m sdlc.cli triage --repo /path/to/repo [--commit HEAD]
  python -m sdlc.cli triage --repo /path/to/repo --no-build-probe
  python -m sdlc.cli triage show --id triage-myrepo-a1b2c3d
```

Add the parser in `main`:

```python
tr = sub.add_parser("triage")
trsub = tr.add_subparsers(dest="triage_cmd")
tr.add_argument("--repo", help="path to an already-cloned repository")
tr.add_argument("--commit", default="HEAD")
tr.add_argument(
    "--no-build-probe",
    action="store_true",
    dest="no_build_probe",
    help="skip the one signal that executes the repo's own code; readiness becomes INDETERMINATE",
)
tr.add_argument(
    "--advisory-source",
    default="none",
    help="'osv' enables a declared outbound vulnerability lookup; default collects nothing",
)
ts = trsub.add_parser("show")
ts.add_argument("--id", required=True)
```

Add dispatch beside the other commands:

```python
if args.cmd == "triage" and args.triage_cmd == "show":
    handle = client.get_workflow_handle(args.id)
    report = await handle.query("triage")
    print("no triage yet" if report is None else report.model_dump_json(indent=2))
    return

if args.cmd == "triage":
    if not args.repo:
        raise SystemExit("triage requires --repo")
    repo = os.path.abspath(args.repo)
    wf_id = f"triage-{slug(os.path.basename(repo))}"
    handle = await client.start_workflow(
        TriageWorkflow.run,
        TriageInput(
            repo_dir=repo,
            commit=args.commit,
            build_probe=not args.no_build_probe,
            advisory_source=args.advisory_source,
        ),
        id=wf_id,
        task_queue=TASK_QUEUE,
    )
    print(f"started {handle.id}")
    print(
        "NOTE: the build probe executes this repository's own code as "
        "the worker user. Operator-run only (NFR-9)."
    )
    return
```

Import `TriageInput, TriageWorkflow` from `.workflows.triage` at the top.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_triage_cli_wiring.py tests/test_triage_workflow_e2e.py -q -p no:warnings`
Expected: 4 + 9 passed

- [ ] **Step 6: Run the whole suite**

Run: `python -m pytest tests/ -q -p no:warnings; echo "exit=$?"`
Expected: `exit=0`

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/worker.py src/sdlc/cli.py tests/test_triage_cli_wiring.py tests/test_triage_workflow_e2e.py
git commit -m "feat(triage): register TriageWorkflow and add the sdlc triage verb (E-42)"
```

---

### Task 9: Roadmap and documentation

**Files:**
- Modify: `ROADMAP.md` (§1 stage 0 note, §2 FR-901/FR-902/FR-903, §5 US-8, §6 ADR-18, §10 E-42, §0 P5)
- Modify: `docs/superpowers/specs/2026-08-08-triage-workflow-and-readiness-gate-design.md` (Status line)

- [ ] **Step 1: Flip the tracker entries**

In `ROADMAP.md`:

- §0 **P5** — note E-40/E-41/E-42/E-43 landed; only E-44 outstanding.
- §2 **FR-901** → `[x]`, noting the stage and readiness verdict now exist and
  complete on repositories that do not build.
- §2 **FR-903** → `[x]`, noting the gate resolves through FR-301/302 and the
  override is recorded on the artifact.
- §5 **US-8** → `[ ]` ⚠️ partial — verdict half landed, checkable-hygiene-list
  half is E-44.
- §6 **ADR-18** → `[x]`, noting E-45's admission rule is
  `verdict is READY or override is not None`.
- §10 **E-42** → `[x]` with a one-paragraph note recording D2 (the `GateHost`
  extraction) and D8a (`SignalSpec.readiness_keys`), since neither was in the
  roadmap's original one-line description of E-42.
- §15 item 2 — strike E-42 from the ordering; the chain is now `E-44` alone.

Also correct the two stale entries this work sits beside:

- §11 **E-47a** → `[x]` — it merged 2026-08-08 (`src/sdlc/capability/`), and the
  tracker's "last verified 2026-08-07" predates it.
- §2 **FR-913** — note E-47a's identity half landed.

- [ ] **Step 2: Update the spec's status line**

Change `| Status | Approved design, not yet implemented |` to
`| Status | Implemented |`.

- [ ] **Step 3: Verify the claims before committing them**

Run: `python -m pytest tests/ -q -p no:warnings; echo "exit=$?"`
Expected: `exit=0`. Do not flip a `[x]` on a red suite.

- [ ] **Step 4: Commit**

```bash
git add ROADMAP.md docs/superpowers/specs/2026-08-08-triage-workflow-and-readiness-gate-design.md
git commit -m "docs: E-42 lands -- FR-901, FR-903, ADR-18 close (P5 needs only E-44)"
```

---

## Notes for the implementer

**The one risky task is Task 2.** Everything else is additive. If the gate suite
goes red after the extraction, the cause is almost always one of three things:

1. A `self._gate(name, cfg, ...)` call site that still passes `cfg` instead of
   `cfg.gate_settings()`. There are 9; `grep -n "self\._gate(" src/sdlc/workflows/feature.py`
   finds them all.
2. `FeatureWorkflow.__init__` not calling `super().__init__()`, leaving
   `_pending` / `_gate_decisions` / `_status` undefined.
3. The `confidence` field missing from `GATE_DECIDED` — see the behaviour note
   in Task 2 Step 4. `test_model_usage_capture` and the benchmark rollup read it.

**What this feature deliberately does not do:** memoize on
`(tree hash, signal version)` (E-46), start fix runs or compute a before/after
delta (E-44), clone from a URL (E-59), or consume the verdict anywhere (E-45).
If a task seems to want one of those, it has drifted.
