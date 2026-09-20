# E-75 discovery: driver-vs-gate-schedule-tick race in the replay harness
(bug golden-tick-race)

**Discovered:** 2026-09-20 during bug notify-flake's verification gate.
**Status:** OPEN — ruled out of scope for notify-flake (orchestrator ruling
2026-09-20 on file: notify-flake closed partial; atomicity binds; the brief's
out-of-scope list excludes "any other flake"). NOT fixed on branch
fix/notify-flake.

## Symptom

`tests/replay/test_graph_golden.py` fails under full-file load with SG-3
command-projection divergence (NOT the notify "not registered" error, which
notify-flake eliminated):

- `budget_arch_reject-sandboxed`: `At index 11 diff:
  'activity:publish_artifact_version' != 'timer'`; captured list one item
  short (missing the final `apply_session_retention` after realignment).
- `waves-sandboxed`: same assertion class (`.workspace/tmp/nf-ff-run1.txt`
  on the fix branch worktree).

A different scenario can strike each run; single-scenario runs pass. The
golden pins ONE specific tick boundary of the gate notification schedule,
so the projection is load-sensitive by construction.

## Root cause (diagnosed in notify-flake's test.md, §mechanism)

The scenario drivers decide a gate on the FIRST 50ms real-time poll that
sees `awaiting:<gate>` (tests/replay/scenarios.py `wait_for`/`decide`),
racing the gate's next schedule-tick workflow task (the
notify/timer reminder sequence in `GateHost._wait_for_decision`,
src/sdlc/workflows/gates.py). Which task the server processes first under
load decides whether the history contains the next `timer` (and any
further `notify`), shifting every later command one index left.
budget_arch_reject's golden pins the decision to land between the escalate
notify (idx 10) and its following remind timer (idx 11):
`[... notify(8), timer(9), notify(10), timer(11), publish(12),
export(13), retention(14)]`. Nothing in the harness pins the driver to a
tick boundary.

## Evidence

- Baseline (clean main `2c732e0`, no fix changes): full-file run flaked
  with the IDENTICAL divergence on budget_arch_reject-sandboxed AND the
  old notify NotFoundError in the same log —
  `.workspace/tmp/nf-baseline-ff-run2.txt` (primary checkout scratch).
- fix/notify-flake after a8f9ac6: full-file runs fail ONLY with this
  divergence; zero "not registered" occurrences (branch worktree
  `.workspace/tmp/nf-ff-run1.txt`, `nf-diag-ff2.txt`).
- Per-scenario runs pass 15/15 (the race needs load); deterministic
  contract file green 77/77.

## Options for the orchestrator

1. Pin the drivers to a tick boundary (harness-only: wait until the gate's
   schedule for the round is consumed before signalling — e.g. a
   schedule-consumed status/trace hook, or wait_for a later tick marker).
2. Capture-time normalization (would touch goldens/projection — violates
   the notify-flake constraint set; listed for completeness only).
3. Other ruling.

Constraint set if taken up: harness-only (`tests/replay/**`), golden
byte-identity, no production semantics change — same as notify-flake's.
