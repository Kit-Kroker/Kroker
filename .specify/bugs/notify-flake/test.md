# Bug Test: Replay-harness notify race — verification report

- **Slug**: notify-flake
- **Tested**: 2026-09-20
- **Fix**: ./fix.md (commit a8f9ac6 on `fix/notify-flake`)
- **Verdict**: partial — ACCEPTED by orchestrator ruling 2026-09-20 (on
  file): the brief's out-of-scope list explicitly excludes any other flake,
  the atomicity constraint binds, and the baseline evidence (identical
  divergence + notify error at clean 2c732e0,
  `.workspace/tmp/nf-baseline-ff-run2.txt`) is decisive. Follow-up card:
  `.workspace/tasks/golden-tick-race.md` (committed on this branch).

## Adjusted gate (ruling on file, 2026-09-20)

The verification gate for THIS slug, as adjusted by the ruling, is:

1. Deterministic contract: `tests/replay/test_notify_registration_chaos.py`
   **77/77 green** (was 29 RED / 48 green at base) — MET.
2. Per-scenario SG-1: **15/15 scenarios exit 0** — MET.
3. Golden byte-identity: zero changes under `tests/replay/golden/` +
   `tests/replay/histories/` (`git status` / `git diff main`), in-test
   count-freeze row green — MET.
4. **Zero `not registered` occurrences** in every branch full-file run log
   (the assessed race is eliminated) — MET.
5. Full-file failure mode is **tick-race-only** — MET (SG-3 divergence on
   waves/budget_arch_reject only; no other failure class observed).
6. 3× consecutive green full-file: **UNMEETABLE UNTIL golden-tick-race IS
   FIXED** — the same gate fails at clean main 2c732e0 (baseline run2
   evidence); ruling on file accepts this leg as blocked by the follow-up
   bug, not by this fix.

## What was verified (all green)

| Gate item | Command | Result |
|---|---|---|
| Deterministic contract (the RED gate) | `uv run --frozen pytest tests/replay/test_notify_registration_chaos.py -q` | exit 0 — **77/77 passed** (was 29 RED / 48 green pre-fix; `.workspace/tmp/nf-wt-{red-pre-fix,green-contract}.txt`) |
| Per-scenario SG-1 gate | `... pytest tests/replay/test_graph_golden.py -m temporal -q -k <scenario>` × 15 | **15/15 exit 0** (`.workspace/tmp/nf-ps-*.txt`) |
| Contract RED → GREEN flip | adopt commit 45a7275 vs fix commit a8f9ac6 | 29 assertion-RED at base → 0 failures after fix |
| Golden byte-identity | `git status` + `git diff main --stat -- tests/replay/golden tests/replay/histories` | **empty** — zero fixture changes; in-test freeze row also green |
| "not registered" race eliminated | grep across this branch's full-file logs | **0 occurrences** |
| Statics | `ruff check .` / `ruff format --check .` / `mypy` / `scripts/check_file_size.py` | all exit 0 |
| Fast pytest tier | `uv run --frozen pytest -q` | exit 0 |

## What is blocked, and why (not this fix)

The brief's gate requires 3× consecutive green full-file
`tests/replay/test_graph_golden.py` runs. On this branch:

- fullfile run1: exit 1 — `waves-sandboxed` + `budget_arch_reject-sandboxed`,
  SG-3 command-projection assertion (`.workspace/tmp/nf-ff-run1.txt`)
- fullfile run2 (diagnostic, `--tb=long`): exit 1 — budget_arch_reject-
  sandboxed, same assertion (`.workspace/tmp/nf-diag-ff2.txt`)
- no `not registered` error in either — the assessed race is gone

**Proof the blocker is pre-existing and out of scope**: two full-file runs
at main `2c732e0` (no branch changes, primary checkout):

- baseline run1: exit 0
- baseline run2: exit 1 — `budget_arch_reject-sandboxed`, **the identical
  SG-3 divergence** (`At index 11 diff: 'activity:publish_artifact_version'
  != 'timer'` / `Right contains one more item:
  'activity:apply_session_retention'`) **and** the old
  `NotFoundError: Activity function notify ... is not registered` in the
  same log (`.workspace/tmp/nf-baseline-ff-run2.txt`)

## Mechanism of the second race (diagnosis, for the ruling)

budget_arch_reject's golden pins the driver's architecture-reject signal to
land between the gate's escalate notify (idx 10) and its following remind
timer start (idx 11): `[... notify(8), timer(9), notify(10), timer(11),
publish(12), export(13), retention(14)]`. The driver decides on the FIRST
50ms real-time poll that sees `awaiting:architecture`; under full-file load
the status query and the workflow-task queueing decide whether the signal
task beats the next schedule-tick task. When it wins, the history is one
timer shorter and every later command shifts one index left — exactly the
observed diff. Nothing in the harness pins the driver to a tick boundary:
the interleaving is load-sensitive by construction. waves hits the same
class (its golden likewise pins a tick boundary under concurrent dev-task
load).

This is a DIFFERENT race from the assessed one (driver-vs-gate-schedule,
not worker-vs-unregistered-activity), it predates the branch (baseline
evidence above), and the brief's out-of-scope list explicitly excludes
"any other flake/hang".

## Options for the orchestrator

1. **Accept 'partial' for this bug** — assessed cause fixed, deterministically
   pinned, all in-scope gate items green; full-file gate re-measured after
   the tick race is fixed under its own slug. (Recommended: it is the brief's
   own scope rule, and the tick race demonstrably blocks the gate at main
   too — 3× green full-file is currently unmeetable on ANY branch.)
2. **Extend this slug** to also pin the drivers to tick boundaries
   (harness-only is still possible — the lever is `tests/replay/scenarios.py`
   drivers / wait_for). Expands the atomic change; needs an explicit scope
   ruling against the out-of-scope list.
3. Other ruling.
