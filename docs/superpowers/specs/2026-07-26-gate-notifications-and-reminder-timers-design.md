# E-9 — gate notifications, reminder timers, fallback escalation (FR-303)

| | |
|---|---|
| Date | 2026-07-26 |
| Status | Approved design |
| Roadmap | E-9 — §9.2; §8 item 5 (Operability) |
| Anchors | FR-303 (notifications + durable timers), FR-301 (gate policy), FR-302 (idempotent signals), FR-704/NFR-4 (observability export), FR-703/NFR-5 (egress), US-4 (per-project gate config) |
| PRD | **No new FR.** FR-303 is the requirement; `GateConfig` gains the timeout clause US-4 already promises |
| ADR | No new ADR. Follows ADR-4 (gates as durable signal waits) and the adapter-registry pattern of ADR-2/ADR-15 |
| Builds on | E-6 (`channels/contract.py`), E-7 (`channels/transport.py`), E-8 (`channels/inbox.py`), E-22/E-32 (`observability/`) |
| Out of scope | Dashboard surface (**E-10**); MCP surface (**E-11**); identity/authz for approvers (**E-60**/FR-1004); network-level egress (**E-21**); per-user notification preferences |

## Problem

`_gate` (`feature.py:639`) opens a gate, marks it pending, emits `GATE_AWAITED`,
and then waits up to `cfg.gate_timeout_hours` (48, `models.py:722`) for a signal
that a human has no way of knowing is wanted:

```python
self._pending[key] = gate_pending(name, round, context)
self._status = f"awaiting:{name}"
self._emit(RunEventKind.GATE_AWAITED, stage=name, gate=name, round=str(round))
try:
    await workflow.wait_condition(
        lambda: key in self._gate_decisions,
        timeout=timedelta(hours=cfg.gate_timeout_hours),
    )
    decision = self._gate_decisions[key]
except TimeoutError:
    decision = GateDecision(gate=name, round=round,
                            outcome=GateOutcome.REJECT, decided_by="timeout")
```

Three defects, in ascending order of severity:

1. **Nobody is told the gate opened.** Discovery requires polling `sdlc inbox`.
2. **Nobody is warned before it expires.** The 48-hour deadline is invisible.
3. **Expiry rejects.** For `merge`, that discards a run which passed every
   deterministic check — including the absolute floors — because a human was
   away for two days. The work is gone and no message was ever sent about it.

ROADMAP records this as *"timeout→auto-reject only; no notify activity, no
reminder timer, no fallback-approver."* FR-303 is the closing requirement:

> Open gates SHALL push notifications (activity-based, retried) with deep
> links; durable timers SHALL drive reminder, escalation-to-fallback, and
> timeout policies.

## 0. What already exists

E-9 is small because E-6/E-7/E-8 did the hard half. It writes **no rendering
code and no signal-handling code**.

| Capability | Where | Status |
|---|---|---|
| Structured pending decisions | `pending.py`, `pending_decisions()` query | ✅ E-6 |
| Render → `title`/`body`/`rows`/`suggested` | `contract.py:50` `default_render` | ✅ E-6 |
| Reply → signal, first-wins per `(gate, round)` | `contract.py:76`, FR-302 | ✅ E-6/E-7 |
| Query/match/signal/verify transport | `channels/transport.py` | ✅ E-7 |
| Cross-run enumeration | `channels/inbox.py` | ✅ E-8 |
| `PushChannel.deliver` protocol | `contract.py:104` | ⚠️ **declared, no implementor** |
| Event trace → `events.jsonl` | `observability/` | ✅ E-22/E-32 |
| **Deliver to a human** | — | ❌ **E-9** |
| **Fire before/at expiry** | — | ❌ **E-9** |
| **Per-gate timeout semantics** | — | ❌ **E-9** |

`MergeGatePending.checks → RenderedDecision.rows` (`contract.py:69`) is already
the check table a merge notification needs. E-9 consumes it unchanged.

### Two structural gifts

- **FR-302 makes the fallback approver safe by construction.** Gate identity is
  `(gate, round)` and the first decision per round wins. Notifying a second
  recipient therefore needs no arbitration, no lock, and no precedence rule —
  primary and fallback race, and the race is already correct.
- **Timers are what Temporal is for.** A 48-hour wait spanning worker restarts
  is NFR-1's guarantee, not new machinery.

## 1. Constraint: a fallback changes who is *told*, not who *may decide*

There is no identity or authorization in the system. FR-1004/E-60 is unbuilt and
ROADMAP's own line is *"there is simply no principal to record."* `GateDecision`
carries `decided_by` as a `"human" | "policy" | "timeout"` **category**, not a
principal.

Modelling the fallback approver as a distinct *authority* would therefore
require inventing the identity system E-60 owns, inside a notification
increment. E-9 does not do this. **Recipients are opaque route strings.** The
fallback escalation widens delivery; authority stays exactly where FR-302 puts
it.

When E-60 lands, it fills `GateDecision` with a real principal and the routes
gain meaning as identities. Nothing here has to be unbuilt for that.

## 2. Models

```python
class TimeoutAction(str, Enum):
    REJECT  = "reject"    # today's behaviour — the default
    APPROVE = "approve"
    HOLD    = "hold"      # no final deadline; stays in the E-8 inbox


class GateConfig(BaseModel):
    """Per-gate policy, the SOFT confidence bar, and the timer schedule."""
    policy: GatePolicy = GatePolicy.HARD
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    on_timeout: TimeoutAction = TimeoutAction.REJECT
    remind_after_hours: int | None = None       # None -> derived (§4)
    escalate_after_hours: int | None = None     # None -> derived (§4)
```

`GateConfig._coerce` (`models.py:47`) is unchanged: a bare string or
`GatePolicy` still coerces to a default-timer `GateConfig`, so every existing
config keeps parsing and keeps its current behaviour.

### Defaults (`models.py:684`)

| Gate | policy | `on_timeout` | Why |
|---|---|---|---|
| `clarify` | HARD | `reject` | unchanged |
| `architecture` | HARD | `reject` | unchanged |
| `plan` | SOFT | `reject` | unchanged |
| `merge` | HARD | **`hold`** | never discard a run that passed its checks |
| `deploy` | HARD | `reject` | unchanged |
| *(unnamed, e.g. `task:<id>`, `budget`, `tool_approval`)* | `default_gate_policy` | `reject` | unchanged |

**Only `merge` changes behaviour.** Everything else is preserved exactly, so
E-9 is not a semantics change wearing a notification costume — it is a
notification feature plus one targeted correction, opt-in everywhere else via
US-4's existing per-project gate config.

`HOLD` is modelled as **the absence of a final deadline**, not a very large
timer. A 100-year timer is a lie that eventually fires; an absent deadline is
the truth being expressed. A held gate keeps `self._pending[key]` populated, so
it remains visible to `pending_decisions()`, the E-8 cross-run inbox, and the
CLI.

## 3. Notifier registry — `src/sdlc/notify/`

Structurally identical to `HARNESSES` (ADR-2) and `TOOLCHAINS` (ADR-15): an
interface, a registry, config-resolved, one reference implementation per
transport.

```python
NOTIFIERS: dict[str, Notifier] = {
    "log":     LogNotifier(),      # default; zero-config; deterministic
    "webhook": WebhookNotifier(),  # generic JSON POST (Slack/Discord-shaped)
}
```

- **`log`** — the default. Writes the rendered notification through the standard
  logging path. Requires no configuration, has no egress, and never fails, which
  makes CI and the test suite deterministic without stubbing a URL.
- **`webhook`** — generic JSON POST. Slack and Discord incoming webhooks accept
  it as-is; anything else is a receiving shim, not our problem (NG7's stance:
  adapters over what the customer already runs, no substrate of our own).

### Routes as a versioned asset

`policy/notifications.yaml`, beside the existing `policy/containment.yaml`:

```yaml
version: 1
default:
  primary:  log
  fallback: log
gates:
  merge:
    primary:  webhook:$SDLC_NOTIFY_WEBHOOK
    fallback: webhook:$SDLC_NOTIFY_ONCALL_WEBHOOK
base_url: null    # deep links are CLI commands until E-10 lands
```

A route is `<notifier>` or `<notifier>:<target>`. Env-var indirection keeps
webhook URLs — which are bearer credentials — out of the repository.

### Egress discipline

**A notify webhook is the pipeline's second outbound egress, after the research
stage.** FR-703 records egress as env-allowlist + tool-level only, with E-18/E-21
open. E-9 must not quietly open a second unpoliced hole, so `WebhookNotifier`
resolves its host against **the same containment allowlist** the `pre_tool` hook
uses (`policy/containment.yaml`). A webhook to a non-allowlisted host fails
closed and is reported as a delivery failure (§6) — it does not silently send
and it does not break the gate.

This does not close E-18: a socket opened inside an allowed call is still
invisible. It only ensures E-9 adds nothing new to that gap.

### Deep links

Until E-10 exists, the honest deep link is the command that actually decides the
gate:

```
Gate 'merge' is awaiting you on run abc123
  round 1 - opened 24h ago, expires in 24h

  build_integration_green  ok
  security_no_critical     ok
  coverage                 FAIL [advisory] 61%

  sdlc approve abc123 --gate merge
  sdlc reject  abc123 --gate merge
```

When `base_url` is configured, a URL line is added. `sdlc approve` already
derives the round from the pending item (E-7), so the command needs no `--round`
and cannot land on a superseded round.

All notification text is **ASCII-only**, matching `transport.py`'s existing
constraint (the Windows console cannot print non-ASCII).

## 4. The wait — a deadline-walking loop

`_gate` swaps its single `wait_condition` for a helper that walks a sorted
schedule:

```python
async def _wait_for_decision(self, key, pending, schedule, expires):
    """Wait for the gate's signal, firing each notification as its deadline
    passes.

    `schedule` is the sorted notification deadlines; `expires` is the final
    deadline, or None for HOLD. Returns the decision, or None when the run
    expired undecided (-> on_timeout). Exits the instant the signal lands,
    so there is nothing to cancel.
    """
    decided = lambda: key in self._gate_decisions
    for at, reason in schedule:
        try:
            await workflow.wait_condition(decided, timeout=at - workflow.now())
            return self._gate_decisions[key]
        except TimeoutError:
            await self._notify(pending, reason, deadline=at)

    if expires is None:                 # HOLD: wait without a deadline
        await workflow.wait_condition(decided)
        return self._gate_decisions[key]
    return None                         # expired undecided
```

Under a non-`HOLD` config the last schedule entry is `(expire_at, "expire")`,
whose notification announces that the gate expired, and `expires` mirrors that
same timestamp so the loop knows exhaustion means *give up* rather than *keep
waiting*. Under `HOLD` both are absent, and the loop falls through to the
unbounded wait. The two are built together by `build_schedule`, so they cannot
disagree.

### Schedule construction (pure, unit-testable)

```python
def build_schedule(cfg, gate, opened_at) -> tuple[
    list[tuple[datetime, NotifyReason]],   # sorted notification deadlines
    datetime | None,                       # final deadline; None under HOLD
]: ...
```

| Reason | Default deadline |
|---|---|
| `opened` | immediately, at `opened_at` |
| `remind` | `remind_after_hours`, else **50%** of `gate_timeout_hours` |
| `escalate` | `escalate_after_hours`, else **80%** of `gate_timeout_hours` |
| `expire` | `gate_timeout_hours`; **omitted entirely when `on_timeout == HOLD`** |

Degenerate configurations are normalised rather than rejected: deadlines are
sorted, non-positive intervals collapse to fire immediately, and any deadline at
or beyond the final one is dropped. A misconfigured schedule must never be able
to hang or crash a gate.

### Why this shape

- Every timer is a **workflow timer**, so replay-safety is free and the whole
  thing runs under Temporal's time-skipping test environment without waiting 48
  hours.
- The loop **exits on the signal**, so no cancellation logic exists to leak — the
  failure mode a detached notifier coroutine would have introduced on every
  REVISE round and every workflow failure path.
- Replay does not double-send: timers and activity results are both recorded in
  history.

### Rendering happens activity-side

The workflow passes `PendingDecision` + reason + deadline to the `notify`
activity; the activity calls `default_render` and the resolved notifier. Route
resolution reads `policy/notifications.yaml`, which the workflow sandbox cannot
do — the same split, for the same reason, as containment's *"flags travel; the
YAML is loaded activity-side."*

## 5. Delivery must not be able to break a gate

`_notify` mirrors `_retain` (`feature.py:396`) exactly:

```python
async def _notify(self, pending, reason, deadline) -> None:
    try:
        await workflow.execute_activity(notify, NotifyInput(...), **NOTIFY_ACT)
    except Exception:
        pass
```

A Slack outage, an expired webhook, a DNS failure, or a non-allowlisted host
**cannot block, fail, delay, or alter a gate.** Retries live in `NOTIFY_ACT`'s
`RetryPolicy`, matching `MEM_ACT`. This is the invariant §7 tests directly.

## 6. The failure mode we must not reproduce

ROADMAP §9.6 is a warning aimed precisely at this increment. Independent reviews
of `vercel/eve` converge on observability as its weak point — *"silent delivery
failures with no diagnostic — no 404, no failed-delivery banner — silence."*
Adding fire-and-forget delivery (§5) is exactly how a system acquires that
defect. §9.7's ordering makes the same point: land `events.jsonl` **before** the
surfaces multiply the ways delivery can fail silently.

So delivery outcomes are traced. A new `RunEventKind.GATE_NOTIFIED` carries:

| field | meaning |
|---|---|
| `gate`, `round` | which gate |
| `reason` | `opened` \| `remind` \| `escalate` \| `expire` |
| `route` | resolved route name (**never the resolved URL** — it is a credential) |
| `delivered` | `true` \| `false` |
| `error` | failure detail when `delivered=false` |

**A notification that failed to deliver is itself observable**, in
`events.jsonl` and `report.html`. Without this, E-9 would fix one silence by
manufacturing another — an operator would believe they were being notified while
every POST 404'd.

`decided_by="timeout"` already exists in `GateOutcomeSummary` (`models.py:788`),
so the retro/SC-6 calibration signal needs no change. `HOLD` simply means it is
no longer emitted for `merge`.

## 7. Testing

| Test | Asserts |
|---|---|
| `build_schedule` unit tests | default 50%/80% derivation; explicit overrides; `HOLD` omits `expire`; degenerate configs (`remind_after > timeout`, zero, negative) normalise rather than raise |
| Time-skipping timer test | with no signal, `opened`/`remind`/`escalate`/`expire` fire in order at the right virtual times |
| Signal-arrives test | a decision at any point stops all further notifications; the loop exits without firing the rest |
| One test per `TimeoutAction` | `REJECT` → today's `GateDecision(decided_by="timeout")`; `APPROVE` → approving decision; `HOLD` → still pending, still in `pending_decisions()`, decidable afterwards |
| **Raising-notifier test** | a notifier that raises on every call leaves the gate fully decidable — §5's invariant |
| Recording fake notifier | reason, order, and rendered content, including the merge check table |
| Egress test | a webhook to a non-allowlisted host fails closed and is reported as `delivered=false` |
| Route resolution | env-var indirection; unknown notifier name fails at load, not at send |

The fake notifier is registered into `NOTIFIERS` the way `tests/fakes/` already
substitutes harness and activity doubles.

## 8. Out of scope

- **The dashboard and MCP surfaces** (E-10/E-11). E-9 delivers a notification;
  it does not build a place to land. `base_url` is the seam that upgrades the
  deep link when E-10 arrives.
- **Identity and authorization** (E-60/FR-1004) — §1.
- **Network-level egress** (E-21). E-9 reuses the existing tool-level allowlist
  and adds nothing to the gap.
- **Per-user notification preferences, digests, quiet hours.** YAGNI: one
  operator, two routes.
- **Notifying on anything but gates.** Stage completion, run finish, and budget
  crossings are already traced; pushing them is a separate decision about noise.

## 9. Open questions

- **OQ-E9-1 — reminder repetition.** FR-303 says "reminder" singular and this
  design fires one. A gate held open for a week (now possible for `merge` under
  `HOLD`) notifies four times and then goes quiet. A decaying repeat is the
  obvious follow-on; it is deliberately not built until a held gate has been
  observed in practice.
- **OQ-E9-2 — `HOLD` and fleet accounting.** A held `merge` gate keeps a run
  open indefinitely. That is the intent, but SC-1 ("runs reaching merge gate
  unattended") and the E-36 heatmap both aggregate over runs; whether a held run
  counts as in-flight or parked is a measurement question for the benchmark, not
  a workflow question. Flagged, not answered here.
