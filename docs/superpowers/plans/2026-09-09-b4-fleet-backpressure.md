# B4 — Fleet Back-Pressure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cap the number of `FeatureWorkflow` runs simultaneously awaiting a human decision, and make every client-side path that starts a new run refuse admission while the fleet is at that cap.

**Architecture:** `dashboard/fleet.py` gains a pure counting function over the `FleetSnapshot` it already produces, a raising capacity check, an env-var cap parser, and one thin async client-side guard that composes all three. Three call sites — the `start` CLI command, the operator `start_run` tool, and the dashboard's `POST /runs` route — call the check immediately before starting a workflow and translate the refusal into their own surface's failure shape (exit code, `ToolError`, HTTP 429). The cap is opt-in: unset `SDLC_FLEET_PENDING_CAP` means no cap and byte-for-byte today's behaviour.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, pytest, pytest-asyncio. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-09-b4-fleet-backpressure-design.md`

## Global Constraints

- The cap counts **runs**, never individual `PendingDecision` items. A run with three open questions counts once.
- Only **open** runs count. `FleetSnapshot.errors` mixes open-run and closed-run query failures; only the open-run half (`open_errors`) may reach the count. A closed run owes nothing.
- Unqueryable **open** runs count toward the cap (**fail-closed**). Do not silently exclude them.
- `SDLC_FLEET_PENDING_CAP` unset means **no cap**. Never introduce a nonzero default.
- **Read the cap before fetching anything.** Every call site must call `fleet_pending_cap()` first and skip the snapshot entirely when it returns `None`. Never write `check_fleet_capacity(await <fetch>, fleet_pending_cap())` — Python evaluates arguments left to right, so the fetch would run even with no cap configured, making an un-opted-in deployment pay a fan-out per start and newly fail when Temporal visibility is degraded.
- The boundary is `>=`, never `>`: refuse when the count is already *at* the cap.
- Scope is `FeatureWorkflow` only. Do not add `CrewTaskWorkflow`, `TriageWorkflow`, `TidyUpWorkflow`, or `AssessmentWorkflow` to any query in this plan.
- Do not touch `tidyup.py` or `benchmarks/workflow.py`. Their in-workflow child `FeatureWorkflow` spawns are explicitly out of scope (spec §7).
- `FleetSnapshot.errors` keeps its current meaning (open + closed, the union). Existing consumers must not change behaviour.
- No new fleet config file, module, or `FleetConfig` model. One env var, one parser.
- No attribution trailers in any commit. Commit via `git commit -F <msgfile>`, one path per `git add` argument, no heredocs.

---

## Start-site audit (done — do not re-derive)

The spec's three call sites were verified against `src/` before this plan was written. `grep -rn "FeatureWorkflow.run" src/ --include=*.py` returns exactly four hits, and this is the full census of ways a `FeatureWorkflow` begins:

| Site | What it is | In this plan? |
|---|---|---|
| `src/sdlc/cli.py:388` | the `start` command's `client.start_workflow(FeatureWorkflow.run, ...)` | **yes** — Task 3 |
| `src/sdlc/cli.py:698` | `get_workflow_handle_for(FeatureWorkflow.run, args.id)` — a *read* on an existing run, not a start | no |
| `src/sdlc/workflows/tidyup.py:229` | in-workflow `execute_child_workflow`, one per accepted finding | no — spec §7 |
| `src/sdlc/benchmarks/workflow.py:270` | in-workflow `execute_child_workflow`, one per benchmark cell | no — spec §7 |

Plus the two `starter`-indirected client-side paths, which reach `FeatureWorkflow` through an injected callable rather than a literal: `src/sdlc/operator/tools.py:530` (`await deps.starter(...)`, Task 4) and `src/sdlc/dashboard/api.py:180` (`await start_run(...)`, Task 5).

`cli.py`'s other three `start_workflow` calls start **other** workflow types and are correctly untouched: `:571` `TriageWorkflow`, `:615` `TidyUpWorkflow`, `:666` `AssessmentWorkflow`. `src/sdlc/benchmarks/cli.py:211` starts `BenchmarkWorkflow`, also untouched.

---

## File Map

- Modify `src/sdlc/dashboard/fleet.py` — Task 1 adds the `open_errors` field to `FleetSnapshot` and populates it in `fetch_fleet`'s open-run loop; Task 2 adds `pending_run_count`, `FleetCapacityExceeded`, `check_fleet_capacity`, `fleet_pending_cap`, and `guard_fleet_capacity`; Task 6 extends the module docstring.
- Modify `src/sdlc/cli.py` — Task 3: one `await guard_fleet_capacity(client)` call plus its `except FleetCapacityExceeded` handler in the `start` branch.
- Modify `src/sdlc/operator/tools.py` — Task 4: one capacity check in `start_run` before `deps.starter(...)`.
- Modify `src/sdlc/operator/errors.py` — Task 4: one `translate()` branch mapping `FleetCapacityExceeded` to an operator-readable `ToolError`.
- Modify `src/sdlc/dashboard/api.py` — Task 5: capacity check in the `POST /runs` route plus a 429 handler.
- Modify `.env.example` — Task 6: document `SDLC_FLEET_PENDING_CAP` under the existing "Tunables (optional)" section.
- Modify `tests/test_dashboard_fleet.py` — Tasks 1 and 2: `open_errors` population tests, and every pure-function test for the new helpers.
- Create `tests/test_fleet_capacity_wiring.py` — Task 3: the CLI wiring's source-needle test.
- Modify `tests/test_operator_writes.py` — Task 4: add `snapshot()` to the existing `FakePoller` (it has none today), plus three tests (refusal at cap, admission below cap, and no fleet read when uncapped).
- Modify `tests/test_dashboard_api.py` — Task 5: three route tests (429 at cap, 200 below cap, and no fleet read when uncapped).

---

### Task 1: `FleetSnapshot` distinguishes open-run from closed-run query failures

**Files:**
- Modify: `src/sdlc/dashboard/fleet.py:43-52` (`FleetSnapshot`), `src/sdlc/dashboard/fleet.py:116-119` (open-run loop)
- Test: `tests/test_dashboard_fleet.py` (add two tests)

**Interfaces:**
- Consumes: `InboxError` (existing, `src/sdlc/channels/inbox.py:24` — fields `run_id: str`, `error: str`). Unchanged by this task; the shared type is deliberately not modified, because `channels/inbox.py`'s own `Inbox` has no closed-run pass and so has no use for an open/closed flag.
- Produces: `FleetSnapshot.open_errors: list[InboxError]` — open-run query failures only. Task 2's `pending_run_count` reads it.

**Context for the implementer:** `fetch_fleet` (`fleet.py:103-138`) runs two loops that both append to the *same* `snap.errors` list. The first (`:116-119`) covers open runs: its `_fetch_open` helper gathers `run_state` and `pending_decisions`, and returns the exception itself on failure. The second (`:128-137`) covers up to `CLOSED_LIMIT = 20` recently-**closed** runs (`fleet.py:29`) and fails when `run_summary` raises. A closed run cannot owe a human a decision, so its query failure must not consume a cap slot — that is the defect this task fixes at the source, before anything counts.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_fleet.py`. The `_Client`, `_Handle`, `_state`, and `_summary` helpers at the top of that file are already exactly what these need — `_Client(open_handles, closed_handles)` yields the closed ids for any query containing `"!="`, which is how `_CLOSED_QUERY` is shaped.

```python
@pytest.mark.asyncio
async def test_an_open_run_query_failure_lands_in_both_errors_and_open_errors():
    client = _Client(
        {
            "run-a": _Handle(state=_state("run-a"), pending=[Q1]),
            "run-bad": _Handle(error=RuntimeError("query timeout")),
        }
    )
    snap = await fetch_fleet(client, now=AT)
    assert [e.run_id for e in snap.errors] == ["run-bad"]
    assert [e.run_id for e in snap.open_errors] == ["run-bad"]


@pytest.mark.asyncio
async def test_a_closed_run_query_failure_stays_out_of_open_errors():
    """B4: a closed run owes no human a decision, so its failed run_summary
    query must never consume a fleet cap slot -- it belongs in errors (which
    the dashboard renders) but not in open_errors (which the cap counts)."""
    client = _Client(
        {"run-a": _Handle(state=_state("run-a"), pending=[])},
        {"run-done": _Handle(error=RuntimeError("summary unavailable"))},
    )
    snap = await fetch_fleet(client, now=AT)
    assert [e.run_id for e in snap.errors] == ["run-done"]
    assert snap.open_errors == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard_fleet.py -k open_errors -v`
Expected: FAIL — `AttributeError: 'FleetSnapshot' object has no attribute 'open_errors'`. (`FleetSnapshot` does not set `extra="forbid"`, but these tests read the attribute rather than passing it to the constructor, so both fail at the attribute access.)

- [ ] **Step 3: Add the field and populate it**

In `src/sdlc/dashboard/fleet.py`, change `FleetSnapshot` (currently lines 43-52) from:

```python
class FleetSnapshot(BaseModel):
    """One fan-out's result. Everything the dashboard serves derives from
    this -- both REST reads and every SSE event."""

    at: datetime
    total_open_runs: int = 0
    runs: list[RunState] = Field(default_factory=list)
    closed: list[RunSummary] = Field(default_factory=list)
    inbox: list[RunInbox] = Field(default_factory=list)
    errors: list[InboxError] = Field(default_factory=list)
```

to:

```python
class FleetSnapshot(BaseModel):
    """One fan-out's result. Everything the dashboard serves derives from
    this -- both REST reads and every SSE event."""

    at: datetime
    total_open_runs: int = 0
    runs: list[RunState] = Field(default_factory=list)
    closed: list[RunSummary] = Field(default_factory=list)
    inbox: list[RunInbox] = Field(default_factory=list)
    errors: list[InboxError] = Field(default_factory=list)
    # B4: the OPEN-run subset of `errors`. `errors` mixes both passes below --
    # a failed pending_decisions query on a live run, and a failed run_summary
    # on an already-closed one. Only the first kind means "this run's pending
    # state is unknown"; a closed run owes nothing. The fleet cap counts this
    # field, never `errors`.
    open_errors: list[InboxError] = Field(default_factory=list)
```

Then in `fetch_fleet`, change the open-run loop's error branch (currently lines 116-119) from:

```python
    for run_id, outcome in zip(open_ids, open_results, strict=False):
        if isinstance(outcome, Exception):
            snap.errors.append(InboxError(run_id=run_id, error=str(outcome)))
            continue
```

to:

```python
    for run_id, outcome in zip(open_ids, open_results, strict=False):
        if isinstance(outcome, Exception):
            err = InboxError(run_id=run_id, error=str(outcome))
            snap.errors.append(err)
            snap.open_errors.append(err)  # B4: cap counts open failures only
            continue
```

Leave the closed-run loop (currently lines 128-137) exactly as it is — it must keep appending to `errors` alone.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dashboard_fleet.py -v`
Expected: PASS — the two new tests plus every pre-existing test in the file. The pre-existing assertions on `snap.errors` (`:104-105`, `:146`, `:203`) are unaffected: `errors` still receives every failure from both loops.

- [ ] **Step 5: Check the additive field breaks no HTTP consumer**

Run: `pytest tests/test_dashboard_api.py tests/test_dashboard_entrypoint.py -v`
Expected: PASS. `GET /inbox` declares `response_model=FleetSnapshot` (`api.py:112-114`) and the SSE stream serializes the whole snapshot (`api.py:132`), so both gain one new key whose value is an empty list by default — additive, and no existing assertion pins the exact key set.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/dashboard/fleet.py tests/test_dashboard_fleet.py
git commit -F <msgfile>
```

Message body (write to a temp file, no attribution trailer):
```
feat(dashboard): split open-run query failures out of FleetSnapshot.errors

fetch_fleet appends to one errors list from two loops: live runs whose
pending_decisions query failed, and already-closed runs whose run_summary
failed. A closed run owes no human a decision, so the new open_errors
field carries just the first kind. errors keeps its current meaning as
the union, so dashboard rendering is unchanged. Groundwork for the B4
fleet cap, which must count unknown-but-live runs without charging
finished ones.
```

---

### Task 2: The capacity check, its exception, the env-var cap, and the client-side guard

**Files:**
- Modify: `src/sdlc/dashboard/fleet.py` — add `import os` to the stdlib import block (lines 16-18; unaffected by Task 1, which only edits further down the file), and add four functions plus one exception class between the end of `fetch_fleet` and `def _utcnow()`. **Line numbers below are pre-Task-1**: Task 1 inserts ~8 lines above this region (6 comment lines in `FleetSnapshot`, 2 in the open-run loop), so after Task 1 lands, `fetch_fleet`'s closing `return snap` sits near line 146 and `_utcnow` near 149. Anchor on the content, not the number.
- Test: `tests/test_dashboard_fleet.py` (add the pure-function and guard tests)

**Interfaces:**
- Consumes: `FleetSnapshot` with `inbox` and `open_errors` (Task 1); `fetch_fleet(client, *, now, closed_limit=CLOSED_LIMIT)` (existing, `fleet.py:103`); `_utcnow()` (existing, `fleet.py:141`).
- Produces, all read by Tasks 3-5:
  - `pending_run_count(snap: FleetSnapshot) -> int`
  - `FleetCapacityExceeded(RuntimeError)` with attributes `cap: int` and `pending: int`
  - `check_fleet_capacity(snap: FleetSnapshot, cap: int | None) -> None` — raises `FleetCapacityExceeded`
  - `fleet_pending_cap() -> int | None` — reads `SDLC_FLEET_PENDING_CAP`
  - `async guard_fleet_capacity(client) -> None` — fetch + check in one call, for a caller holding a Temporal client rather than a poller

**Why `guard_fleet_capacity` exists:** the operator tool and the dashboard route both already hold a `FleetPoller` and can call `await poller.snapshot()` in one line, which their test suites can drive with a fake poller. `cli.py` holds only a raw Temporal client, and this repo has no pattern for exercising `cli.main()`'s async body (`tests/test_tidyup_cli_wiring.py` tests `build_parser()` and asserts on `inspect.getsource`). Putting the fetch-then-check composition in `fleet.py` means its behaviour is covered by real tests against the existing `_Client`/`_Handle` fakes, and `cli.py`'s untestable surface shrinks to a single call line.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_fleet.py`. Add `RunInbox` and `InboxError` to the existing `sdlc.channels.inbox` imports if they are not already imported in this file, and extend the `sdlc.dashboard.fleet` import line:

```python
from sdlc.channels.inbox import InboxError, RunInbox
from sdlc.dashboard.fleet import (
    FleetCapacityExceeded,
    FleetSnapshot,
    check_fleet_capacity,
    fetch_fleet,
    fleet_pending_cap,
    guard_fleet_capacity,
    pending_run_count,
)
```

Then the tests:

```python
# -- pending_run_count: what the cap actually counts (B4) --


def _snap(*, pending_runs: int = 0, open_errs: int = 0, closed_errs: int = 0) -> FleetSnapshot:
    return FleetSnapshot(
        at=AT,
        total_open_runs=pending_runs + open_errs,
        inbox=[RunInbox(run_id=f"open-{i}", pending=[Q1]) for i in range(pending_runs)],
        open_errors=[InboxError(run_id=f"bad-{i}", error="boom") for i in range(open_errs)],
        errors=(
            [InboxError(run_id=f"bad-{i}", error="boom") for i in range(open_errs)]
            + [InboxError(run_id=f"done-{i}", error="boom") for i in range(closed_errs)]
        ),
    )


def test_an_empty_fleet_has_nothing_pending():
    assert pending_run_count(_snap()) == 0


def test_each_run_with_pending_items_counts_once():
    assert pending_run_count(_snap(pending_runs=2)) == 2


def test_an_unqueryable_open_run_counts_toward_the_cap():
    """Fail-closed: an open run whose query failed has an UNKNOWN pending
    state, not a zero one. C8's shape -- an absence must never read as an
    approval."""
    assert pending_run_count(_snap(open_errs=1)) == 1


def test_a_closed_run_error_counts_for_nothing():
    """The Task 1 regression: three failed closed-run summary fetches are
    visible in errors but owe no decisions, so the cap must ignore them."""
    assert pending_run_count(_snap(closed_errs=3)) == 0


def test_pending_and_unqueryable_open_runs_sum():
    assert pending_run_count(_snap(pending_runs=2, open_errs=1, closed_errs=5)) == 3


def test_a_run_with_three_pending_items_still_counts_once():
    snap = FleetSnapshot(
        at=AT,
        total_open_runs=1,
        inbox=[RunInbox(run_id="busy", pending=[Q1, Q1, ARCH])],
    )
    assert pending_run_count(snap) == 1


# -- check_fleet_capacity: the admission decision --


def test_no_cap_configured_always_admits():
    check_fleet_capacity(_snap(pending_runs=99), None)  # must not raise


def test_below_the_cap_admits():
    check_fleet_capacity(_snap(pending_runs=4), 5)  # must not raise


def test_exactly_at_the_cap_refuses():
    """The boundary is >=, not >: cap=5 must mean at most five pending, so a
    sixth start is refused rather than admitted."""
    with pytest.raises(FleetCapacityExceeded):
        check_fleet_capacity(_snap(pending_runs=5), 5)


def test_over_the_cap_refuses():
    with pytest.raises(FleetCapacityExceeded):
        check_fleet_capacity(_snap(pending_runs=7), 5)


def test_the_refusal_carries_the_cap_and_the_count():
    with pytest.raises(FleetCapacityExceeded) as e:
        check_fleet_capacity(_snap(pending_runs=6), 5)
    assert e.value.cap == 5
    assert e.value.pending == 6
    assert "6" in str(e.value) and "5" in str(e.value)


# -- fleet_pending_cap: the env var --


def test_an_unset_cap_means_no_cap(monkeypatch):
    monkeypatch.delenv("SDLC_FLEET_PENDING_CAP", raising=False)
    assert fleet_pending_cap() is None


def test_a_set_cap_is_parsed(monkeypatch):
    monkeypatch.setenv("SDLC_FLEET_PENDING_CAP", "5")
    assert fleet_pending_cap() == 5


def test_a_garbage_cap_fails_loudly_rather_than_disabling_the_check(monkeypatch):
    """A typo'd cap must not silently mean 'no back-pressure' -- the same
    fail-closed posture as counting unqueryable open runs."""
    monkeypatch.setenv("SDLC_FLEET_PENDING_CAP", "lots")
    with pytest.raises(ValueError):
        fleet_pending_cap()


# -- guard_fleet_capacity: fetch + check, for a caller holding a client --


@pytest.mark.asyncio
async def test_the_guard_admits_when_no_cap_is_set(monkeypatch):
    monkeypatch.delenv("SDLC_FLEET_PENDING_CAP", raising=False)
    client = _Client({"run-a": _Handle(state=_state("run-a"), pending=[ARCH])})
    await guard_fleet_capacity(client)  # must not raise


@pytest.mark.asyncio
async def test_the_guard_never_touches_the_fleet_when_no_cap_is_set(monkeypatch):
    """B4 is opt-in, and opt-in must mean the fetch does not happen at all --
    not merely that its result is ignored. Reading the cap after awaiting the
    fetch (argument evaluation is left to right) would make every un-opted-in
    deployment pay a fan-out per start, and would turn a Temporal visibility
    blip into a failed `start` for operators who never enabled the cap.
    """
    monkeypatch.delenv("SDLC_FLEET_PENDING_CAP", raising=False)

    class _ExplodingClient:
        def list_workflows(self, query):
            raise AssertionError("the guard queried the fleet with no cap configured")

    await guard_fleet_capacity(_ExplodingClient())  # must not raise, must not query


@pytest.mark.asyncio
async def test_the_guard_refuses_when_the_fetched_fleet_is_at_cap(monkeypatch):
    monkeypatch.setenv("SDLC_FLEET_PENDING_CAP", "1")
    client = _Client({"run-a": _Handle(state=_state("run-a"), pending=[ARCH])})
    with pytest.raises(FleetCapacityExceeded) as e:
        await guard_fleet_capacity(client)
    assert e.value.pending == 1


@pytest.mark.asyncio
async def test_the_guard_admits_when_the_fetched_fleet_is_below_cap(monkeypatch):
    monkeypatch.setenv("SDLC_FLEET_PENDING_CAP", "2")
    client = _Client({"run-a": _Handle(state=_state("run-a"), pending=[ARCH])})
    await guard_fleet_capacity(client)  # 1 pending < cap 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard_fleet.py -v`
Expected: FAIL at collection — `ImportError: cannot import name 'FleetCapacityExceeded' from 'sdlc.dashboard.fleet'`. None of the five new names exist yet.

- [ ] **Step 3: Add `import os`**

In `src/sdlc/dashboard/fleet.py`, change the stdlib import block (currently lines 16-18) from:

```python
import asyncio
import contextlib
from datetime import UTC, datetime
```

to:

```python
import asyncio
import contextlib
import os
from datetime import UTC, datetime
```

- [ ] **Step 4: Add the exception and the four functions**

In `src/sdlc/dashboard/fleet.py`, insert this immediately after `fetch_fleet` (whose closing `return snap` was line 138 before Task 1 and is near line 146 after it) and before `def _utcnow()` (was 141, now near 149) — locate both by content:

```python
class FleetCapacityExceeded(RuntimeError):
    """B4: admission refused -- the fleet already owes humans as many
    decisions as it is allowed to. Carries cap/pending so a caller can render
    a message or an HTTP status without re-querying the fleet."""

    def __init__(self, cap: int, pending: int) -> None:
        super().__init__(
            f"fleet pending-decision cap reached: {pending} run(s) pending, cap is {cap}"
        )
        self.cap = cap
        self.pending = pending


def pending_run_count(snap: FleetSnapshot) -> int:
    """Runs currently owed a human decision, or whose load is unknown -- OPEN
    runs only.

    Counts RUNS, not pending items: a run holding three open questions is one
    human interaction to reclaim, not three. Unqueryable open runs count
    (fail-closed) because their pending state is unknown, not zero -- the same
    reason C8 refuses to read a lens that never ran as a lens that approved.
    Unqueryable CLOSED runs (in `errors` but not `open_errors`) are excluded:
    a finished run owes nothing.
    """
    return len(snap.inbox) + len(snap.open_errors)


def check_fleet_capacity(snap: FleetSnapshot, cap: int | None) -> None:
    """Raise FleetCapacityExceeded if the fleet is already at or over `cap`.

    `cap is None` means no cap is configured and every start is admitted. The
    boundary is >= so a configured 5 means at most five pending runs at any
    admission decision -- with > the steady state would settle at six.
    """
    if cap is None:
        return
    pending = pending_run_count(snap)
    if pending >= cap:
        raise FleetCapacityExceeded(cap, pending)


def fleet_pending_cap() -> int | None:
    """The configured cap, or None when unset (no cap -- B4 is opt-in).

    A set-but-unparseable value raises rather than degrading to None: a
    typo'd cap must not silently mean "no back-pressure".
    """
    raw = os.environ.get("SDLC_FLEET_PENDING_CAP")
    if raw is None:
        return None
    return int(raw)


async def guard_fleet_capacity(client) -> None:
    """Fetch the fleet and refuse admission if it is at cap (B4).

    For a caller holding a Temporal client rather than a FleetPoller -- the
    CLI. A caller that already has a poller should read the cap itself and
    pass `await poller.snapshot()` to check_fleet_capacity, so the poller's
    cached fan-out is reused instead of paying a fresh one.

    Reads the cap FIRST and returns without touching the client when none is
    configured. B4 is opt-in, so a deployment that never set the env var must
    not start paying a fleet fan-out per run start -- nor start failing on one
    when Temporal visibility is degraded.
    """
    cap = fleet_pending_cap()
    if cap is None:
        return
    check_fleet_capacity(await fetch_fleet(client, now=_utcnow()), cap)
```

**Why the cap is read before the fetch, at every call site in this plan.** Writing this as the one-liner `check_fleet_capacity(await fetch_fleet(client, now=_utcnow()), fleet_pending_cap())` would be a defect, not a style choice: Python evaluates arguments left to right, so the `await fetch_fleet(...)` would run *before* `fleet_pending_cap()` returned `None`. Every un-opted-in deployment would then pay a full fleet fan-out on every run start, and — worse — a Temporal visibility blip would newly break `start` for operators who never enabled back-pressure at all. `check_fleet_capacity` keeps its own `cap is None` guard (it is part of its contract and stays tested), but no call site may rely on it to avoid the fetch.

`guard_fleet_capacity` references `_utcnow`, defined just below it at module level — fine, because the name is resolved at call time, not at definition time.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_dashboard_fleet.py -v`
Expected: PASS — 18 new tests (6 counting, 5 admission, 3 env-var, 4 guard including the never-touches-the-fleet one) plus every pre-existing test in the file.

- [ ] **Step 6: Confirm no import cycle was introduced**

Run: `python -c "import sdlc.cli, sdlc.dashboard.api, sdlc.operator.tools; print('imports clean')"`
Expected: prints `imports clean`. This matters because Tasks 3-5 will import from `dashboard/fleet.py` in all three modules, and `dashboard/api.py` already imports `slug` from `cli.py` (`api.py:29`). No cycle exists: `dashboard/__init__.py` is empty (0 bytes), so importing `sdlc.dashboard.fleet` does not pull in `dashboard/api.py`, and `fleet.py` itself imports only `channels.inbox`, `core.models`, and `pending`.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/dashboard/fleet.py tests/test_dashboard_fleet.py
git commit -F <msgfile>
```

Message body:
```
feat(dashboard): add the fleet pending-decision cap check

pending_run_count counts open runs owed a human decision, plus open runs
whose query failed (fail-closed -- unknown is not zero), and ignores
closed-run errors entirely. check_fleet_capacity raises
FleetCapacityExceeded at >= the cap so a configured N means N.
fleet_pending_cap reads SDLC_FLEET_PENDING_CAP, unset meaning no cap, and
raises on a garbage value rather than quietly disabling back-pressure.
guard_fleet_capacity composes fetch-then-check for a caller holding a
Temporal client. Nothing calls any of this yet (B4).
```

---

### Task 3: The `start` CLI command refuses to start a run when the fleet is at cap

**Files:**
- Modify: `src/sdlc/cli.py:43-44` (a new import line between the `core.models` block's closing paren and `from .naming import slug`), `src/sdlc/cli.py:374-403` (the `start` branch)
- Test: `tests/test_fleet_capacity_wiring.py` (new)

**Interfaces:**
- Consumes: `guard_fleet_capacity(client)` and `FleetCapacityExceeded` (Task 2).
- Produces: nothing other tasks read. This is a leaf wiring change.

**Context for the implementer:** `main()` in `cli.py` connects a Temporal client at `:368-372` when `_needs_temporal_client(args)` is true (the `start` command is not in that function's `local_only` list, so `client` is always a live client by the time the `start` branch runs). The branch currently builds a `PipelineConfig`, applies any `--role-model` overrides, computes `wf_id`, calls `client.start_workflow(...)`, prints `started <id>`, and returns.

**Deliberate deviation from spec §9, recorded here rather than silently:** the spec's testing section asks for a CLI test where "a fetched snapshot at cap → `SystemExit(1)` with the capacity message printed, `start_workflow` never called." That requires driving `cli.main()`'s async body with a fake client, and no such harness exists in this repo — `main()` parses `sys.argv`, connects a real Temporal client, and branches inline, and every existing CLI test (`tests/test_tidyup_cli_wiring.py`, `tests/test_assessment_cli_wiring.py`) covers either `build_parser()` or module source rather than `main()`. Building that harness is a larger change than the one-line call it would test. Instead, the fetch-then-check-then-raise behaviour the spec wants covered is tested for real in Task 2 (`guard_fleet_capacity`, against the existing `_Client`/`_Handle` fakes), and this task pins the wiring — presence, refusal handling, and ordering — with source-needle tests, the same technique `tests/test_tidyup_cli_wiring.py:36-43` already uses for must-be-wired facts. The operator and dashboard call sites (Tasks 4 and 5) do get the full behavioural tests the spec describes, because their fake pollers make it cheap.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fleet_capacity_wiring.py`:

```python
"""B4: every client-side FeatureWorkflow start path consults the fleet cap.

The CLI's start branch lives inside cli.main()'s async body, which this repo
has no harness for driving (tests/test_tidyup_cli_wiring.py tests
build_parser() and asserts on source instead). The behaviour of the guard
itself is covered for real in tests/test_dashboard_fleet.py; what needs
pinning here is that the CLI actually calls it -- otherwise the check exists
and never runs, which is exactly the shape C8 named for review lenses.
"""

import inspect

from sdlc import cli


def test_the_start_command_guards_fleet_capacity():
    src = inspect.getsource(cli.main)
    assert "await guard_fleet_capacity(client)" in src, (
        "cli.py's start branch must call guard_fleet_capacity before "
        "start_workflow, or the cap exists without ever being consulted"
    )


def test_the_start_command_reports_a_refusal_instead_of_a_traceback():
    src = inspect.getsource(cli.main)
    assert "except FleetCapacityExceeded" in src, (
        "a refused start must print an operator-readable message and exit "
        "nonzero, not surface a RuntimeError traceback"
    )


def test_the_guard_runs_before_the_workflow_is_started():
    """Ordering, not just presence: guarding after start_workflow would
    admit the run and then complain about it."""
    src = inspect.getsource(cli.main)
    assert src.index("guard_fleet_capacity(client)") < src.index("FeatureWorkflow.run"), (
        "the capacity guard must precede the FeatureWorkflow start"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fleet_capacity_wiring.py -v`
Expected: FAIL — all three. The first two fail their `assert ... in src`; the third fails with `ValueError: substring not found` from `str.index`.

- [ ] **Step 3: Add the import**

In `src/sdlc/cli.py`, after the existing `from .core.models import (...)` block (currently ending at line 43) and before `from .naming import slug` (currently line 44), add:

```python
from .dashboard.fleet import FleetCapacityExceeded, guard_fleet_capacity
```

The resulting import order (`.core.models`, `.dashboard.fleet`, `.naming`, `.worker`, `.workflows.*`) is alphabetical, which is what `ruff`'s isort rules expect.

- [ ] **Step 4: Guard the start branch**

In `src/sdlc/cli.py`, change the `start` branch (currently lines 374-403) from:

```python
    if args.cmd == "start":
        from .cli_roles import build_role_overrides, parse_role_models

        cfg = PipelineConfig()
        if args.role_model:
            try:
                overrides = parse_role_models(args.role_model)
                cfg.roles.update(build_role_overrides(overrides))
            except Exception as e:  # ValueError / RegistryError
                print(f"invalid --role-model: {e}")
                raise SystemExit(1) from None
        wf_id = f"feature-{slug(args.title)}"
        assert client is not None
        handle = await client.start_workflow(
            FeatureWorkflow.run,
```

to:

```python
    if args.cmd == "start":
        from .cli_roles import build_role_overrides, parse_role_models

        cfg = PipelineConfig()
        if args.role_model:
            try:
                overrides = parse_role_models(args.role_model)
                cfg.roles.update(build_role_overrides(overrides))
            except Exception as e:  # ValueError / RegistryError
                print(f"invalid --role-model: {e}")
                raise SystemExit(1) from None
        wf_id = f"feature-{slug(args.title)}"
        assert client is not None
        # B4 fleet back-pressure -- see
        # docs/superpowers/specs/2026-09-09-b4-fleet-backpressure-design.md.
        # Refuse a new run while the fleet already owes humans its full
        # allowance of decisions. No-ops without touching Temporal when
        # SDLC_FLEET_PENDING_CAP is unset.
        try:
            await guard_fleet_capacity(client)
        except FleetCapacityExceeded as e:
            print(
                f"fleet at capacity: {e.pending} run(s) awaiting a human "
                f"decision, cap is {e.cap}. Clear some pending decisions "
                f"(python -m sdlc.cli inbox) or raise "
                f"SDLC_FLEET_PENDING_CAP."
            )
            raise SystemExit(1) from None
        handle = await client.start_workflow(
            FeatureWorkflow.run,
```

Leave everything from `FeatureWorkflow.run,` onward unchanged. The `raise ... from None` and the print-then-exit shape match the existing `--role-model` failure directly above it and the `revise`-without-`--comment` check at `:363-365`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_fleet_capacity_wiring.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Confirm the other CLI start paths were not touched**

Run: `pytest tests/test_tidyup_cli_wiring.py tests/test_assessment_cli_wiring.py tests/test_benchmark_cli.py -v`
Expected: PASS. `TriageWorkflow` (`:571`), `TidyUpWorkflow` (`:615`), `AssessmentWorkflow` (`:666`), and `BenchmarkWorkflow` (`benchmarks/cli.py:211`) are out of scope and must remain unguarded — see the start-site audit above.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/cli.py tests/test_fleet_capacity_wiring.py
git commit -F <msgfile>
```

Message body:
```
feat(cli): refuse `start` while the fleet is at its pending-decision cap

The start command consults guard_fleet_capacity before starting a
FeatureWorkflow and prints an operator-readable refusal naming the count,
the cap, and how to clear it. Pinned by source-needle tests, including
one on ordering, because cli.main()'s async body has no test harness in
this repo and a guard placed after the start would admit the run it was
meant to refuse. Triage/tidyup/assess/benchmark starts are deliberately
untouched (B4).
```

---

### Task 4: The operator `start_run` tool refuses at cap, with a model-readable reason

**Files:**
- Modify: `src/sdlc/operator/tools.py:501-541` (`start_run`; the inserted check goes at `:528-530`)
- Modify: `src/sdlc/operator/errors.py:13-14` (imports), `src/sdlc/operator/errors.py:25-47` (`translate`)
- Test: `tests/test_operator_writes.py` (extend `FakePoller`, add two tests)

**Interfaces:**
- Consumes: `check_fleet_capacity`, `fleet_pending_cap`, `FleetCapacityExceeded` (Task 2); `OperatorDeps.poller` (existing, `deps.py:25`, documented as a `dashboard.fleet.FleetPoller`); `ToolError` (existing, `errors.py:17`).
- Produces: nothing other tasks read.

**Context for the implementer:** `start_run` (`tools.py:501-541`) is decorated with `@guard` (`errors.py:50-60`), which funnels every exception through `translate()` into a `ToolError` whose message is safe to show a model. So `start_run` needs no `try`/`except` of its own — the branch goes in `translate()`, where the other domain exceptions are already mapped. `start_run` already calls `deps.note_other_tool()` first and validates brownfield/title before starting; the capacity check goes after those and immediately before `await deps.starter(...)` at `:530`.

**Test-fixture note:** `tests/test_operator_writes.py`'s `FakePoller` (`:33-38`) implements only `_client_or_connect`, not `snapshot()`. Adding a `poller.snapshot()` call to `start_run` breaks every `start_run` test in that file until the fixture grows one. That fixture edit is part of this task, not an afterthought.

- [ ] **Step 1: Give the test fixture a snapshot, and write the failing tests**

In `tests/test_operator_writes.py`, change `FakePoller` (currently lines 33-38) from:

```python
class FakePoller:
    def __init__(self, handle):
        self._handle = handle

    async def _client_or_connect(self):
        return FakeClient(self._handle)
```

to:

```python
class FakePoller:
    def __init__(self, handle, snap=None):
        self._handle = handle
        self._snap = snap if snap is not None else FleetSnapshot(at=AT_SNAP)

    async def _client_or_connect(self):
        return FakeClient(self._handle)

    async def snapshot(self):
        # B4: start_run reads the fleet's pending-decision load from here.
        # Defaults to an empty fleet so every pre-existing start_run test
        # keeps admitting.
        return self._snap
```

Add the imports and the timestamp constant this needs, beside the file's existing imports:

```python
from datetime import UTC, datetime

from sdlc.channels.inbox import RunInbox
from sdlc.dashboard.fleet import FleetSnapshot

AT_SNAP = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
```

(If the file already imports `datetime`/`UTC`, do not duplicate the import.)

Then append these two tests:

```python
@pytest.mark.asyncio
async def test_start_run_refuses_when_the_fleet_is_at_capacity(deps, monkeypatch):
    """B4: the tool must decline rather than adding a fifth pending decision
    to a fleet capped at four."""
    monkeypatch.setenv("SDLC_FLEET_PENDING_CAP", "2")
    deps.poller._snap = FleetSnapshot(
        at=AT_SNAP,
        total_open_runs=2,
        inbox=[
            RunInbox(run_id="feature-one", pending=[Q1]),
            RunInbox(run_id="feature-two", pending=[Q1]),
        ],
    )
    with pytest.raises(ToolError) as e:
        await tools.start_run(deps, title="Add SSO", mode=ProjectMode.GREENFIELD)
    assert "capacity" in str(e.value.message)
    assert "2" in str(e.value.message)
    assert deps.started == []  # the starter was never called


@pytest.mark.asyncio
async def test_start_run_admits_below_the_cap(deps, monkeypatch):
    monkeypatch.setenv("SDLC_FLEET_PENDING_CAP", "3")
    deps.poller._snap = FleetSnapshot(
        at=AT_SNAP,
        total_open_runs=1,
        inbox=[RunInbox(run_id="feature-one", pending=[Q1])],
    )
    run_id = await tools.start_run(deps, title="Add SSO", mode=ProjectMode.GREENFIELD)
    assert run_id == "feature-add-sso"
    assert len(deps.started) == 1


@pytest.mark.asyncio
async def test_start_run_does_not_read_the_fleet_when_no_cap_is_set(deps, monkeypatch):
    """Opt-in means the snapshot is never taken, not that it is taken and
    ignored -- poller.snapshot() falls back to an inline Temporal fan-out
    when its cache is stale, so an un-opted-in operator must not pay it."""
    monkeypatch.delenv("SDLC_FLEET_PENDING_CAP", raising=False)

    async def exploding_snapshot():
        raise AssertionError("start_run read the fleet with no cap configured")

    deps.poller.snapshot = exploding_snapshot
    run_id = await tools.start_run(deps, title="Add SSO", mode=ProjectMode.GREENFIELD)
    assert run_id == "feature-add-sso"
```

`ToolError` must be importable in this test file — add `from sdlc.operator.errors import ToolError` if it is not already imported (the existing duplicate-id test at `:163-169` asserts on a raised error, so it very likely is).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_operator_writes.py -k "capacity or below_the_cap or does_not_read_the_fleet" -v`
Expected: FAIL on `test_start_run_refuses_when_the_fleet_is_at_capacity` — `start_run` never consults the fleet, so it succeeds instead of raising `ToolError` and `deps.started` has one entry. The other two **pass already**, and that is expected: `test_start_run_admits_below_the_cap` and `test_start_run_does_not_read_the_fleet_when_no_cap_is_set` are regression guards, not red-first tests — nothing reads the fleet yet, so "reads it only when capped" is trivially true today and must stay true after Step 3.

- [ ] **Step 3: Add the capacity check to `start_run`**

In `src/sdlc/operator/tools.py`, add to the imports (after the existing `from ..core.models import (...)` block, keeping alphabetical order — `..dashboard.fleet` sorts after `..core.models` and before `..naming`):

```python
from ..dashboard.fleet import check_fleet_capacity, fleet_pending_cap
```

Then in `start_run`, insert the check between the title validation and the `try:` that calls the starter. Change (currently lines 528-530):

```python
    wf_id = f"feature-{stem}"
    try:
        started = await deps.starter(idea, PipelineConfig(), wf_id)
```

to:

```python
    wf_id = f"feature-{stem}"
    # B4 fleet back-pressure, before anything is started -- see
    # docs/superpowers/specs/2026-09-09-b4-fleet-backpressure-design.md.
    # The cap is read FIRST: with none configured this must not touch the
    # fleet at all, since the poller's snapshot() falls back to an inline
    # fan-out when its cache is stale (fleet.py:218-224).
    cap = fleet_pending_cap()
    if cap is not None:
        check_fleet_capacity(await deps.poller.snapshot(), cap)
    try:
        started = await deps.starter(idea, PipelineConfig(), wf_id)
```

`FleetCapacityExceeded` propagates out of `start_run` untouched — `@guard` catches it and Step 4 teaches `translate()` what to say about it.

- [ ] **Step 4: Map the refusal to a model-readable `ToolError`**

In `src/sdlc/operator/errors.py`, change the imports (currently lines 13-14) from:

```python
from ..board.store import ConflictError, InvalidTransition, NotFoundError
from ..channels.transport import Ambiguous, NoMatch
```

to:

```python
from ..board.store import ConflictError, InvalidTransition, NotFoundError
from ..channels.transport import Ambiguous, NoMatch
from ..dashboard.fleet import FleetCapacityExceeded
```

Then add a branch in `translate()`. Change (currently lines 40-42, the `InvalidTransition` branch and the `else` that follows it — note `:38-39` is the `ConflictError` branch above, which stays untouched):

```python
    elif isinstance(exc, InvalidTransition):
        msg = f"invalid board transition: {exc}"
    else:
```

to:

```python
    elif isinstance(exc, InvalidTransition):
        msg = f"invalid board transition: {exc}"
    elif isinstance(exc, FleetCapacityExceeded):
        # B4: an actionable refusal, not a bug -- the model should stop
        # starting runs and tell the operator what is blocking.
        msg = (
            f"the fleet is at capacity: {exc.pending} run(s) are already "
            f"awaiting a human decision and the cap is {exc.cap}. Do not "
            f"retry; tell the operator to clear some pending decisions "
            f"first (the inbox lists them)."
        )
    else:
```

Leave the `else` branch's deliberately type-only message unchanged.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_operator_writes.py -v`
Expected: PASS — the three new tests plus every pre-existing test in the file. The pre-existing `start_run` tests (`:144`, `:156`, `:163`, `:181`, `:195`) run with `SDLC_FLEET_PENDING_CAP` unset, so `fleet_pending_cap()` returns `None` and `poller.snapshot()` is never called at all — the `snapshot()` added to `FakePoller` in Step 1 is there for the *capped* tests, and as insurance against a future test that does set the env var. (Had the check been written as a single call with the fetch as its first argument, those five tests would depend on the fixture's `snapshot()` to pass; they must not.)

- [ ] **Step 6: Run the rest of the operator suite**

Run: `pytest tests/test_operator_agent.py tests/test_operator_writes.py -v`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/operator/tools.py src/sdlc/operator/errors.py tests/test_operator_writes.py
git commit -F <msgfile>
```

Message body:
```
feat(operator): refuse start_run while the fleet is at its cap

The tool checks the poller's cached snapshot before calling the starter,
and translate() maps the refusal to a ToolError that tells the model to
stop rather than retry -- an actionable limit, not a fault. FakePoller in
the tests grows a snapshot() method for the capped cases; the existing
start_run tests never reach it, because an unset cap short-circuits before
the fleet is read (B4).
```

---

### Task 5: `POST /runs` answers 429 when the fleet is at cap

**Files:**
- Modify: `src/sdlc/dashboard/api.py:37` (import), `src/sdlc/dashboard/api.py:173-187` (the `start` route)
- Test: `tests/test_dashboard_api.py` (add two tests)

**Interfaces:**
- Consumes: `check_fleet_capacity`, `fleet_pending_cap`, `FleetCapacityExceeded` (Task 2); the `poller` already passed to `create_router` (`api.py:75`).
- Produces: nothing other tasks read.

**Context for the implementer:** the `start` route (`api.py:173-187`) already has a three-branch failure ladder: re-raise an `HTTPException` untouched, map an `"already started"` message to 409, and map anything else to 502. The capacity refusal must be caught *before* the generic `except Exception`, or it would surface as a 502 "bad gateway" — which would tell an operator their Temporal is broken when in fact the fleet is simply full.

- [ ] **Step 1: Write the failing tests**

In `tests/test_dashboard_api.py`, append these tests. The existing `start_client` fixture (`:182-199`) builds the router with a `_FakePoller(snap)` whose `snapshot()` returns the module's `snap` fixture — one run, `runs=[...]`, and an empty `inbox` — so the default fleet has a pending count of zero and existing tests keep passing.

```python
def test_start_run_429s_when_the_fleet_is_at_capacity(snap, monkeypatch):
    """B4: a full fleet is 429 (a load limit the caller should back off from),
    never 502 -- the operator must not be told Temporal is broken."""
    monkeypatch.setenv("SDLC_FLEET_PENDING_CAP", "1")
    snap.inbox = [RunInbox(run_id="feature-one", pending=[ARCH])]
    started = []

    async def starter(idea, cfg, wf_id):
        started.append(wf_id)
        return wf_id

    app = FastAPI()
    app.include_router(create_router(_FakePoller(snap), starter=starter))
    r = TestClient(app).post(
        "/runs", json={"title": "Add SSO", "description": "d", "mode": "greenfield"}
    )
    assert r.status_code == 429
    assert "cap" in r.json()["detail"]
    assert started == []  # the starter was never called


def test_start_run_admits_below_the_cap(snap, monkeypatch):
    monkeypatch.setenv("SDLC_FLEET_PENDING_CAP", "2")
    snap.inbox = [RunInbox(run_id="feature-one", pending=[ARCH])]
    started = []

    async def starter(idea, cfg, wf_id):
        started.append(wf_id)
        return wf_id

    app = FastAPI()
    app.include_router(create_router(_FakePoller(snap), starter=starter))
    r = TestClient(app).post(
        "/runs", json={"title": "Add SSO", "description": "d", "mode": "greenfield"}
    )
    assert r.status_code == 200
    assert started == ["feature-add-sso"]


def test_start_run_does_not_read_the_fleet_when_no_cap_is_set(snap, monkeypatch):
    """Opt-in must mean the snapshot is never taken. A poller whose snapshot()
    raises stands in for degraded Temporal visibility: with no cap set, the
    route must still return 200 rather than newly 502-ing a deployment that
    never enabled back-pressure."""
    monkeypatch.delenv("SDLC_FLEET_PENDING_CAP", raising=False)

    class _ExplodingPoller:
        async def snapshot(self):
            raise AssertionError("the route read the fleet with no cap configured")

    started = []

    async def starter(idea, cfg, wf_id):
        started.append(wf_id)
        return wf_id

    app = FastAPI()
    app.include_router(create_router(_ExplodingPoller(), starter=starter))
    r = TestClient(app).post(
        "/runs", json={"title": "Add SSO", "description": "d", "mode": "greenfield"}
    )
    assert r.status_code == 200
    assert started == ["feature-add-sso"]
```

Add `from sdlc.channels.inbox import RunInbox` to the file's imports if it is not already there.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard_api.py -k "429 or admits_below or does_not_read_the_fleet" -v`
Expected: FAIL on `test_start_run_429s_when_the_fleet_is_at_capacity` — the route never consults the fleet, so it answers 200 instead of 429 and `started` has one entry. The other two **pass already**, as regression guards rather than red-first tests: nothing reads the fleet yet, so "reads it only when capped" is trivially true today and must remain true after Step 4.

- [ ] **Step 3: Add the import**

In `src/sdlc/dashboard/api.py`, change line 37 from:

```python
from .fleet import FleetPoller, FleetSnapshot
```

to:

```python
from .fleet import (
    FleetCapacityExceeded,
    FleetPoller,
    FleetSnapshot,
    check_fleet_capacity,
    fleet_pending_cap,
)
```

- [ ] **Step 4: Guard the route**

In `src/sdlc/dashboard/api.py`, change the `start` route (currently lines 173-187) from:

```python
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
```

to:

```python
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
        except Exception as e:  # noqa: BLE001
            if "already started" in str(e).lower():
                raise HTTPException(409, f"run {wf_id!r} already exists") from e
            raise HTTPException(502, str(e)) from e
        return StartedRun(run_id=wf_id)
```

The capacity check gets its **own** `try` block ahead of the starter's, rather than another `except` clause on the existing one: sharing the block would let a `FleetCapacityExceeded` raised by the check be reachable only after the starter had already run.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_dashboard_api.py -v`
Expected: PASS — the three new tests plus every pre-existing test, including `test_start_run_builds_the_workflow_id_from_the_title` (`:201`) and `test_start_run_409s_on_a_duplicate_id` (`:218`). Those two run with `SDLC_FLEET_PENDING_CAP` unset, so `fleet_pending_cap()` returns `None` and the route never calls `poller.snapshot()` — which is exactly what the third new test pins.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/dashboard/api.py tests/test_dashboard_api.py
git commit -F <msgfile>
```

Message body:
```
feat(dashboard): 429 on POST /runs while the fleet is at its cap

The route checks the poller's snapshot in its own try block ahead of the
starter's, so a full fleet answers 429 (back off) rather than falling
through to the 502 branch and blaming Temporal for a queue that is merely
full (B4).
```

---

### Task 6: Contract text and operator discoverability

**Files:**
- Modify: `src/sdlc/dashboard/fleet.py:1-12` (module docstring)
- Modify: `.env.example` (the "Tunables (optional)" section)

**Interfaces:**
- None — documentation only, no code interfaces change.

**Why `.env.example` and not a stage contract:** B4 lands at the admission layer, above any single stage, so there is no `merge.md`-style stage contract to extend (those live under `src/sdlc/stages/<name>/`). The module docstring is where `fleet.py` already documents its invariants, and `.env.example` is where every other `SDLC_*` knob is documented for an operator — a module docstring alone would never teach anyone the new env var exists.

- [ ] **Step 1: Extend the module docstring**

In `src/sdlc/dashboard/fleet.py`, change the module docstring (currently lines 1-12) from:

```python
"""Fleet fan-out and snapshot for the dashboard backend (E-10).

Imports no web framework: the fan-out and the poller are where the interesting
failures live, so they must be testable without an HTTP client -- the same
reason channels/transport.py is testable without a CLI.

Generalizes channels/inbox.py's pattern to two queries per handle, and adds
a capped second pass over recently CLOSED runs. That second pass is why the
dashboard needs no database (spec D7): Temporal keeps closed workflows
queryable for its retention period, so Temporal is the store. The bound is
real -- history reaches back only as far as that retention.
"""
```

to:

```python
"""Fleet fan-out and snapshot for the dashboard backend (E-10), and the
fleet-wide admission cap over it (B4).

Imports no web framework: the fan-out and the poller are where the interesting
failures live, so they must be testable without an HTTP client -- the same
reason channels/transport.py is testable without a CLI.

Generalizes channels/inbox.py's pattern to two queries per handle, and adds
a capped second pass over recently CLOSED runs. That second pass is why the
dashboard needs no database (spec D7): Temporal keeps closed workflows
queryable for its retention period, so Temporal is the store. The bound is
real -- history reaches back only as far as that retention.

Back-pressure (B4, designed in
docs/superpowers/specs/2026-09-09-b4-fleet-backpressure-design.md): FR-303
holds ONE run at ONE gate; nothing capped how many runs could stall on humans
at once. fleet_pending_cap reads that cap from SDLC_FLEET_PENDING_CAP;
check_fleet_capacity raises FleetCapacityExceeded once pending_run_count
reaches it; guard_fleet_capacity composes fetch-then-check for a caller
holding a client rather than a poller. The three client-side FeatureWorkflow
start paths (cli.py's `start`, operator start_run, dashboard POST /runs)
consult it before starting anything, each translating the refusal into its
own surface's failure shape.

Five properties are load-bearing, each with a test that fails if it is
dropped: the count is of RUNS, not pending items; only OPEN runs count, which
is why open_errors exists apart from errors; an unqueryable open run counts
(fail-closed -- unknown is not zero, C8's rule); the boundary is >=, so a
configured N means N; and the cap is opt-in, which means an unset cap must
skip the fetch ENTIRELY rather than discard its result -- read the cap before
awaiting a snapshot, never as the second argument to a call whose first
argument fetches. In-workflow child spawns (tidyup, benchmarks) are NOT
capped -- they run in a workflow sandbox with no client, and are bounded
fan-out from a run a human already approved.
"""
```

- [ ] **Step 2: Document the env var for operators**

In `.env.example`, change the "Tunables (optional)" section from:

```
# --- Tunables (optional) ---
# SDLC_WORKTREES_ROOT=/tmp/sdlc/worktrees
# SDLC_MODEL_MAX_TOKENS=64000
```

(That is the first three lines of the section only — it continues with `SDLC_LONG_ACTIVITY_HEARTBEAT_MINUTES`, `SDLC_LONG_ACTIVITY_TIMEOUT_HOURS`, and the commented `SDLC_AGENTS_DIR` block. Leave all of those exactly as they are; only insert above `SDLC_WORKTREES_ROOT`.)

to:

```
# --- Tunables (optional) ---
# Fleet back-pressure (B4). Max FeatureWorkflow runs allowed to be awaiting a
# human decision at once; a new run refuses to start at or above this number,
# from every surface (CLI `start`, operator chat, dashboard). Counts runs, not
# questions -- one run with three open questions counts once -- and counts a
# live run whose state cannot be queried, so degraded visibility blocks
# visibly instead of over-admitting silently. Unset means no cap.
# SDLC_FLEET_PENDING_CAP=5
# SDLC_WORKTREES_ROOT=/tmp/sdlc/worktrees
# SDLC_MODEL_MAX_TOKENS=64000
```

- [ ] **Step 3: Verify nothing regressed**

Run: `pytest tests/test_dashboard_fleet.py tests/test_dashboard_api.py -q`
Expected: PASS. Docstring and comment edits only; this step exists to catch an accidental code deletion while editing the docstring above the imports.

- [ ] **Step 4: Commit**

```bash
git add src/sdlc/dashboard/fleet.py .env.example
git commit -F <msgfile>
```

Message body:
```
docs(dashboard): document the fleet cap and its env var

fleet.py's docstring names the five load-bearing properties of the cap
(runs not items, open runs only, fail-closed on unqueryable open runs,
the >= boundary, and opt-in meaning the fetch is skipped entirely) plus
what is deliberately not capped. .env.example gains
SDLC_FLEET_PENDING_CAP beside the other tunables, since a module
docstring cannot teach an operator that the knob exists (B4).
```

---

## Final verification

- [ ] Run the full suite: `pytest tests/ -q`
- [ ] Run lint: `ruff check .`
- [ ] Run format check: `ruff format --check .`
- [ ] Run type check: `mypy src/`
- [ ] Run the file-size ratchet: `python scripts/check_file_size.py`
- [ ] Confirm the cap is genuinely opt-in: with `SDLC_FLEET_PENDING_CAP` unset, `pytest tests/test_dashboard_api.py tests/test_operator_writes.py tests/test_dashboard_fleet.py -q` passes, and `git stash` + re-run shows the same pre-existing tests passing before and after.
- [ ] Confirm no call site fetches before reading the cap: `grep -rn "fleet_pending_cap())" src/` returns **nothing**. That needle (note the doubled closing paren — an inner `fleet_pending_cap()` call closing inside an outer call's argument list) matches only the forbidden one-liner shape, and matches none of the three correct sites, which pass an already-bound `cap` local instead. Do **not** grep for `check_fleet_capacity(await` — the corrected code contains exactly that substring three times, by design. The three tests named `*does_not_read_the_fleet_when_no_cap_is_set` / `*never_touches_the_fleet_when_no_cap_is_set` (Tasks 2, 4, 5) are the behavioural backstop: each fails if its own site regresses.
- [ ] Confirm scope was not widened: `git diff main -- src/sdlc/workflows/tidyup.py src/sdlc/benchmarks/workflow.py` is empty (spec §7 keeps in-workflow spawns uncapped).
- [ ] Confirm no new workflow type entered any query: `git diff main -- src/sdlc/channels/inbox.py` is empty, and `grep -n "CrewTaskWorkflow\|TriageWorkflow" src/sdlc/dashboard/fleet.py` returns nothing.
- [ ] Confirm `errors` kept its meaning: `grep -n "snap.errors.append" src/sdlc/dashboard/fleet.py` returns two hits (both loops still populate the union).
- [ ] Confirm six commits exist on the branch, each independently green.
- [ ] Confirm no commit message contains `Co-Authored-By` or `Claude-Session`: `git log main..HEAD --format=%B | grep -iE "co-authored|claude-session"` returns nothing.
