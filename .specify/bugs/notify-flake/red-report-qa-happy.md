# RED-set report — qa-happy seat (bug notify-flake)

- **Seat**: qa-happy (happy path). Worktree
  `D:\own\Kroker\.claude\worktrees\fix-notify-flake`, branch
  `fix/notify-flake`, base main `2c732e0`.
- **Date**: 2026-09-20. All RED observations below are from the pre-fix tree
  (no harness change has landed).
- **Scope kept**: one new test file, `tests/replay/test_activity_registration.py`
  — test files only, no production code, no golden/history file touched, no
  existing test edited or weakened. This report is the only other file
  written; it is left uncommitted for the bug-lead.
- **RED principle**: the race itself is nondeterministic by nature, so the
  gate is the brief's deterministic contract form — registration completeness
  against the committed goldens — pinned in the FAST tier (no Temporal
  server). The live-race demonstration is supporting evidence only.

## 1. Deliverable: tests/replay/test_activity_registration.py

43 test items: 12 gate-RED + 12 fix-surface-RED + 19 deliberate-green guards.

### RED carriers (24)

| Test (parametrized) | Count | Exact failing assertion |
|---|---|---|
| `test_every_scheduled_activity_is_registered[<scenario>]` — the GATE from the brief | 12 | `AssertionError: <scenario>: golden commands schedule ['notify'] but activities() does not register them. An unregistered scheduled activity races the next workflow task and fails it with "Activity function ... is not registered on this worker" (bug: notify-flake)` |
| `test_registered_notify_is_a_fake_returning_results[<scenario>]` — fix-surface contract | 12 | `AssertionError: <scenario>: golden schedules activity:notify but the scenario registers no notify; the pending task then races the WFT` |

The 12 scenarios (exactly those whose goldens contain `activity:notify`):
greenfield_happy, brownfield_happy, arch_revise_final, arch_timeout_reject,
plan_revise_approve, waves, seeded, budget_clarify_reject,
budget_arch_reject, research_greenfield, cancel_during_code,
max_gate_rounds_1. The gate test passes today on the three notify-free
scenarios (context_reject, delta_failed, intake_reject) — their workflows
reject before any gate opens.

The fake-contract test additionally pins, once a notify IS registered:
it must not be the production `sdlc.notify.activities.notify` (harness
purity — the production transport resolves real routes), it must accept a
valid `NotifyInput` (stage-gate variant), and its return must validate as
`Results` from `sdlc.notify.contract` — the shape `_notify`'s success path
iterates (`gates.py:150-167`).

### Deliberate-green guards (19)

- `test_core_activities_stay_registered[...]` (15): `evaluate_gate` +
  `export_run_artifacts` stay registered everywhere — the fix may only ADD
  registrations.
- `test_goldens_schedule_notify_exactly_as_pinned` (1): the golden file set
  (16 files) and the per-file `activity:notify` counts (34 schedulings
  total, matching the brief's number) are frozen — catches a golden
  regeneration or a production-side descheduling "fix" (constraint 3/4).
- Gate test on the 3 notify-free scenarios (3): proves the gate is about
  registration, not a blanket `notify`-must-exist rule.

## 2. Command evidence (pre-fix tree, base 2c732e0)

All pytest via `uv run --frozen pytest`, output redirected to the
orchestrator scratch (console host eats summary lines):

- `pytest tests/replay/test_activity_registration.py -v` →
  `.workspace/tmp/notify-flake-qa-red.txt` — **24 failed, 19 passed**,
  exit 1; every failure an `AssertionError` from the two intended
  assertions above; no errors, no collection failures.
- After two ruff auto-fixes (constant-`getattr` → attribute access,
  `timezone.utc` → `UTC`) + reformat, re-run on the final file →
  `.workspace/tmp/notify-flake-qa-red-final.txt` — **24 failed, 19
  passed in 22.37s**, exit 1. The committed bytes are the verified ones.
- Package context `pytest tests/replay/` (fast tier) →
  `.workspace/tmp/notify-flake-qa-replay-fast.txt` — **24 failed, 91
  passed, 48 deselected**: every pre-existing replay test green; the only
  failures are the new RED set.
- Statics: `uv run --frozen ruff check` + `ruff format --check` on the
  file — clean. (mypy is src/-scoped per repo baseline; tests excluded.)

## 3. Symptom demonstration (supporting evidence, not the gate)

One full-file run at HEAD, as the brief allows:
`pytest -m temporal tests/replay/test_graph_golden.py` →
`.workspace/tmp/notify-flake-qa-symptom.txt` — **32 passed in 109.65s**,
exit 0. The race did NOT strike this attempt. Recorded honestly rather
than chased: the brief says one flaky demonstration is enough and not to
chase repeats, and the card's evidence matrix already documents full-file
failures at baseline bf2383f AND at HEAD (a6d8d56: max_gate_rounds_1,
plan_revise_approve; budget_arch_reject at baseline). A clean pass at the
same HEAD is itself confirmation of the nondeterministic character. The
deterministic RED lives in the registration contract.

## 4. Finding for the fixer (brief correction, not a scope fork)

The brief's candidate-fix surface — "`_base_activities` AND
`_budget_activities` — both omit it" — is INCOMPLETE for the gate test:
only 6 of the 12 notify-bearing scenarios take their activities from those
two bundles (greenfield_happy, arch_revise_final, plan_revise_approve,
max_gate_rounds_1 via `_base_activities`; budget_clarify_reject,
budget_arch_reject via `_budget_activities`). The other 6 build INLINE
activity lists in `tests/replay/scenarios.py` that also omit `notify`:
brownfield_happy, arch_timeout_reject, waves, seeded, research_greenfield,
cancel_during_code. The fix must reach all 12 (e.g. a shared no-op notify
fake threaded into every list, or appended in each). Still harness-only
(`tests/replay/**`), so constraint 2 holds — no SCOPE GATE escalation
needed; this is a brief-precision note, and the gate test enforces it
either way.

## 5. No-production-code confirmation

`git status` in the worktree: exactly one new test file (committed, see
below) + this report (uncommitted, left for the lead). No `src/sdlc`
file touched — constraints 2 and 4 hold by construction; goldens and
histories untouched (constraint 3 — the counts pin guards it in-test too).

Tests committed as `b89e11e` ("test(replay): RED registration contracts
for the notify flake") on `fix/notify-flake` — 1 file, 149 insertions,
pre-commit hooks passed, subject + body only, no trailers per standing
ruling.

Seat clear: 43 items — 24 assertion-RED on the pre-fix tree (12 gate +
12 fix-surface), 19 deliberate guards green; deterministic, fast-tier,
no server required.
