# B4 — fleet back-pressure (STOP_IF)

**Date:** 2026-09-09
**Status:** design, pending user + reviewer sign-off
**Scope:** one row from the external-ideas register (`docs/reports/external-ideas-2026-09.md`, section B, B4). A new, small build: a fleet-wide cap on `FeatureWorkflow` runs currently awaiting a human decision, enforced at every path that starts a new one.
**Satisfies:** no FR moves. FR-303 covers a single open gate's notification/timeout behaviour; nothing in the PRD or `src/` caps the fleet's total pending-decision count today (confirmed: no `max_pending`/`backpressure`/`STOP_IF`/`fleet.*cap` hits anywhere in `src/`, `policy/`, `docs/ROADMAP.md`, `PRD.md`).
**Baseline:** `main` at `e94e2e0`.
**Does not cover:** in-workflow `FeatureWorkflow` child spawns (`tidyup.py`, `benchmarks/workflow.py`); `TriageWorkflow`/`TidyUpWorkflow`/`AssessmentWorkflow`'s own start paths; any change to `TimeoutAction`, `GateConfig`, or per-gate policy; any new fleet-level config file. See §7.

---

## 1. Problem

`FR-303` (`PRD.md:222-224`) governs one open gate: notifications, reminders, escalation-to-fallback, timeout policy — all scoped to a single run's single pending decision. Nothing aggregates across runs. A human reviewing a fleet of `FeatureWorkflow` runs today has no backstop against an unbounded number of them simultaneously waiting on a decision: `cli.py`'s `start` command, `operator/tools.py`'s `start_run` tool, and `dashboard/api.py`'s `POST /runs` route all call `client.start_workflow` (or the `starter` indirection over it) with no check of how many runs are already stalled on a human. Both sources named this independently (register row B4). The register's own framing is exact: "a cap on decisions pending human review across the fleet; new runs refuse to start while the queue is over the cap."

The data needed to answer "how many runs are pending a human right now" already exists and is already computed twice: `dashboard/fleet.py`'s `fetch_fleet` (feeding `FleetPoller`, itself feeding the E-10 dashboard) and `channels/inbox.py`'s `fetch_inbox` (feeding the CLI/operator cross-run inbox, FR-305's realization) both query every open run's `pending_decisions()` and aggregate. Neither is reused verbatim here — see §2 for why.

## 2. What "the fleet" means

**`FeatureWorkflow` runs only — a deliberate narrowing, not a double-counting fix.** `dashboard/fleet.py`'s `fetch_fleet` already scopes to `FeatureWorkflow` by default (`list_open_run_ids(client)` with no `types` argument, `fleet.py:105`).

An earlier draft of this section claimed reusing `channels/inbox.py`'s `fetch_inbox` (which additionally queries `CrewTaskWorkflow`, `inbox.py:110`) would double-count a stalled crew child against its parent run. That claim is wrong and worth recording as wrong: `GateHost.pending_decisions()` (`workflows/gates.py:118-121`) returns `list(self._pending.values())` — strictly the **querying host's own** pending dict. A `FeatureWorkflow` parent's query never includes its `CrewTaskWorkflow` child's pending items; each workflow type is queried independently and reports only its own load. `fetch_inbox` querying both types does not double anything.

The real effect of `FeatureWorkflow`-only scope is the opposite of double-counting: it **undercounts**. A `CrewTaskWorkflow` child stalled on a human gate is invisible to a cap that only ever looks at `FeatureWorkflow` runs — and `channels/inbox.py`'s own comment on why it includes crew children is exactly the load this cap is meant to catch: "a crew's gate is exactly what a human owes a decision on" (`inbox.py:86-88`). A fleet could sit at zero by this cap's count while several crew children wait on humans.

This spec keeps the narrower scope anyway, for three reasons, and names the undercount as an accepted gap rather than an oversight: (1) `dashboard/fleet.py`'s existing dashboard view — the thing an operator actually looks at — is already `FeatureWorkflow`-scoped, so the cap and the view it protects agree on what "the fleet" is; (2) refusing a *new* `FeatureWorkflow` start does not stop an *existing* crew child from opening more gates regardless of what this cap counts, so widening the count doesn't materially change what back-pressure buys until crew-spawning is itself gated (out of scope, see §7); (3) counting `CrewTaskWorkflow` correctly would require querying it as its own type alongside `FeatureWorkflow` (mirroring `inbox.py:110`) and deciding whether a parent run with a stalled child counts as one "pending run" or two for cap purposes — a real design question this spec is not answering. If the undercount proves to matter in practice, a follow-up can extend `pending_run_count` to also query `CrewTaskWorkflow` runs.

`TriageWorkflow`, `TidyUpWorkflow`, and `AssessmentWorkflow` are out of scope. They are not `FeatureWorkflow`, `cli.py`'s three other `start_workflow` calls (`:571`, `:615`, `:666`) start them directly, and they were not part of what B4's landing site names ("fleet level (dashboard / scheduler)" — the dashboard fleet view is `FeatureWorkflow`-only today; extending the cap to other workflow types is a bigger scope decision left for later if wanted).

## 3. The unit: runs, not items

The cap counts **runs with at least one pending decision**, not the sum of individual `PendingDecision` items across all runs. This matches FR-303's own framing (a gate holds *one run* pending) and `RunInbox`'s shape (`channels/inbox.py:17-21`: one entry per run, a list of items inside it). A run that opened three `ClarifyPending` questions at once is one human interaction to triage, not three. This is not universally true — wave mode runs dev tasks concurrently (`feature.py`'s `asyncio.gather`, per `GateHost._on_gate_decided`'s own docstring at `workflows/gates.py:82-89`: "a second gate opening while this one awaits a human"), so a single run's pending list can legitimately hold more than one item at once — but the choice of aggregation unit (runs, not items) holds regardless: a run juggling several open gates simultaneously is still one run's worth of human attention to reclaim, not several. "At most N runs waiting on a human" is the natural fleet-level generalization of FR-303's single-run hold either way.

## 4. Fail-closed on query errors — open runs only

`FleetSnapshot.errors` (`fleet.py:52`) is **not** exclusively open-run failures. `fetch_fleet` appends to the same `errors` list from two separate loops: the open-run loop (`fleet.py:116-119`, a failed `pending_decisions()`/`run_state` query) and the closed-run loop (`fleet.py:128-137`, a failed `run_summary()` query over up to `CLOSED_LIMIT=20` already-finished runs, `fleet.py:29`). A closed run owes a human nothing — it already finished — so an error fetching its retrospective summary is not a sign of unknown pending load; counting it toward the cap would let a flaky closed-run query (irrelevant to admission) block new starts.

The fail-closed reasoning from the design consultation applies only to the **open**-run half of `snap.errors`: an *open* run that failed to query is a run whose gate state is genuinely unknown, and that unknown must count as pending (not zero) for the same reason C8 named for a review lens that never ran — an absence must not read as an approval. A *closed* run's query failure carries no such ambiguity.

`FleetSnapshot` needs one small additive change to make this distinction available without re-deriving it: a second field, populated only by the open-run loop, alongside the existing `errors` (left as-is — the union of both, unchanged, since dashboard error-list rendering already reads it and should keep seeing everything):

```python
class FleetSnapshot(BaseModel):
    ...
    errors: list[InboxError] = Field(default_factory=list)  # unchanged: open + closed
    open_errors: list[InboxError] = Field(default_factory=list)  # NEW: open-run failures only
```

`fleet.py:118` appends to both `snap.errors` and `snap.open_errors`; `fleet.py:135` (the closed-run loop) appends only to `snap.errors`, as today. This keeps every existing `snap.errors` consumer (dashboard error rendering, existing tests asserting on `snap.errors`) unchanged, and gives the cap the one thing it actually needs:

```python
def pending_run_count(snap: FleetSnapshot) -> int:
    """Runs currently owed a human decision, or whose load is unknown --
    OPEN runs only. Unqueryable OPEN runs (snap.open_errors) count toward
    the cap: fail-closed, not fail-open, an unqueryable run's pending state
    is unknown, not zero. Unqueryable CLOSED runs (the rest of snap.errors)
    owe nothing and are excluded -- they already finished.
    """
    return len(snap.inbox) + len(snap.open_errors)
```

## 5. The check

New module-level additions to `src/sdlc/dashboard/fleet.py`, beside `fetch_fleet` (the module already imports no web framework, so it is safe for `cli.py` and `operator/tools.py` to import from) — plus the `open_errors` field added to `FleetSnapshot` and populated in `fetch_fleet`'s open-run loop, per §4. `check_fleet_capacity` and `pending_run_count` themselves remain pure functions over an already-fetched `FleetSnapshot` (no client, no I/O); §4's `FleetSnapshot`/`fetch_fleet` change is what makes the snapshot itself carry the distinction the pure function needs, not an exception to the purity claim.

```python
class FleetCapacityExceeded(RuntimeError):
    """Raised by check_fleet_capacity when the fleet is at or over its
    pending-decision cap. Carries cap/pending so a caller can render a
    message or an HTTP response without re-querying."""

    def __init__(self, cap: int, pending: int) -> None:
        super().__init__(
            f"fleet pending-decision cap reached: {pending} run(s) pending, cap is {cap}"
        )
        self.cap = cap
        self.pending = pending


def check_fleet_capacity(snap: FleetSnapshot, cap: int | None) -> None:
    """Raises FleetCapacityExceeded if snap's pending-run count is already
    at or over cap. cap=None means no cap configured -- always passes."""
    if cap is None:
        return
    pending = pending_run_count(snap)
    if pending >= cap:
        raise FleetCapacityExceeded(cap, pending)
```

`check_fleet_capacity` is a **pure function over an already-fetched `FleetSnapshot`**, not over a Temporal client or a `FleetPoller` — deliberately, so it unit-tests without any Temporal fixture and so each call site supplies a snapshot however is cheapest for it (see §6).

**Boundary: `>=`, not `>`.** Refusing only when `pending > cap` would let the steady-state count drift to `cap + 1`: an operator setting `SDLC_FLEET_PENDING_CAP=5` would observe six pending runs in practice (five already there, one more admitted before the sixth was noticed) and read it as a bug. `>=` makes the configured number mean what it says: at most `cap` runs pending *at the moment any admission decision is made*. It is not a live ceiling on the count at every instant — an admitted run can still open a gate afterward, and several runs admitted in quick succession before any of them reaches a gate can all open one later, so `pending` can rise above `cap` between admission checks. The cap throttles *new starts*, not concurrently-open gates already past admission.

## 6. Config and call sites

`SDLC_FLEET_PENDING_CAP`, an env var, parsed by one small shared helper (also in `fleet.py`):

```python
def fleet_pending_cap() -> int | None:
    """SDLC_FLEET_PENDING_CAP, parsed once per call site. Unset -> None (no
    cap, opt-in). Set but not an integer -> raises ValueError immediately:
    a misconfigured cap must fail loudly, not silently disable the check --
    the same fail-closed posture as §4."""
    raw = os.environ.get("SDLC_FLEET_PENDING_CAP")
    if raw is None:
        return None
    return int(raw)  # ValueError on garbage is the intended failure mode
```

Unset is the default (**no cap**, opt-in): a nonzero default would silently change every existing deployment's admission behaviour the moment this ships, the right number depends on human review capacity this repo cannot know in advance, and combined with §4's fail-closed error counting, a default cap could spuriously refuse starts purely from transient query flakiness on a fleet nobody has tuned it for yet.

Three call sites, each obtaining a `FleetSnapshot` the cheapest way available to it and then calling `check_fleet_capacity`:

- **`operator/tools.py`'s `start_run`** (`:502`) and **`dashboard/api.py`'s `POST /runs`** (`:173`) both already have a `FleetPoller` in scope (`OperatorDeps.poller`, `deps.py:25`; `create_router(poller, ...)`, `api.py:75`). Both call `await poller.snapshot()` — the poller's own cached-or-fan-out logic (`fleet.py:218-224`) means a busy dashboard pays no extra Temporal round trip beyond what it already does every 2s.
- **`cli.py`'s `start` command** (`:374-403`) has no poller (a one-shot CLI process has no subscriber to amortize a poll loop over) and calls `fetch_fleet(client, now=datetime.now(UTC))` directly — the free function `FleetPoller` itself wraps.

Each call site wraps its `start_workflow`/`starter` call with the cap check immediately before it, and translates `FleetCapacityExceeded` to its own surface's failure shape:

- **`cli.py`**: catches `FleetCapacityExceeded`, prints `f"fleet at capacity: {e.pending} run(s) pending, cap is {e.cap}"`, `raise SystemExit(1)`. Matches the existing `revise`-without-`--comment` pattern at `:363-365`.
- **`operator/tools.py`**: no per-call wrapping needed — `errors.py`'s `translate()` (`:25-47`) already funnels every non-`ToolError` exception through the `@guard` decorator already applied to `start_run`. Add one `elif isinstance(exc, FleetCapacityExceeded):` branch there: `msg = f"the fleet is at capacity ({exc.pending} run(s) pending human review, cap is {exc.cap}); ask the operator to clear some pending decisions before starting new work"`.
- **`dashboard/api.py`**: catches `FleetCapacityExceeded` in the `start` route (`:173-187`), before the existing generic `except Exception` fallback, and raises `HTTPException(429, str(e))` — 429 (Too Many Requests) is the correct status for "the server is refusing admission because a load threshold was reached," distinct from the existing 409 (`already started`) and 502 (Temporal call failed) branches already there.

## 7. Explicitly out of scope

- **In-workflow `FeatureWorkflow` child spawns.** `tidyup.py:228` starts one child `FeatureWorkflow` per accepted tidy-up finding; `benchmarks/workflow.py:269` starts one per benchmark cell. Both run via `workflow.execute_child_workflow` inside a parent workflow's deterministic sandbox, which has no Temporal client and cannot call a client-side helper like `check_fleet_capacity` without a new activity wrapping it. Both are also **bounded fan-out from an already-approved parent run** (a human already approved the tidy-up backlog or the benchmark suite), not open-ended intake — the kind of unattended admission burst B4 exists to stop is a human or an automated surface starting arbitrarily many *new, unrelated* runs, not a fixed-size fan-out a human already signed off on. If this judgment proves wrong (e.g. a large tidy-up backlog itself floods the human-review queue), a follow-up spec can wrap the check in an activity and call it from both sites — that is a real scope increase (new activity, retry semantics, two more call sites) deliberately deferred here.
- **`TriageWorkflow`/`TidyUpWorkflow`/`AssessmentWorkflow`'s own start paths.** Not `FeatureWorkflow`; see §2.
- **Any new fleet-level config file or `FleetConfig` model.** One env var and one parsing helper is proportionate to a single integer threshold; a config module/schema for one field is premature structure (Q4 in the design consultation rejected this explicitly).
- **Tuning `SDLC_FLEET_PENDING_CAP`'s value, or providing a default.** Left unset (no cap) until an operator has fleet data to size it from — see §6.
- **Any change to `TimeoutAction`, `GateConfig.on_timeout`, or FR-303's per-gate reminder/escalation machinery.** B4 adds a pre-admission check; it does not touch what happens to a gate once a run is already inside the pipeline.
- **A UI affordance surfacing the cap or current pending count in the dashboard.** `FleetSnapshot` already exposes everything a future dashboard panel would need (`pending_run_count(snap)`, §4); rendering it is a separate, small follow-up with no design questions of its own.

## 8. Contract text

There is no per-stage `.md` contract to extend here (`merge.md`-style contracts live under `stages/<name>/`; B4 lands at the fleet/admission layer, above any single stage). The contract instead lives as:

- `dashboard/fleet.py`'s module docstring gains a paragraph naming `check_fleet_capacity`/`FleetCapacityExceeded`/`fleet_pending_cap` and their fail-closed, opt-in, `>=`-boundary semantics (a condensed version of §3-§6 above) — the existing docstring already explains the module's other two invariants (why no database, why the poller is lazy) in the same style.
- Each of the three call sites gets a one-line comment at its check, naming which register row (B4) and pointing back to this spec — the existing convention this codebase already follows for E4, C3, C6 (see their code citations in `docs/reports/external-ideas-2026-09.md`).

## 9. Testing

All new pure-function tests land in `tests/test_dashboard_fleet.py` (existing file for this module):

- **`pending_run_count`**: empty snapshot → 0; `inbox` with 2 entries, no errors → 2; `inbox` empty, `open_errors` with 1 entry → 1; both populated → sum; **`errors` populated but `open_errors` empty → 0** (a closed-run-only error set must not count — this is the regression test for the Section 4 fix).
- **`fetch_fleet`'s new `open_errors` field**: an open run whose `pending_decisions()`/`run_state` query raises → appears in both `errors` and `open_errors`; a closed run whose `run_summary()` query raises → appears in `errors` only, not `open_errors`.
- **`check_fleet_capacity`**: `cap=None` never raises regardless of snapshot; `pending < cap` passes; `pending == cap` raises (boundary — confirms `>=` not `>`); `pending > cap` raises; raised `FleetCapacityExceeded` carries the exact `cap`/`pending` passed.
- **`fleet_pending_cap`**: unset env → `None`; `"5"` → `5`; `"abc"` → raises `ValueError` (monkeypatch `os.environ`).
- **Integration, one per call site** (new or extended test files as each site already has coverage):
  - `cli.py`'s `start`: a fetched snapshot at cap → `SystemExit(1)` with the capacity message printed, `start_workflow` never called.
  - `operator/tools.py`'s `start_run`: a `deps.poller.snapshot()` returning an at-cap snapshot → `ToolError` with the operator-facing message, `deps.starter` never called.
  - `dashboard/api.py`'s `POST /runs`: same setup → HTTP 429 with the capacity message in the body, `starter` never called.
- **No-cap regression**: with `SDLC_FLEET_PENDING_CAP` unset, all three call sites behave exactly as before this change (existing tests for `start`/`start_run`/`POST /runs` continue passing unmodified) — confirms opt-in is really opt-in.
