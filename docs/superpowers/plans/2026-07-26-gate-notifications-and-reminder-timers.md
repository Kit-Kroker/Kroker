# E-9 Gate Notifications & Reminder Timers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an open gate reach a human — notify when it opens, remind before it expires, escalate to a fallback route, and stop discarding a green `merge` run on timeout.

**Architecture:** `_gate` (`feature.py:639`) swaps its single `wait_condition(timeout=48h)` for a loop that walks a sorted list of notification deadlines, firing a fire-and-forget `notify` activity at each. Delivery is a registry of `Notifier` adapters (`log`, `webhook`) resolved from a versioned asset, `policy/notifications.yaml`. Rendering reuses E-6's `default_render` unchanged. `GateConfig` gains `on_timeout` so expiry semantics are per-gate.

**Tech Stack:** Python 3.14, Temporal (`temporalio`), Pydantic v2, PyYAML, `pytest` + `pytest-asyncio`, Temporal's `WorkflowEnvironment.start_time_skipping`.

**Spec:** `docs/superpowers/specs/2026-07-26-gate-notifications-and-reminder-timers-design.md`

## Global Constraints

- **All operator-facing strings are ASCII-only.** The Windows console cannot print non-ASCII (`transport.py:11`). Use `->` not `→`, `--` not `—`.
- **Delivery must never break a gate.** Every notification path is wrapped so that any exception leaves the gate decidable. This is the invariant Task 7 tests directly.
- **Never log or trace a resolved webhook URL.** It is a bearer credential. Traces carry the *notifier name* (`webhook`), never the target.
- **Workflow code is sandboxed:** no file I/O, no `datetime.now()`, no `random`. Use `workflow.now()` and put all file reads in activities.
- **Only `merge` changes default behaviour** (`on_timeout=hold`). Every other gate keeps today's `reject`. The existing test suite passing unchanged is part of the proof.
- **New files go under `src/sdlc/notify/`**; `pyproject` packages only `src/`, so nothing lands in `interfaces/`.
- Follow the existing import style: `from __future__ import annotations` at the top of every new module.

---

## File Structure

**Create:**
- `src/sdlc/notify/__init__.py` — public exports
- `src/sdlc/notify/contract.py` — `NotifyReason`, `NotifyInput`, `DeliveryResult`, `Notifier` protocol
- `src/sdlc/notify/schedule.py` — `build_schedule` (pure, no I/O)
- `src/sdlc/notify/render.py` — `RenderedDecision` -> ASCII notification text
- `src/sdlc/notify/routes.py` — `policy/notifications.yaml` loader + route resolution
- `src/sdlc/notify/notifiers.py` — `LogNotifier`, `WebhookNotifier`, `NOTIFIERS`
- `src/sdlc/notify/activities.py` — the `notify` activity
- `policy/notifications.yaml` — the versioned route asset
- `tests/test_notify_schedule.py`, `tests/test_notify_render.py`, `tests/test_notify_routes.py`, `tests/test_notify_notifiers.py`, `tests/test_notify_activity.py`, `tests/test_gate_timeout_action.py`, `tests/test_gate_notifications.py`

**Modify:**
- `src/sdlc/models.py` — `TimeoutAction`, `GateConfig` fields, gate defaults (`:40`, `:684`)
- `src/sdlc/observability/trace.py` — `RunEventKind.GATE_NOTIFIED` (`:15`)
- `src/sdlc/harness/containment.py:188` — promote `_host_allowed` to `host_allowed`
- `src/sdlc/workflows/feature.py` — `NOTIFY_ACT`, `_notify`, `_wait_for_decision`, `_gate` (`:78`, `:639`)
- `src/sdlc/worker.py` — register the `notify` activity

---

### Task 1: `TimeoutAction` and per-gate timer config

**Files:**
- Modify: `src/sdlc/models.py:28-52` (enums + `GateConfig`), `src/sdlc/models.py:684-690` (defaults)
- Test: `tests/test_gate_timeout_action.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `TimeoutAction` (enum: `REJECT="reject"`, `APPROVE="approve"`, `HOLD="hold"`); `GateConfig.on_timeout: TimeoutAction`, `GateConfig.remind_after_hours: int | None`, `GateConfig.escalate_after_hours: int | None`. Tasks 2, 7, 8 all read these.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gate_timeout_action.py`:

```python
"""E-9 Task 1: per-gate timeout semantics. Only `merge` changes default
behaviour; every other gate keeps today's reject."""
from __future__ import annotations

from sdlc.models import GateConfig, GatePolicy, PipelineConfig, TimeoutAction


def test_default_on_timeout_is_reject():
    """Preserves today's behaviour for any gate that does not opt out."""
    assert GateConfig().on_timeout is TimeoutAction.REJECT


def test_timer_overrides_default_to_none():
    cfg = GateConfig()
    assert cfg.remind_after_hours is None
    assert cfg.escalate_after_hours is None


def test_merge_defaults_to_hold_every_other_gate_rejects():
    gates = PipelineConfig().gates
    assert gates["merge"].on_timeout is TimeoutAction.HOLD
    for name in ("clarify", "architecture", "plan", "deploy"):
        assert gates[name].on_timeout is TimeoutAction.REJECT, name


def test_bare_policy_string_still_coerces():
    """GateConfig._coerce is unchanged: existing configs keep parsing and
    keep today's timeout behaviour."""
    cfg = PipelineConfig(gates={"architecture": "hard"})
    assert cfg.gates["architecture"].policy is GatePolicy.HARD
    assert cfg.gates["architecture"].on_timeout is TimeoutAction.REJECT


def test_overrides_round_trip_through_dict_coercion():
    cfg = PipelineConfig(gates={
        "merge": {"policy": "hard", "on_timeout": "approve",
                  "remind_after_hours": 4, "escalate_after_hours": 8},
    })
    g = cfg.gates["merge"]
    assert g.on_timeout is TimeoutAction.APPROVE
    assert (g.remind_after_hours, g.escalate_after_hours) == (4, 8)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gate_timeout_action.py -v`
Expected: FAIL with `ImportError: cannot import name 'TimeoutAction' from 'sdlc.models'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/models.py`, after the `GateOutcome` enum (around line 38), add:

```python
class TimeoutAction(str, Enum):
    """What an expired gate does (FR-303). REJECT is today's behaviour and
    the default everywhere except `merge` -- see PipelineConfig.gates."""
    REJECT = "reject"      # terminal, decided_by="timeout"
    APPROVE = "approve"
    HOLD = "hold"          # no final deadline; stays pending and visible
```

Extend `GateConfig` (line 40):

```python
class GateConfig(BaseModel):
    """Per-gate policy + the confidence bar a SOFT gate must clear to
    auto-approve (FR-301), plus the E-9 timer schedule. threshold is read
    only when policy == SOFT; the *_after_hours fields fall back to a
    fraction of PipelineConfig.gate_timeout_hours when None (see
    sdlc.notify.schedule.build_schedule)."""
    policy: GatePolicy = GatePolicy.HARD
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    on_timeout: TimeoutAction = TimeoutAction.REJECT
    remind_after_hours: int | None = Field(default=None, gt=0)
    escalate_after_hours: int | None = Field(default=None, gt=0)
```

Leave `_coerce` (line 46) untouched. Change only the `merge` entry in `PipelineConfig.gates` (line 688):

```python
        # E-9: a merge gate that expires would discard a run which passed
        # every absolute check. Holding keeps it pending and visible in the
        # E-8 inbox instead. Every other gate keeps today's reject.
        "merge": GateConfig(policy=GatePolicy.HARD,
                            on_timeout=TimeoutAction.HOLD),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gate_timeout_action.py -v`
Expected: 5 passed

- [ ] **Step 5: Verify nothing else regressed**

Run: `pytest tests/ -q -x -k "not temporal"`
Expected: no new failures. `GateConfig` is widely constructed; this confirms the added fields are all defaulted.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py tests/test_gate_timeout_action.py
git commit -m "feat(models): TimeoutAction + per-gate timer config (E-9)"
```

---

### Task 2: `build_schedule` — the pure timer schedule

**Files:**
- Create: `src/sdlc/notify/__init__.py`, `src/sdlc/notify/contract.py`, `src/sdlc/notify/schedule.py`
- Test: `tests/test_notify_schedule.py`

**Interfaces:**
- Consumes: `GateConfig`, `TimeoutAction` (Task 1).
- Produces:
  - `NotifyReason` enum: `OPENED="opened"`, `REMIND="remind"`, `ESCALATE="escalate"`, `EXPIRE="expire"`.
  - `build_schedule(gate_cfg: GateConfig, timeout_hours: int, opened_at: datetime) -> tuple[list[tuple[datetime, NotifyReason]], datetime | None]` — sorted deadlines, and the final deadline (`None` under `HOLD`). Task 7 calls this.

- [ ] **Step 1: Write the failing test**

Create `tests/test_notify_schedule.py`:

```python
"""E-9 Task 2: schedule construction is pure and total -- no configuration
may make it raise, hang, or emit an out-of-order deadline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sdlc.models import GateConfig, TimeoutAction
from sdlc.notify.schedule import NotifyReason, build_schedule

T0 = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _at(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


def test_default_schedule_is_opened_remind_50pct_escalate_80pct_expire():
    schedule, expires = build_schedule(GateConfig(), 48, T0)
    assert schedule == [
        (T0, NotifyReason.OPENED),
        (_at(24), NotifyReason.REMIND),      # 50% of 48
        (_at(38.4), NotifyReason.ESCALATE),  # 80% of 48
        (_at(48), NotifyReason.EXPIRE),
    ]
    assert expires == _at(48)


def test_explicit_overrides_win():
    cfg = GateConfig(remind_after_hours=2, escalate_after_hours=6)
    schedule, expires = build_schedule(cfg, 48, T0)
    assert [r for _, r in schedule] == [
        NotifyReason.OPENED, NotifyReason.REMIND,
        NotifyReason.ESCALATE, NotifyReason.EXPIRE,
    ]
    assert [t for t, _ in schedule] == [T0, _at(2), _at(6), _at(48)]
    assert expires == _at(48)


def test_hold_omits_expire_and_returns_no_final_deadline():
    cfg = GateConfig(on_timeout=TimeoutAction.HOLD)
    schedule, expires = build_schedule(cfg, 48, T0)
    assert [r for _, r in schedule] == [
        NotifyReason.OPENED, NotifyReason.REMIND, NotifyReason.ESCALATE,
    ]
    assert expires is None


def test_deadlines_at_or_past_expiry_are_dropped():
    """A reminder that would fire after the gate is already dead is noise."""
    cfg = GateConfig(remind_after_hours=48, escalate_after_hours=100)
    schedule, _ = build_schedule(cfg, 48, T0)
    assert [r for _, r in schedule] == [
        NotifyReason.OPENED, NotifyReason.EXPIRE]


def test_out_of_order_overrides_are_sorted_not_rejected():
    """escalate before remind is a misconfiguration, not a crash."""
    cfg = GateConfig(remind_after_hours=10, escalate_after_hours=3)
    schedule, _ = build_schedule(cfg, 48, T0)
    assert [t for t, _ in schedule] == [T0, _at(3), _at(10), _at(48)]


def test_zero_timeout_hours_yields_opened_then_immediate_expire():
    schedule, expires = build_schedule(GateConfig(), 0, T0)
    assert [r for _, r in schedule] == [
        NotifyReason.OPENED, NotifyReason.EXPIRE]
    assert expires == T0


def test_hold_with_zero_timeout_still_notifies_open_and_never_expires():
    cfg = GateConfig(on_timeout=TimeoutAction.HOLD)
    schedule, expires = build_schedule(cfg, 0, T0)
    assert [r for _, r in schedule] == [NotifyReason.OPENED]
    assert expires is None


def test_schedule_is_always_sorted_and_starts_at_opened():
    for timeout in (0, 1, 5, 48, 720):
        for cfg in (GateConfig(),
                    GateConfig(remind_after_hours=1),
                    GateConfig(on_timeout=TimeoutAction.HOLD),
                    GateConfig(remind_after_hours=99,
                               escalate_after_hours=1)):
            schedule, _ = build_schedule(cfg, timeout, T0)
            times = [t for t, _ in schedule]
            assert times == sorted(times), (cfg, timeout)
            assert schedule[0] == (T0, NotifyReason.OPENED)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_notify_schedule.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.notify'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/notify/__init__.py`:

```python
"""E-9 (FR-303): gate notifications, reminder timers, fallback escalation.

The workflow owns the timers; this package owns everything else -- what a
notification says, where it goes, and how it is delivered. All file I/O lives
in `activities.py`, because the workflow sandbox cannot read files (the same
split as harness containment).
"""
from .contract import DeliveryResult, NotifyInput, Notifier, NotifyReason
from .schedule import build_schedule

__all__ = [
    "DeliveryResult", "NotifyInput", "Notifier", "NotifyReason",
    "build_schedule",
]
```

Create `src/sdlc/notify/contract.py`:

```python
"""What a notification is, independent of how it is delivered."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from ..pending import PendingDecision


class NotifyReason(str, Enum):
    """Why this notification is being sent. Also selects the recipient tier:
    ESCALATE goes to primary AND fallback; everything else to primary."""
    OPENED = "opened"
    REMIND = "remind"
    ESCALATE = "escalate"
    EXPIRE = "expire"


class NotifyInput(BaseModel):
    """Workflow -> notify activity. Carries the pending decision itself so
    the activity can render it with E-6's default_render; no route is passed
    because route resolution reads a file the workflow cannot."""
    run_id: str
    pending: PendingDecision
    reason: NotifyReason
    opened_at: datetime
    now: datetime            # workflow.now() -- the activity reads no clock
    deadline: datetime | None = None


class DeliveryResult(BaseModel):
    """One delivery attempt. `notifier` is the adapter NAME only -- never the
    resolved target, which for a webhook is a bearer credential."""
    notifier: str
    delivered: bool
    error: str | None = None


class Results(BaseModel):
    """The notify activity's return value. A list is not used directly so the
    payload stays a named type across the Temporal boundary."""
    results: list[DeliveryResult] = Field(default_factory=list)


@runtime_checkable
class Notifier(Protocol):
    """A delivery transport. `target` is the route's suffix (a URL for
    webhook, None for log). Raising is allowed -- the activity catches and
    reports it as a failed delivery."""
    async def deliver(self, text: str, target: str | None) -> None: ...
```

Create `src/sdlc/notify/schedule.py`:

```python
"""When notifications fire. Pure: no I/O, no clock read -- `opened_at` is
supplied by the caller (workflow.now() in the workflow) so the schedule is
deterministic and replay-safe.

Totality is the design property that matters: no GateConfig may make this
raise, emit an unsorted schedule, or omit the OPENED entry. A misconfigured
schedule must never be able to hang or crash a gate.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..models import GateConfig, TimeoutAction
from .contract import NotifyReason

REMIND_FRACTION = 0.5     # of gate_timeout_hours, when not set explicitly
ESCALATE_FRACTION = 0.8

Schedule = list[tuple[datetime, NotifyReason]]


def build_schedule(gate_cfg: GateConfig, timeout_hours: int,
                   opened_at: datetime) -> tuple[Schedule, datetime | None]:
    """Return (sorted notification deadlines, final deadline).

    The final deadline is None under HOLD, which is what tells the caller
    that exhausting the schedule means "keep waiting" rather than "give up".
    Under any other TimeoutAction the schedule's last entry is EXPIRE at that
    same instant, so the two cannot disagree.
    """
    expires: datetime | None = (
        None if gate_cfg.on_timeout is TimeoutAction.HOLD
        else opened_at + timedelta(hours=timeout_hours))

    schedule: Schedule = [(opened_at, NotifyReason.OPENED)]

    for reason, explicit, fraction in (
        (NotifyReason.REMIND, gate_cfg.remind_after_hours, REMIND_FRACTION),
        (NotifyReason.ESCALATE, gate_cfg.escalate_after_hours,
         ESCALATE_FRACTION),
    ):
        hours = explicit if explicit is not None else timeout_hours * fraction
        at = opened_at + timedelta(hours=hours)
        if at <= opened_at:
            continue                      # collapses into OPENED
        if expires is not None and at >= expires:
            continue                      # would fire after the gate is dead
        schedule.append((at, reason))

    schedule.sort(key=lambda e: e[0])
    if expires is not None:
        schedule.append((expires, NotifyReason.EXPIRE))
    return schedule, expires
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_notify_schedule.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/notify/ tests/test_notify_schedule.py
git commit -m "feat(notify): pure build_schedule for gate timers (E-9)"
```

---

### Task 3: Notification text from `RenderedDecision`

**Files:**
- Create: `src/sdlc/notify/render.py`
- Test: `tests/test_notify_render.py`

**Interfaces:**
- Consumes: `default_render` (`channels/contract.py:50`), `NotifyReason` (Task 2).
- Produces: `render_notification(pending: PendingDecision, reason: NotifyReason, run_id: str, opened_at: datetime, now: datetime, deadline: datetime | None, base_url: str | None) -> str`. Task 6's activity calls this.

- [ ] **Step 1: Write the failing test**

Create `tests/test_notify_render.py`:

```python
"""E-9 Task 3: notification text. Reuses E-6's default_render -- this module
adds the envelope (why you are being told, when it expires, how to reply)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sdlc.models import CheckResult, GateClassification
from sdlc.notify.contract import NotifyReason
from sdlc.notify.render import render_notification
from sdlc.pending import ClarifyPending, MergeGatePending

T0 = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _merge_pending() -> MergeGatePending:
    return MergeGatePending(
        key="merge#1", gate="merge", round=1, verdict="ready to merge",
        checks=[
            CheckResult(name="security_no_critical", passed=True,
                        classification=GateClassification.ABSOLUTE,
                        detail=""),
            CheckResult(name="coverage", passed=False,
                        classification=GateClassification.ADVISORY,
                        detail="61%"),
        ])


def test_merge_notification_carries_check_table_and_cli_commands():
    text = render_notification(
        _merge_pending(), NotifyReason.OPENED, run_id="abc123",
        opened_at=T0, now=T0, deadline=T0 + timedelta(hours=48),
        base_url=None)
    assert "run abc123" in text
    assert "security_no_critical" in text
    assert "coverage" in text and "61%" in text
    assert "sdlc approve abc123 --gate merge" in text
    assert "sdlc reject abc123 --gate merge" in text


def test_clarify_notification_offers_the_answer_verb_not_gate_verbs():
    pending = ClarifyPending(key="q1", question="Which datastore?",
                             why_it_matters="Drives the schema.",
                             suggested_answer="postgres")
    text = render_notification(pending, NotifyReason.OPENED, run_id="abc123",
                               opened_at=T0, now=T0, deadline=None,
                               base_url=None)
    assert "sdlc answer abc123" in text
    assert "--gate" not in text
    assert "postgres" in text


def test_reason_is_stated_and_expiry_is_relative():
    text = render_notification(
        _merge_pending(), NotifyReason.REMIND, run_id="abc123", opened_at=T0,
        now=T0 + timedelta(hours=24), deadline=T0 + timedelta(hours=48),
        base_url=None)
    assert "reminder" in text.lower()
    assert "opened 24h ago" in text
    assert "expires in 24h" in text


def test_hold_gate_says_it_will_not_expire():
    text = render_notification(
        _merge_pending(), NotifyReason.OPENED, run_id="abc123", opened_at=T0,
        now=T0, deadline=None, base_url=None)
    assert "does not expire" in text
    assert "expires in" not in text


def test_expire_reason_reads_as_terminal():
    text = render_notification(
        _merge_pending(), NotifyReason.EXPIRE, run_id="abc123", opened_at=T0,
        now=T0 + timedelta(hours=48), deadline=T0 + timedelta(hours=48),
        base_url=None)
    assert "expired" in text.lower()


def test_base_url_adds_a_link_without_removing_the_commands():
    text = render_notification(
        _merge_pending(), NotifyReason.OPENED, run_id="abc123", opened_at=T0,
        now=T0, deadline=None, base_url="https://sdlc.example.com")
    assert "https://sdlc.example.com/runs/abc123" in text
    assert "sdlc approve abc123 --gate merge" in text


def test_text_is_ascii_only():
    """The Windows console cannot print non-ASCII (transport.py:11)."""
    text = render_notification(
        _merge_pending(), NotifyReason.ESCALATE, run_id="abc123",
        opened_at=T0, now=T0 + timedelta(hours=38),
        deadline=T0 + timedelta(hours=48), base_url=None)
    text.encode("ascii")     # raises UnicodeEncodeError on failure
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_notify_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.notify.render'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/notify/render.py`:

```python
"""Notification text. E-6's default_render already turns a PendingDecision
into title/body/rows; this module only adds the envelope -- why you are being
told now, when it dies, and the exact command that decides it.

ASCII-only, like every other operator-facing string in the project.
"""
from __future__ import annotations

from datetime import datetime

from ..channels.contract import default_render
from ..pending import PendingDecision
from .contract import NotifyReason

_LEAD = {
    NotifyReason.OPENED: "is awaiting you",
    NotifyReason.REMIND: "is still awaiting you (reminder)",
    NotifyReason.ESCALATE: "is still awaiting a decision (escalated)",
    NotifyReason.EXPIRE: "has expired undecided",
}


def _hours(delta) -> str:
    return f"{int(delta.total_seconds() // 3600)}h"


def render_notification(pending: PendingDecision, reason: NotifyReason,
                        run_id: str, opened_at: datetime, now: datetime,
                        deadline: datetime | None,
                        base_url: str | None) -> str:
    r = default_render(pending)
    gate = getattr(pending, "gate", None)
    subject = f"Gate '{gate}'" if gate else "A question"

    lines = [f"{subject} {_LEAD[reason]} on run {run_id}", "", r.title]
    if r.body:
        lines.append(r.body)

    timing = f"  opened {_hours(now - opened_at)} ago"
    if deadline is None:
        timing += " - does not expire"
    elif deadline > now:
        timing += f" - expires in {_hours(deadline - now)}"
    lines += ["", timing]

    if r.rows:
        lines.append("")
        width = max(len(name) for name, _ in r.rows)
        lines += [f"  {name:<{width}}  {detail}" for name, detail in r.rows]

    if r.suggested:
        lines += ["", f"  suggested: {r.suggested}"]

    lines.append("")
    if reason is not NotifyReason.EXPIRE:
        if gate:
            lines += [f"  sdlc approve {run_id} --gate {gate}",
                      f"  sdlc reject {run_id} --gate {gate}"]
        else:
            lines.append(f"  sdlc answer {run_id} --question {pending.key}")
        if base_url:
            lines.append(f"  {base_url.rstrip('/')}/runs/{run_id}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_notify_render.py -v`
Expected: 7 passed

If `CheckResult` / `GateClassification` import paths differ, run `grep -n "class CheckResult\|class GateClassification" src/sdlc/models.py` and fix the test's import — the production code is correct as written.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/notify/render.py tests/test_notify_render.py
git commit -m "feat(notify): ASCII notification text over E-6 default_render (E-9)"
```

---

### Task 4: Route asset and resolution

**Files:**
- Create: `src/sdlc/notify/routes.py`, `policy/notifications.yaml`
- Test: `tests/test_notify_routes.py`

**Interfaces:**
- Consumes: `NotifyReason` (Task 2).
- Produces:
  - `NotifyConfigError(Exception)`
  - `Route(BaseModel)` with `notifier: str`, `target: str | None`
  - `NotifyRoutes(BaseModel)` with `version: int`, `base_url: str | None`, `allow_hosts: list[str]`, and `routes_for(gate: str, reason: NotifyReason) -> list[Route]`
  - `load_routes(path=None) -> NotifyRoutes`
  - Env var `SDLC_NOTIFY_ROUTES` overrides discovery.

- [ ] **Step 1: Write the failing test**

Create `tests/test_notify_routes.py`:

```python
"""E-9 Task 4: routes as a versioned asset, mirroring policy/containment.yaml.
Unknown notifier names fail at LOAD, not at send -- a typo must not surface
for the first time during an expiring gate."""
from __future__ import annotations

import pytest

from sdlc.notify.contract import NotifyReason
from sdlc.notify.routes import NotifyConfigError, load_routes

ASSET = """
version: 1
base_url: null
allow_hosts: [hooks.slack.com]
default:
  primary: log
  fallback: log
gates:
  merge:
    primary: webhook:$MERGE_HOOK
    fallback: webhook:$ONCALL_HOOK
"""


def _write(tmp_path, text=ASSET):
    p = tmp_path / "notifications.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_non_escalate_reasons_go_to_primary_only(tmp_path, monkeypatch):
    monkeypatch.setenv("MERGE_HOOK", "https://hooks.slack.com/a")
    monkeypatch.setenv("ONCALL_HOOK", "https://hooks.slack.com/b")
    routes = load_routes(_write(tmp_path))
    for reason in (NotifyReason.OPENED, NotifyReason.REMIND,
                   NotifyReason.EXPIRE):
        got = routes.routes_for("merge", reason)
        assert [r.target for r in got] == ["https://hooks.slack.com/a"]


def test_escalate_adds_the_fallback_route(tmp_path, monkeypatch):
    monkeypatch.setenv("MERGE_HOOK", "https://hooks.slack.com/a")
    monkeypatch.setenv("ONCALL_HOOK", "https://hooks.slack.com/b")
    routes = load_routes(_write(tmp_path))
    got = routes.routes_for("merge", NotifyReason.ESCALATE)
    assert [r.target for r in got] == ["https://hooks.slack.com/a",
                                       "https://hooks.slack.com/b"]


def test_unlisted_gate_falls_back_to_default(tmp_path):
    routes = load_routes(_write(tmp_path))
    got = routes.routes_for("architecture", NotifyReason.OPENED)
    assert [(r.notifier, r.target) for r in got] == [("log", None)]


def test_unset_env_var_drops_the_route_rather_than_sending_a_literal(
        tmp_path, monkeypatch):
    """A literal '$MERGE_HOOK' POSTed to nowhere is worse than no route."""
    monkeypatch.delenv("MERGE_HOOK", raising=False)
    monkeypatch.setenv("ONCALL_HOOK", "https://hooks.slack.com/b")
    routes = load_routes(_write(tmp_path))
    got = routes.routes_for("merge", NotifyReason.OPENED)
    assert got == []


def test_unknown_notifier_name_fails_at_load(tmp_path):
    bad = ASSET.replace("primary: log", "primary: carrier_pigeon")
    with pytest.raises(NotifyConfigError, match="carrier_pigeon"):
        load_routes(_write(tmp_path, bad))


def test_unsupported_version_fails_at_load(tmp_path):
    with pytest.raises(NotifyConfigError, match="version"):
        load_routes(_write(tmp_path, ASSET.replace("version: 1", "version: 9")))


def test_missing_file_fails_closed(tmp_path):
    with pytest.raises(NotifyConfigError):
        load_routes(tmp_path / "nope.yaml")


def test_env_var_overrides_discovery(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_NOTIFY_ROUTES", str(_write(tmp_path)))
    assert load_routes().allow_hosts == ["hooks.slack.com"]


def test_shipped_asset_parses():
    """policy/notifications.yaml must always load -- it is the default."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert load_routes(root / "policy" / "notifications.yaml").version == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_notify_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.notify.routes'`

- [ ] **Step 3: Write minimal implementation**

Create `policy/notifications.yaml`:

```yaml
# E-9 (FR-303) -- where gate notifications go. Versioned asset, like
# policy/containment.yaml: a route change is a reviewable file diff.
#
# A route is "<notifier>" or "<notifier>:<target>". Targets beginning with $
# are read from the environment, so webhook URLs -- which are bearer
# credentials -- never enter the repository. An unset variable DROPS the
# route rather than sending to a literal "$NAME".
#
# `escalate` delivers to primary AND fallback. Every other reason goes to
# primary only. A fallback widens who is TOLD; it confers no authority --
# FR-302's first-decision-wins already settles who decides (E-60 owns
# identity).
version: 1

# Absolute base for deep links. Null until the dashboard (E-10) exists, at
# which point notifications gain a URL beside the CLI commands.
base_url: null

# Hosts a `webhook` route may POST to. A notify webhook is the pipeline's
# second outbound egress after research (FR-703), so it is allowlisted
# explicitly and fails closed. Subdomain matching follows the containment
# hook's rule (sdlc.harness.containment.host_allowed).
allow_hosts:
  - hooks.slack.com
  - discord.com

default:
  primary: log
  fallback: log

# Per-gate overrides. Example:
# gates:
#   merge:
#     primary: webhook:$SDLC_NOTIFY_WEBHOOK
#     fallback: webhook:$SDLC_NOTIFY_ONCALL_WEBHOOK
gates: {}
```

Create `src/sdlc/notify/routes.py`:

```python
"""Route resolution from policy/notifications.yaml.

Mirrors sdlc.harness.containment's loader deliberately: same discovery order
(explicit path -> env var -> walk up for the checkout markers), same
fail-closed stance, same "a structural problem raises at load" rule. A typo in
a notifier name must surface at boot, not for the first time while a gate is
expiring.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .contract import NotifyReason

ROUTES_PATH_ENV = "SDLC_NOTIFY_ROUTES"
_ROOT_MARKERS = ("pyproject.toml", "agents/registry.yaml")


class NotifyConfigError(Exception):
    """Any structural problem with the routes asset."""


class Route(BaseModel):
    notifier: str
    target: str | None = None


class NotifyRoutes(BaseModel):
    version: int
    base_url: str | None = None
    allow_hosts: list[str] = Field(default_factory=list)
    default: dict[str, Route] = Field(default_factory=dict)
    gates: dict[str, dict[str, Route]] = Field(default_factory=dict)

    def routes_for(self, gate: str, reason: NotifyReason) -> list[Route]:
        """Primary always; fallback additionally on ESCALATE. A tier whose
        route is absent (unset env var, not configured) is skipped."""
        table = self.gates.get(gate) or self.default
        tiers = (["primary", "fallback"]
                 if reason is NotifyReason.ESCALATE else ["primary"])
        return [table[t] for t in tiers if t in table]


def _discover() -> Path | None:
    for d in (Path.cwd(), *Path.cwd().parents):
        if all((d / m).is_file() for m in _ROOT_MARKERS):
            return d / "policy" / "notifications.yaml"
    return None


def _resolve_path(path: str | os.PathLike | None) -> Path:
    if path is not None:
        return Path(path)
    env = os.environ.get(ROUTES_PATH_ENV)
    if env:
        return Path(env)
    found = _discover()
    if found is not None:
        return found
    raise NotifyConfigError(
        f"cannot locate the notification routes asset. Tried: an explicit "
        f"path; ${ROUTES_PATH_ENV}; and walking up from {Path.cwd()} for a "
        f"directory containing {' and '.join(_ROOT_MARKERS)}.")


def _parse_route(raw: str, where: str) -> Route | None:
    """'log' -> Route(log); 'webhook:$X' -> Route(webhook, os.environ[X]).
    Returns None when an env-var target is unset: dropping the route beats
    POSTing to the literal string."""
    from .notifiers import NOTIFIERS       # local: avoids an import cycle

    notifier, _, target = raw.partition(":")
    notifier = notifier.strip()
    if notifier not in NOTIFIERS:
        raise NotifyConfigError(
            f"unknown notifier {notifier!r} at {where}; "
            f"known: {', '.join(sorted(NOTIFIERS))}")
    target = target.strip() or None
    if target and target.startswith("$"):
        target = os.environ.get(target[1:])
        if not target:
            return None
    return Route(notifier=notifier, target=target)


def _parse_table(raw: dict, where: str) -> dict[str, Route]:
    table: dict[str, Route] = {}
    for tier in ("primary", "fallback"):
        value = (raw or {}).get(tier)
        if value is None:
            continue
        if not isinstance(value, str):
            raise NotifyConfigError(
                f"{where}.{tier} must be a route string, got {type(value)}")
        route = _parse_route(value, f"{where}.{tier}")
        if route is not None:
            table[tier] = route
    return table


def load_routes(path: str | os.PathLike | None = None) -> NotifyRoutes:
    p = _resolve_path(path)
    if not p.is_file():
        raise NotifyConfigError(f"notification routes asset is not a file: {p}")

    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if raw.get("version") != 1:
        raise NotifyConfigError(
            f"unsupported notifications version {raw.get('version')!r} in {p}; "
            f"expected 1")

    return NotifyRoutes(
        version=1,
        base_url=raw.get("base_url"),
        allow_hosts=list(raw.get("allow_hosts") or []),
        default=_parse_table(raw.get("default") or {}, "default"),
        gates={g: _parse_table(t or {}, f"gates.{g}")
               for g, t in (raw.get("gates") or {}).items()},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_notify_routes.py -v`
Expected: 9 passed. (Task 5 creates `notifiers.NOTIFIERS`; if it does not exist yet, add a temporary `NOTIFIERS = {"log": None, "webhook": None}` in a new `src/sdlc/notify/notifiers.py` and let Task 5 replace it.)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/notify/routes.py policy/notifications.yaml tests/test_notify_routes.py
git commit -m "feat(notify): routes as a versioned asset (E-9)"
```

---

### Task 5: `LogNotifier`, `WebhookNotifier`, and the allowlist

**Files:**
- Create/replace: `src/sdlc/notify/notifiers.py`
- Modify: `src/sdlc/harness/containment.py:188` and its call site at `:220`
- Test: `tests/test_notify_notifiers.py`

**Interfaces:**
- Consumes: `Notifier` protocol (Task 2), `NotifyRoutes.allow_hosts` (Task 4).
- Produces: `NOTIFIERS: dict[str, Notifier]` with keys `"log"` and `"webhook"`; `LogNotifier`; `WebhookNotifier(allow_hosts: list[str])`; `EgressDenied(Exception)`. Also promotes `containment._host_allowed` to public `containment.host_allowed(host, allow_hosts) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_notify_notifiers.py`:

```python
"""E-9 Task 5: the two reference transports. The webhook is the pipeline's
second outbound egress after research (FR-703), so it fails closed on any
host not explicitly allowlisted."""
from __future__ import annotations

import logging

import pytest

from sdlc.notify.notifiers import (
    NOTIFIERS, EgressDenied, LogNotifier, WebhookNotifier,
)


def test_registry_ships_exactly_log_and_webhook():
    assert set(NOTIFIERS) == {"log", "webhook"}


@pytest.mark.asyncio
async def test_log_notifier_writes_the_text_and_never_raises(caplog):
    with caplog.at_level(logging.INFO):
        await LogNotifier().deliver("gate merge awaiting you", None)
    assert "gate merge awaiting you" in caplog.text


@pytest.mark.asyncio
async def test_webhook_posts_json_to_an_allowlisted_host(monkeypatch):
    sent = {}

    async def fake_post(url, payload):
        sent["url"], sent["payload"] = url, payload

    n = WebhookNotifier(allow_hosts=["hooks.slack.com"])
    monkeypatch.setattr(n, "_post", fake_post)
    await n.deliver("hello", "https://hooks.slack.com/services/T/B/X")
    assert sent["url"] == "https://hooks.slack.com/services/T/B/X"
    assert sent["payload"] == {"text": "hello"}


@pytest.mark.asyncio
async def test_webhook_accepts_a_subdomain_of_an_allowlisted_host(monkeypatch):
    n = WebhookNotifier(allow_hosts=["slack.com"])
    monkeypatch.setattr(n, "_post", lambda url, payload: _noop())
    await n.deliver("hello", "https://hooks.slack.com/x")


async def _noop():
    return None


@pytest.mark.asyncio
async def test_webhook_denies_a_non_allowlisted_host(monkeypatch):
    n = WebhookNotifier(allow_hosts=["hooks.slack.com"])
    monkeypatch.setattr(n, "_post", lambda url, payload: _noop())
    with pytest.raises(EgressDenied, match="evil.example.com"):
        await n.deliver("hello", "https://evil.example.com/x")


@pytest.mark.asyncio
async def test_webhook_denies_when_the_allowlist_is_empty():
    """Fail closed: no allowlist means no egress, not unrestricted egress."""
    with pytest.raises(EgressDenied):
        await WebhookNotifier(allow_hosts=[]).deliver(
            "hello", "https://hooks.slack.com/x")


@pytest.mark.asyncio
async def test_webhook_without_a_target_is_a_config_error():
    with pytest.raises(EgressDenied):
        await WebhookNotifier(allow_hosts=["hooks.slack.com"]).deliver(
            "hello", None)


def test_containment_host_matching_is_reused_not_reimplemented():
    """One implementation of the subdomain rule, shared with the pre_tool
    hook -- two would drift and a host would be allowed in one and denied
    in the other."""
    from sdlc.harness.containment import host_allowed
    assert host_allowed("hooks.slack.com", ["slack.com"])
    assert not host_allowed("notslack.com", ["slack.com"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_notify_notifiers.py -v`
Expected: FAIL with `ImportError: cannot import name 'EgressDenied'`

- [ ] **Step 3: Promote the containment matcher**

In `src/sdlc/harness/containment.py`, rename `_host_allowed` (line 188) to `host_allowed` and update its single call site at line 220:

```python
def host_allowed(host: str, allow_hosts: list[str]) -> bool:
    """Exact match or subdomain of an allowlisted host.

    Public because E-9's WebhookNotifier reuses it: two implementations of
    this rule would drift, and a host allowed for WebFetch but denied for a
    notification (or the reverse) is a policy hole.
    """
```

Run `grep -n "_host_allowed" src/sdlc/ -r` and confirm zero remaining references.

- [ ] **Step 4: Write minimal implementation**

Create `src/sdlc/notify/notifiers.py` (replacing any stub from Task 4):

```python
"""The two reference delivery transports, in a registry resolved by config --
the same shape as HARNESSES (ADR-2) and TOOLCHAINS (ADR-15).

`log` is the default: zero configuration, no egress, deterministic in CI.
`webhook` is a generic JSON POST that Slack and Discord accept as-is; anything
else is a receiving shim, not our substrate (NG7).
"""
from __future__ import annotations

import json
import logging
import urllib.request
from urllib.parse import urlparse

from ..harness.containment import host_allowed

log = logging.getLogger("sdlc.notify")

POST_TIMEOUT_S = 10


class EgressDenied(Exception):
    """A webhook route was refused before any bytes left the process."""


class LogNotifier:
    """Default transport. Never raises, needs no configuration, and makes the
    test suite deterministic without stubbing a URL."""

    async def deliver(self, text: str, target: str | None) -> None:
        log.info("notification:\n%s", text)


class WebhookNotifier:
    """Generic JSON POST. The host is checked against the notification
    allowlist BEFORE the request is built: a notify webhook is the pipeline's
    second outbound egress after research, and FR-703 is not yet closed at
    the network level, so this tier fails closed."""

    def __init__(self, allow_hosts: list[str] | None = None) -> None:
        self.allow_hosts = list(allow_hosts or [])

    async def deliver(self, text: str, target: str | None) -> None:
        if not target:
            raise EgressDenied("webhook route has no target URL")
        host = urlparse(target).hostname or ""
        if not host_allowed(host, self.allow_hosts):
            raise EgressDenied(
                f"host {host!r} is not in the notification allow_hosts "
                f"(policy/notifications.yaml)")
        await self._post(target, {"text": text})

    async def _post(self, url: str, payload: dict) -> None:
        import asyncio

        def _send() -> None:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=POST_TIMEOUT_S):
                pass

        await asyncio.to_thread(_send)


NOTIFIERS: dict[str, object] = {
    "log": LogNotifier(),
    "webhook": WebhookNotifier(),      # allow_hosts injected per-run (Task 6)
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_notify_notifiers.py tests/test_notify_routes.py -v`
Expected: all passed

- [ ] **Step 6: Verify containment still passes**

Run: `pytest tests/ -q -k "containment or hook"`
Expected: no failures — the rename is internal.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/notify/notifiers.py src/sdlc/harness/containment.py tests/test_notify_notifiers.py
git commit -m "feat(notify): log + webhook transports, allowlisted egress (E-9)"
```

---

### Task 6: The `notify` activity

**Files:**
- Create: `src/sdlc/notify/activities.py`
- Modify: `src/sdlc/worker.py`
- Test: `tests/test_notify_activity.py`

**Interfaces:**
- Consumes: `NotifyInput`, `Results`, `DeliveryResult` (Task 2); `render_notification` (Task 3); `load_routes` (Task 4); `NOTIFIERS`, `WebhookNotifier` (Task 5).
- Produces: `@activity.defn async def notify(inp: NotifyInput) -> Results`. Task 7's `_notify` calls it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_notify_activity.py`:

```python
"""E-9 Task 6: the activity. Every route is attempted; a raising transport
becomes a reported failure, never an exception that reaches the workflow."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sdlc.notify import activities as act
from sdlc.notify.contract import NotifyInput, NotifyReason
from sdlc.pending import ClarifyPending

T0 = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)

ASSET = """
version: 1
base_url: null
allow_hosts: [hooks.slack.com]
default:
  primary: log
  fallback: log
gates: {}
"""


@pytest.fixture
def routes(tmp_path, monkeypatch):
    p = tmp_path / "notifications.yaml"
    p.write_text(ASSET, encoding="utf-8")
    monkeypatch.setenv("SDLC_NOTIFY_ROUTES", str(p))
    return p


def _input(reason=NotifyReason.OPENED) -> NotifyInput:
    return NotifyInput(
        run_id="abc123",
        pending=ClarifyPending(key="q1", question="Which datastore?",
                               why_it_matters="Drives the schema."),
        reason=reason, opened_at=T0, now=T0,
        deadline=T0 + timedelta(hours=48))


@pytest.mark.asyncio
async def test_primary_only_for_opened(routes):
    out = await act.notify(_input())
    assert [r.notifier for r in out.results] == ["log"]
    assert all(r.delivered for r in out.results)


@pytest.mark.asyncio
async def test_escalate_delivers_to_primary_and_fallback(routes):
    out = await act.notify(_input(NotifyReason.ESCALATE))
    assert [r.notifier for r in out.results] == ["log", "log"]


@pytest.mark.asyncio
async def test_a_raising_transport_is_reported_not_propagated(routes,
                                                              monkeypatch):
    class Boom:
        async def deliver(self, text, target):
            raise RuntimeError("slack is down")

    monkeypatch.setitem(act.NOTIFIERS, "log", Boom())
    out = await act.notify(_input())
    assert out.results[0].delivered is False
    assert "slack is down" in out.results[0].error


@pytest.mark.asyncio
async def test_a_broken_routes_asset_is_reported_not_propagated(monkeypatch,
                                                                tmp_path):
    bad = tmp_path / "notifications.yaml"
    bad.write_text("version: 99\n", encoding="utf-8")
    monkeypatch.setenv("SDLC_NOTIFY_ROUTES", str(bad))
    out = await act.notify(_input())
    assert out.results == [] or all(not r.delivered for r in out.results)


@pytest.mark.asyncio
async def test_no_configured_route_yields_no_results(routes, monkeypatch):
    monkeypatch.setattr(act, "load_routes",
                        lambda: _routes_with_no_primary())
    out = await act.notify(_input())
    assert out.results == []


def _routes_with_no_primary():
    from sdlc.notify.routes import NotifyRoutes
    return NotifyRoutes(version=1, default={}, gates={})


@pytest.mark.asyncio
async def test_webhook_gets_the_allowlist_injected(routes, monkeypatch):
    """allow_hosts lives in the asset, so the transport must be built per
    call rather than used from the module-level registry."""
    seen = {}

    class Recorder:
        def __init__(self, allow_hosts=None):
            seen["allow_hosts"] = allow_hosts

        async def deliver(self, text, target):
            pass

    monkeypatch.setattr(act, "WebhookNotifier", Recorder)
    monkeypatch.setattr(act, "load_routes", lambda: _webhook_routes())
    await act.notify(_input())
    assert seen["allow_hosts"] == ["hooks.slack.com"]


def _webhook_routes():
    from sdlc.notify.routes import NotifyRoutes, Route
    return NotifyRoutes(
        version=1, allow_hosts=["hooks.slack.com"],
        default={"primary": Route(notifier="webhook",
                                  target="https://hooks.slack.com/x")},
        gates={})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_notify_activity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.notify.activities'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/notify/activities.py`:

```python
"""The notify activity -- everything the workflow sandbox cannot do.

Route resolution reads a YAML file and delivery opens a socket, so both live
here. The same split as harness containment: "flags travel; the YAML is
loaded activity-side."

This activity NEVER raises. A gate must remain decidable no matter what the
notification path does, so every failure becomes a DeliveryResult the
workflow can trace (spec 6) rather than an exception it must swallow blind.
"""
from __future__ import annotations

from temporalio import activity

from .contract import DeliveryResult, NotifyInput, Results
from .notifiers import NOTIFIERS, WebhookNotifier
from .render import render_notification
from .routes import load_routes


def _build(notifier_name: str, allow_hosts: list[str]):
    """Resolve a transport. `webhook` is constructed per call because its
    allowlist comes from the asset, not from module state."""
    if notifier_name == "webhook":
        return WebhookNotifier(allow_hosts=allow_hosts)
    return NOTIFIERS[notifier_name]


@activity.defn
async def notify(inp: NotifyInput) -> Results:
    try:
        routes = load_routes()
    except Exception as e:                # noqa: BLE001 - reported, not raised
        activity.logger.warning("notification routes unavailable: %s", e)
        return Results(results=[
            DeliveryResult(notifier="unresolved", delivered=False,
                           error=str(e)[:500])])

    gate = getattr(inp.pending, "gate", None) or ""
    text = render_notification(
        pending=inp.pending, reason=inp.reason, run_id=inp.run_id,
        opened_at=inp.opened_at, now=inp.now,
        deadline=inp.deadline, base_url=routes.base_url)

    out: list[DeliveryResult] = []
    for route in routes.routes_for(gate, inp.reason):
        try:
            transport = _build(route.notifier, routes.allow_hosts)
            await transport.deliver(text, route.target)
            out.append(DeliveryResult(notifier=route.notifier,
                                      delivered=True))
        except Exception as e:            # noqa: BLE001 - reported, not raised
            out.append(DeliveryResult(notifier=route.notifier,
                                      delivered=False, error=str(e)[:500]))
    return Results(results=out)
```

Register it in `src/sdlc/worker.py` — find the `activities=[...]` list and add `notify`, with the import `from .notify.activities import notify`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_notify_activity.py -v`
Expected: 6 passed

The activity reads no clock: `now` arrives on `NotifyInput` (set from `workflow.now()` in Task 7), which is what keeps the rendered "opened Nh ago" text deterministic across activity retries. The test's `_input()` helper must therefore pass `now=T0`.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/notify/activities.py src/sdlc/notify/contract.py src/sdlc/worker.py tests/test_notify_activity.py
git commit -m "feat(notify): notify activity, never raises (E-9)"
```

---

### Task 7: Wire the timers into `_gate`

**Files:**
- Modify: `src/sdlc/workflows/feature.py:78-120` (activity options), `:639-689` (`_gate`), plus a new `_notify` and `_wait_for_decision`
- Modify: `src/sdlc/observability/trace.py:15-26`
- Test: `tests/test_gate_notifications.py`

**Interfaces:**
- Consumes: `build_schedule`, `NotifyReason`, `NotifyInput`, `Results` (Tasks 2, 6).
- Produces: `RunEventKind.GATE_NOTIFIED`; `FeatureWorkflow._notify(...)`; `FeatureWorkflow._wait_for_decision(...)`. Task 8 changes the timeout branch this task leaves in place.

- [ ] **Step 1: Add the event kind**

In `src/sdlc/observability/trace.py`, add to `RunEventKind` after `GATE_DECIDED`:

```python
    GATE_NOTIFIED = "gate_notified"
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_gate_notifications.py`:

```python
"""E-9 Task 7: the timers fire in order, stop on the signal, and cannot
break the gate. Time-skipping so a 48h schedule runs in milliseconds."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from sdlc.activities import evaluate_gate
from sdlc.models import GateDecision, GateOutcome
from sdlc.notify.contract import DeliveryResult, NotifyInput, Results
from sdlc.observability.activities import export_run_artifacts
from tests.fakes.canned import AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea
from tests.fakes.fake_activities import GIT_FAKES

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

pytestmark = pytest.mark.temporal

TASK_QUEUE = "notify"
SENT: list[tuple[str, str]] = []       # (gate, reason)


@activity.defn(name="notify")
async def recording_notify(inp: NotifyInput) -> Results:
    SENT.append((getattr(inp.pending, "gate", None) or inp.pending.key,
                 inp.reason.value))
    return Results(results=[DeliveryResult(notifier="log", delivered=True)])


@activity.defn(name="notify")
async def exploding_notify(inp: NotifyInput) -> Results:
    raise RuntimeError("delivery subsystem is on fire")


def _activities(notify_act):
    return [evaluate_gate, export_run_artifacts, notify_act, *GIT_FAKES,
            *fake_agent_activities(AGENT_SPECS)]


async def _wait_for_status(handle, target, timeout_s=10.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r}")


@pytest.mark.asyncio
async def test_opened_notification_fires_and_signal_stops_the_rest(
        tmp_path, monkeypatch):
    """A gate decided promptly notifies once (opened) and never reminds."""
    SENT.clear()
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow],
                              activities=_activities(recording_notify),
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run, args=[greenfield_idea(), cfg],
                    id=f"notify-{uuid.uuid4()}", task_queue=TASK_QUEUE)

                async def drive():
                    await _wait_for_status(handle, "awaiting:clarify")
                    for qid in QUESTION_IDS:
                        await handle.signal(FeatureWorkflow.answer_question,
                                            args=[qid, "yes"])
                    for gate in ("architecture", "plan", "merge", "deploy"):
                        try:
                            await _wait_for_status(handle, f"awaiting:{gate}")
                        except AssertionError:
                            continue
                        await handle.signal(
                            FeatureWorkflow.submit_gate_decision,
                            GateDecision(gate=gate, round=1,
                                         outcome=GateOutcome.APPROVE,
                                         decided_by="human"))

                driver = asyncio.create_task(drive())
                result = await handle.result()
                await driver

    assert result.startswith("deployed:"), result
    reasons = {reason for _, reason in SENT}
    assert "opened" in reasons
    assert "remind" not in reasons and "expire" not in reasons


@pytest.mark.asyncio
async def test_exploding_notifier_leaves_every_gate_decidable(
        tmp_path, monkeypatch):
    """The load-bearing invariant: delivery cannot break a gate."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow],
                              activities=_activities(exploding_notify),
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run, args=[greenfield_idea(), cfg],
                    id=f"notify-boom-{uuid.uuid4()}", task_queue=TASK_QUEUE)

                async def drive():
                    await _wait_for_status(handle, "awaiting:clarify")
                    for qid in QUESTION_IDS:
                        await handle.signal(FeatureWorkflow.answer_question,
                                            args=[qid, "yes"])
                    for gate in ("architecture", "plan", "merge", "deploy"):
                        try:
                            await _wait_for_status(handle, f"awaiting:{gate}")
                        except AssertionError:
                            continue
                        await handle.signal(
                            FeatureWorkflow.submit_gate_decision,
                            GateDecision(gate=gate, round=1,
                                         outcome=GateOutcome.APPROVE,
                                         decided_by="human"))

                driver = asyncio.create_task(drive())
                result = await handle.result()
                await driver
                summary = await handle.query(FeatureWorkflow.run_summary)

    assert result.startswith("deployed:"), result
    assert summary is not None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_gate_notifications.py -v -m temporal`
Expected: FAIL — no `notify` activity is invoked, so `SENT` stays empty and `"opened" in reasons` fails.

- [ ] **Step 4: Write the implementation**

In `src/sdlc/workflows/feature.py`, add to the sandboxed import block (near line 59):

```python
    from ..notify.contract import NotifyInput, NotifyReason, Results
    from ..notify.schedule import build_schedule
    from ..notify.activities import notify
```

Add the activity options beside `MEM_ACT` (line 94):

```python
# E-9: delivery is best-effort and must never delay a gate. Same retry shape
# as MEM_ACT -- both are fire-and-forget side effects of a decision.
NOTIFY_ACT = dict(start_to_close_timeout=timedelta(seconds=30),
                  retry_policy=RetryPolicy(maximum_attempts=5))
```

Add the two methods to `FeatureWorkflow`, next to `_retain`:

```python
    async def _notify(self, pending, reason, opened_at, deadline) -> None:
        """Fire-and-forget delivery. Mirrors _retain: a transport failure can
        never block, fail, or delay a gate. Unlike _retain it does not swallow
        silently -- the outcome is traced, because a notification that failed
        to deliver must be visible (spec 6, ROADMAP 9.6)."""
        gate = getattr(pending, "gate", None) or pending.key
        try:
            out: Results = await workflow.execute_activity(
                notify,
                NotifyInput(run_id=workflow.info().workflow_id,
                            pending=pending, reason=reason,
                            opened_at=opened_at, now=workflow.now(),
                            deadline=deadline),
                **NOTIFY_ACT)
        except Exception as e:                # noqa: BLE001
            self._emit(RunEventKind.GATE_NOTIFIED, stage=gate, gate=gate,
                       reason=reason.value, notifier="unresolved",
                       delivered="false", error=str(e)[:200])
            return
        for r in out.results:
            self._emit(RunEventKind.GATE_NOTIFIED, stage=gate, gate=gate,
                       reason=reason.value, notifier=r.notifier,
                       delivered="true" if r.delivered else "false",
                       **({"error": r.error[:200]} if r.error else {}))

    async def _wait_for_decision(self, key, pending, schedule, expires):
        """Wait for the gate's signal, firing each notification as its
        deadline passes. Returns the decision, or None when the gate expired
        undecided. Exits the instant the signal lands, so there is nothing to
        cancel -- the reason this is a loop rather than a detached
        coroutine."""
        opened_at = schedule[0][0]
        decided = lambda: key in self._gate_decisions      # noqa: E731
        for at, reason in schedule:
            try:
                await workflow.wait_condition(
                    decided, timeout=at - workflow.now())
                return self._gate_decisions[key]
            except TimeoutError:
                await self._notify(pending, reason, opened_at, expires)
        if expires is None:                    # HOLD: wait without a deadline
            await workflow.wait_condition(decided)
            return self._gate_decisions[key]
        return None
```

Replace the wait inside `_gate` (lines 659-675). The timeout branch is unchanged in this task — Task 8 makes it honour `on_timeout`:

```python
            gate_cfg = cfg.gates.get(
                name, GateConfig(policy=default_policy or cfg.default_gate_policy))
            pending = gate_pending(name, round, context)
            self._pending[key] = pending
            self._status = f"awaiting:{name}"
            self._emit(RunEventKind.GATE_AWAITED, stage=name,
                       gate=name, round=str(round))
            schedule, expires = build_schedule(
                gate_cfg, cfg.gate_timeout_hours, workflow.now())
            try:
                decided = await self._wait_for_decision(
                    key, pending, schedule, expires)
                if decided is not None:
                    decision = decided
                else:
                    decision = GateDecision(gate=name, round=round,
                                            outcome=GateOutcome.REJECT,
                                            decided_by="timeout")
            finally:
                self._status = "running"
                self._pending.pop(key, None)
```

Note `policy` is already computed at line 646 from the same lookup; reuse `gate_cfg.policy` for it rather than looking the config up twice.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_gate_notifications.py -v -m temporal`
Expected: 2 passed

- [ ] **Step 6: Verify the existing suite is unchanged**

Run: `pytest tests/ -q`
Expected: no new failures. Existing gate tests supply no `notify` activity; the workflow's `execute_activity` will fail and be caught by `_notify`, which is exactly the invariant under test.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/workflows/feature.py src/sdlc/observability/trace.py src/sdlc/notify/ tests/test_gate_notifications.py
git commit -m "feat(workflow): deadline-walking gate wait with notifications (E-9)"
```

---

### Task 8: Honour `on_timeout`

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (`_gate`'s timeout branch, from Task 7)
- Test: `tests/test_gate_timeout_action.py` (extend)

**Interfaces:**
- Consumes: `TimeoutAction` (Task 1), `_wait_for_decision` (Task 7).
- Produces: no new symbols — `_gate` now maps expiry through `gate_cfg.on_timeout`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gate_timeout_action.py`:

```python
import asyncio
import uuid

import pytest
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from sdlc.activities import evaluate_gate
from sdlc.observability.activities import export_run_artifacts
from tests.fakes.canned import AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea
from tests.fakes.fake_activities import GIT_FAKES

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities


async def _wait_for_status(handle, target, timeout_s=10.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r}")


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_architecture_gate_timeout_still_rejects(tmp_path, monkeypatch):
    """Today's behaviour, preserved. Time-skipping runs the 48h in ms."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    cfg.gate_timeout_hours = 1
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue="timeout",
                          workflows=[FeatureWorkflow],
                          activities=[evaluate_gate, export_run_artifacts,
                                      *GIT_FAKES,
                                      *fake_agent_activities(AGENT_SPECS)],
                          plugins=[PydanticAIPlugin()]):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run, args=[greenfield_idea(), cfg],
                id=f"timeout-{uuid.uuid4()}", task_queue="timeout")
            with env.auto_time_skipping_disabled():
                await _wait_for_status(handle, "awaiting:clarify")
                for qid in QUESTION_IDS:
                    await handle.signal(FeatureWorkflow.answer_question,
                                        args=[qid, "yes"])
                await _wait_for_status(handle, "awaiting:architecture")
            result = await handle.result()
    assert "architecture" in result and result.startswith("rejected:"), result


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_hold_keeps_the_gate_pending_past_its_nominal_deadline(
        tmp_path, monkeypatch):
    """A HOLD gate outlives gate_timeout_hours and stays decidable."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    cfg.gate_timeout_hours = 1
    cfg.gates["architecture"] = GateConfig(policy=GatePolicy.HARD,
                                           on_timeout=TimeoutAction.HOLD)
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue="hold",
                          workflows=[FeatureWorkflow],
                          activities=[evaluate_gate, export_run_artifacts,
                                      *GIT_FAKES,
                                      *fake_agent_activities(AGENT_SPECS)],
                          plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run, args=[greenfield_idea(), cfg],
                    id=f"hold-{uuid.uuid4()}", task_queue="hold")
                with env.auto_time_skipping_disabled():
                    await _wait_for_status(handle, "awaiting:clarify")
                    for qid in QUESTION_IDS:
                        await handle.signal(FeatureWorkflow.answer_question,
                                            args=[qid, "yes"])
                    await _wait_for_status(handle, "awaiting:architecture")
                await env.sleep(7200)      # 2h -- twice the nominal timeout
                assert await handle.query(
                    FeatureWorkflow.pending_gate) == "awaiting:architecture"
                pending = await handle.query(FeatureWorkflow.pending_decisions)
                assert any(p["gate"] == "architecture" for p in pending)
                await handle.signal(
                    FeatureWorkflow.submit_gate_decision,
                    GateDecision(gate="architecture", round=1,
                                 outcome=GateOutcome.REJECT,
                                 decided_by="human"))
                result = await handle.result()
    assert result.startswith("rejected:"), result
```

Add the needed imports at the top of the file: `GateDecision`, `GateOutcome`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gate_timeout_action.py -v -m temporal`
Expected: the HOLD test FAILS — the gate rejects at 1h instead of staying pending.

- [ ] **Step 3: Write the implementation**

Replace the timeout branch written in Task 7 with:

```python
                decided = await self._wait_for_decision(
                    key, pending, schedule, expires)
                if decided is not None:
                    decision = decided
                else:
                    # Expired undecided. HOLD never reaches here -- its
                    # schedule has no final deadline, so _wait_for_decision
                    # waits without one.
                    decision = GateDecision(
                        gate=name, round=round, decided_by="timeout",
                        outcome=(GateOutcome.APPROVE
                                 if gate_cfg.on_timeout is TimeoutAction.APPROVE
                                 else GateOutcome.REJECT),
                        comments=f"no decision within "
                                 f"{cfg.gate_timeout_hours}h")
```

Add `TimeoutAction` to the sandboxed model imports at line 62.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gate_timeout_action.py -v`
Expected: all passed

- [ ] **Step 5: Run the full suite**

Run: `pytest tests/ -q`
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_gate_timeout_action.py
git commit -m "feat(workflow): gate expiry honours on_timeout (E-9)"
```

---

### Task 9: Full timer sequence under time-skipping, and docs

**Files:**
- Modify: `tests/test_gate_notifications.py` (add the sequence test)
- Modify: `ROADMAP.md` (mark E-9, update FR-303 and FR-601's siblings)
- Test: the sequence test is the deliverable

**Interfaces:**
- Consumes: everything above.
- Produces: no new symbols.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gate_notifications.py`:

```python
@pytest.mark.asyncio
async def test_full_timer_sequence_fires_in_order_then_expires(
        tmp_path, monkeypatch):
    """With no decision ever sent: opened -> remind (50%) -> escalate (80%)
    -> expire, in order, and the gate then rejects."""
    SENT.clear()
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    cfg.gate_timeout_hours = 10
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[FeatureWorkflow],
                          activities=_activities(recording_notify),
                          plugins=[PydanticAIPlugin()]):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run, args=[greenfield_idea(), cfg],
                id=f"seq-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            with env.auto_time_skipping_disabled():
                await _wait_for_status(handle, "awaiting:clarify")
                for qid in QUESTION_IDS:
                    await handle.signal(FeatureWorkflow.answer_question,
                                        args=[qid, "yes"])
                await _wait_for_status(handle, "awaiting:architecture")
            result = await handle.result()

    arch = [reason for gate, reason in SENT if gate == "architecture"]
    assert arch == ["opened", "remind", "escalate", "expire"], arch
    assert result.startswith("rejected:"), result
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `pytest tests/test_gate_notifications.py::test_full_timer_sequence_fires_in_order_then_expires -v -m temporal`
Expected: PASS if Tasks 7-8 are correct. If it fails on ordering, the bug is in `build_schedule`'s sort or in `_wait_for_decision` recomputing `at - workflow.now()` — both are covered by Task 2's unit tests, so re-run those first to localise.

- [ ] **Step 3: Update the roadmap**

In `ROADMAP.md`:
- §9.2: change E-9 to `- [x] **E-9** Notify activity + reminder timer + fallback approver (FR-303). *Landed:* `src/sdlc/notify/` (schedule + routes asset + log/webhook transports + activity), deadline-walking wait in `_gate`, `GATE_NOTIFIED` traced with delivery outcome. `on_timeout` per gate; `merge` holds rather than discarding a green run. Spec `docs/superpowers/specs/2026-07-26-gate-notifications-and-reminder-timers-design.md`, plan `docs/superpowers/plans/2026-07-26-gate-notifications-and-reminder-timers.md`.`
- §2 FR-303: change to `- [x] **FR-303** notifications + durable timers — notify activity (retried, `log`/`webhook` adapters), reminder + escalation + expiry timers, `on_timeout` per gate (E-9).`
- §0 P2: note that notifications have landed; dashboard backend and brownfield mode remain.

- [ ] **Step 4: Run the whole suite one final time**

Run: `pytest tests/ -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_gate_notifications.py ROADMAP.md
git commit -m "test(notify): full timer sequence under time-skipping; E-9 landed"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §0 what exists | — (context) |
| §1 fallback is routing, not authority | Task 4 (`routes_for` adds fallback on ESCALATE only) |
| §2 `TimeoutAction`, `GateConfig`, defaults | Task 1 |
| §3 `NOTIFIERS` registry, `log` + `webhook` | Task 5 |
| §3 routes asset, env indirection | Task 4 |
| §3 egress discipline | Task 5 (+ `containment.host_allowed` promotion) |
| §3 deep links, `base_url`, ASCII | Task 3 |
| §4 deadline-walking loop | Task 7 |
| §4 `build_schedule`, 50%/80%, degenerate configs | Task 2 |
| §4 rendering activity-side | Task 6 |
| §5 delivery cannot break a gate | Task 6 (activity never raises) + Task 7 (`_notify` catches) + Task 7's exploding-notifier test |
| §6 `GATE_NOTIFIED` with `delivered`/`error` | Task 7 |
| §7 test matrix | Tasks 1-9 |
| §8 out of scope | — |

**Known deviation from the spec, resolved here:** §3 says the webhook host is checked against "the same containment allowlist". Containment has no *global* allowlist — `allow_hosts` is a per-rule field (`containment.py:64`) on rules using the `HOST_NOT_ALLOWLISTED` predicate. The plan therefore reuses containment's **matching function** (promoted to `host_allowed`, one implementation of the subdomain rule) but sources the list from `policy/notifications.yaml`'s own `allow_hosts:`. Still explicit, still fail-closed on an empty list.

**Placeholder scan:** none. Every step carries runnable code or an exact command.

**Type consistency:** `NotifyInput` carries `now: datetime` from its definition in Task 2, is passed by the activity in Task 6, and is filled from `workflow.now()` in Task 7 — one shape across all three. `Results` (not a bare list) crosses the activity boundary in Tasks 6 and 7. `NotifyReason` values (`opened`/`remind`/`escalate`/`expire`) are identical in Tasks 2, 3, 4, 6, 7, 9. `host_allowed` is public from Task 5 onward and has no remaining `_host_allowed` references.
