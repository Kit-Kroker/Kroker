# Bug Assessment: Replay golden tier flakes — gate remind timer elided when the driver's decision signal wins a real-time race

- **Slug**: golden-tick-race
- **Created**: 2026-10-18
- **Source**: pasted text (orchestrator TASK BRIEF; symptom observed 2026-10-17/18 on main `b01f9b07`)
- **Verdict**: valid (mechanism proven by a deterministic probe, 3/3 per variant)
- **Severity**: medium (test-infrastructure flake; no production behavior change; blocks any N×green replay gate and keeps the continue-on-error temporal tier untrustworthy)

## Report (verbatim or summarized)

`pytest -m temporal tests/replay` intermittently fails
`test_graph_workflow_reproduces_the_golden_trace[budget_arch_reject-sandboxed]`
(rarely a sibling) with SG-3 "command projection differs": the captured
projection has `activity:publish_artifact_version` where the golden has
`timer` at index 11, and the captured sequence is one entry shorter (pytest
names the golden's trailing `activity:cleanup_run_worktrees` as the extra
item). Failed 2/2 in one window, passed 32/32 in another, failed again later
on main `b01f9b07` — roughly a coin flip per window.

## Symptom

A golden replay capture sometimes records one fewer `timer` command than the
golden pins: the budget gate's remind timer vanishes mid-sequence and every
later command shifts one index left. Expected: the captured command
projection equals the golden byte-for-byte on every run.

## Reproduction

Probabilistic on the primary checkout (load-dependent window):

1. Run `pytest -m temporal tests/replay/test_graph_golden.py` (full file) on
   main under ordinary machine load; repeat across windows until
   `[budget_arch_reject-sandboxed]` fails SG-3 (prior windows: 2/2 fail,
   32/32 pass, fail again; one 016-era evening failed ~6 runs over 40 min).
2. Deterministic mechanism probe (this assessment, container
   `ghcr.io/kit-kroker/kroker-worker:latest`, script
   `.workspace/tmp/tickrace_probe2.py`): a gate-shaped workflow whose
   decision signal is server-recorded while its OPENED-notify activity is
   still executing produces a history with **zero** timer events (3/3);
   signaling after the notify completes records
   `TIMER_STARTED → SIGNALED → TIMER_CANCELED` (3/3).

## Prior diagnoses (built on, not re-derived)

- `notify-flake` (2026-09-20), `.specify/bugs/notify-flake/test.md:68-98`:
  diagnosed this as a second, out-of-scope race — "driver-vs-gate-schedule",
  "the status query and the workflow-task queueing decide whether the signal
  task beats the next schedule-tick task" — and named the lever:
  "pin the drivers to tick boundaries … the lever is
  `tests/replay/scenarios.py` drivers / wait_for". Never fixed; card
  `.workspace/tasks/golden-tick-race.md` was a local untracked card (now
  gone; the tracked mechanism survives in test.md).
- `.workspace/tasks/2026-10-02-golden-graph-trace-flake.md`: reproduced 3/3
  in kroker-dev + kroker-baseline on main `2196438`, passed 2/2 after a host
  restart — "re-attributed to load, still not investigated"; also records
  that CI's temporal step is continue-on-error (the flake is invisible
  there).
- `.specify/specs/016-decomposition-case/verification.md:36-45`: identical
  failure on pristine base `b01f9b07` — not the 016 branch, not the
  `cleanup_run_worktrees` registration (both already excluded as non-causes
  in the brief).
- `cdcf83d` (memory hint "golden-tick race fix family"): that commit bounds
  `AGENT_ACTIVITY_CONFIG` retries (bug `e2e-proposer-hang`) — adjacent era,
  different mechanism. **Not a regression**: the race predates it and was
  never fixed; the notify-flake-era commits (`4ce7deba`, `315992db`)
  addressed the separate "activity not registered" flake.

## Suspected Code Paths

- `tests/replay/harness.py:100-112` — concurrent mode runs the driver and
  `handle.result()` inside `env.auto_time_skipping_disabled()`: gate remind
  timers (hours away) cannot fire, so every gate decision arrives as a
  real-time driver signal racing the workflow's own scheduling.
- `src/sdlc/workflows/gates.py:169-186` (`_wait_for_decision`) with
  `src/sdlc/notify/schedule.py:42` (first schedule entry `OPENED` at
  `opened_at`): iteration 1 gets `timeout=0` → CPython 3.13
  `asyncio.wait_for` fast path raises `TimeoutError` with no timer → the
  OPENED notify activity; the remind timer exists only after the workflow
  task that resumes from that activity's completion.
- `temporalio/worker/_workflow_instance.py:1860-1905` (`wait_condition` =
  `asyncio.wait_for` over a condition future) and `:2855-2875`
  (`_timer_impl` applies the TimerStart command eagerly at `call_at`):
  when the decision signal is already recorded at resume, iteration 2
  issues TimerStart+CancelTimer **within one workflow-task completion** —
  and Temporal core elides the pair (probe-proven): no `TIMER_STARTED`
  event lands in history.
- `tests/replay/projection.py:24-37` — `command_projection` counts
  `TIMER_STARTED`; the elided run is one `timer` shorter and shifts every
  later command left — byte-identical to the observed SG-3 diff.
- `tests/replay/scenarios.py:86-108` (`wait_for`/`decide`/`answer_clarify`)
  — the driver signals on the first status poll that sees `awaiting:*`;
  nothing pins the signal to the gate's remind-timer creation.

## Root Cause Hypothesis

Confidence: **high** (proven, not hypothesized). The golden pins the
interleaving where each gate decision signal is recorded *after* the gate's
remind `TIMER_STARTED`. The harness allows the other legal interleaving:
under load, the driver's signal (one client→server hop) beats the fake
notify activity's completion report (worker round trips), so the resumed
gate calls `wait_condition` with the decision already present; the SDK's
eager TimerStart plus the immediate condition resolution put
StartTimer+CancelTimer in a single workflow-task completion, which Temporal
core elides from history — the capture is legitimately one `timer` shorter.
`budget_arch_reject` is the frequent victim because its budget gate opens
precisely when the driver is hot-polling `awaiting:budget` (immediately
after sending the architecture reject); siblings (waves, arch_revise_final,
observed in the notify-flake and 015-erosion logs) hit the same class at
other gates. All 46 decided signals across all 21 recorded histories are
the timer-first variant — the goldens uniformly pin the lucky side of the
race.

## Proposed Remediation

**Preferred (deterministic capture, harness-only — the lever the
notify-flake ruling named)**: pin the drivers in `tests/replay/scenarios.py`
so a decision/answer signal is sent only after the pending gate's remind
timer is visible in history. At `decide()`/`answer_clarify()` entry,
snapshot the history's `TIMER_STARTED` count; after `wait_for(status)`
returns, poll `handle.fetch_history()` (bounded, ~10 s deadline, hard error
on expiry) until the count increases; then signal. By construction this
reproduces the recorded timer-first interleaving for every scenario —
verified consistent with all 21 histories — with zero golden edits and no
`src/` change.

**Alternatives** (rejected):
- Make SG-3 accept either ordering (normalize an elided timer). Masks the
  race and weakens the timer pin for genuinely timer-dependent scenarios
  (arch_timeout_reject); the brief prefers deterministic capture.
- Add a test-only query exposing gate-timer state. Touches the workflow
  wire surface (`src/`); heavier than the harness pin.

**Files likely to change**:
- `tests/replay/scenarios.py` (the `decide`/`answer_clarify` chokepoint; a
  shared "await the pending gate timer" helper)
- `tests/replay/test_graph_golden_chaos.py` or a new RED contract module
  under `tests/replay/` (driver-pin contracts)

**Tests to add or update**:
- Happy-path RED contract: `decide()`/`answer_clarify()` hold the signal
  until a new `TIMER_STARTED` exists (fake handle whose history gains the
  timer after a delay — pre-fix signals immediately → RED).
- Chaos RED contract: the adversarial interleaving (signal server-recorded
  before the notify activity completes) yields a history with no timer
  event and a one-shorter `command_projection` — pinning the mechanism on
  record — and the fixed driver never produces it.
- Existing in-test golden count-freeze rows and SG-2 byte-identity must
  stay green unchanged (no golden/history re-record).

**Verification gate** (per brief): `pytest -m temporal tests/replay` green
5 consecutive runs in the kroker-dev container (primary checkout at `/app`,
`kroker-verify-venv`, image `ghcr.io/kit-kroker/kroker-worker:latest`);
never two pytest runs chained in one shell call.

## Risks & Considerations

- A scenario whose decided gate legitimately schedules no remind timer
  (none today; every recorded decided gate has one) would deadlock at the
  pin — the bounded poll fails loudly with a named error instead.
- `fetch_history` polling adds client-side load during full-file runs —
  bounded (tens of ms cadence, few iterations per gate).
- The pin changes signal timing, not signal content: SG-1 double-capture
  equality and both sandboxed/unsandboxed variants stay deterministic.
- CI visibility (continue-on-error temporal step) is the 2026-10-02 card's
  second ask — out of scope here; noted for the orchestrator.

## Open Questions

- None blocking the cause. For the fix ruling: confirm direction A
  (deterministic driver pin, preferred) vs B (projection robust to either
  ordering).
