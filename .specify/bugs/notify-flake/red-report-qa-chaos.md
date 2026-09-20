# RED-set report — qa-chaos seat (bug notify-flake)

- **Seat**: qa-chaos. **Date**: 2026-09-20. **Base**: main `2c732e0`, primary
  checkout (no fix worktree exists yet; the file is untracked for the
  bug-lead to commit with the RED set).
- **Charter**: edge cases around the fix surface (boundary values, error
  paths, concurrency, stale state), RED verified first, test files in
  `tests/` only.
- **Delivered**: `tests/replay/test_notify_registration_chaos.py` —
  44 collected, **29 RED / 15 green, exit 1**. All failures are
  assertion-class (`AssertionError` or pytest `Failed:`); zero errors, zero
  collection failures. Deterministic: pure inspection of scenario bundles +
  committed goldens; no Temporal, no server, no timers, no network.

## 0. Three findings that RESHAPE the brief (read before fixing)

Verified by a deterministic probe (`.workspace/tmp/notify-flake-chaos-probe.py`,
output in `-probe` run log) and pinned by the rows below:

1. **13 goldens schedule `activity:notify`, not 12** (34 schedulings — the
   count was right, the file count wasn't). The 13th is
   `partial_awaiting_architecture`: `Scenario.golden=False` excludes it from
   `GOLDEN_SCENARIOS`, but its golden file is committed, schedules notify 1x,
   and `test_fixtures_present.py` requires the file — any capture/replay of
   it rides the same worker.
2. **Only 6 of 16 scenarios use the two named helpers.** The candidate fix
   ("register in `_base_activities` AND `_budget_activities`") leaves **7
   notify-scheduling goldens red**: brownfield_happy, arch_timeout_reject,
   waves, seeded, research_greenfield, cancel_during_code,
   partial_awaiting_architecture all build INLINE activity lists. Binding
   constraint 1 ("every activity type the golden histories schedule") is the
   real contract; my rows enforce it per scenario so a helpers-only fix
   stays red.
3. **`research_greenfield` is ALSO missing `plan_research` — a real SCOPE
   fork** (brief: "today that is exactly notify" is wrong). Same race class
   (unregistered scheduled activity). Fork: the committed golden
   **memorializes the degraded research path** — `activity:plan_research`
   1x, and NO `research_subquestion`/`synthesize_brief` (the failure is
   caught at `stages/research/step.py:269`, run still closes `deployed:`).
   A WORKING plan_research fake changes the command projection → violates
   constraint 3 (golden byte-identity, no regeneration). Ruling needed:
   (i) a failing-compatible fake (raises non-retryable exactly like the
   unregistered path did → commands identical, race gone), or (ii) defer
   plan_research out of scope. Row map below is deliberately split so a
   ruling can quarantine the sweep row without weakening the notify rows.

## 1. Row map (axes → RED mechanism)

| Row (all in `test_notify_registration_chaos.py`) | Params | Axis | RED today via |
|---|---|---|---|
| `test_notify_is_registered_by_every_scenario_that_schedules_it` | 13 | completeness across bundle SHAPES (boundary) | `AssertionError: notify-flake race: <name> golden schedules activity:notify but its bundle (<_base_activities/_budget_activities/<lambda>) does not register it; a pending unregistered activity task is the WFT-collision race` |
| `test_no_activity_other_than_notify_is_left_unregistered` | 16 | general sweep, notify excluded so it stays separable under a ruling; also the stale-state guard for future scenarios | RED only on `research_greenfield`: `schedules ['plan_research'] its bundle does not register`; the 15 clean params PASS (the sweep is not vacuous) |
| `test_base_activities_registers_notify` | 1 | the assessment's minimum surface | `AssertionError: _base_activities() omits notify` |
| `test_budget_activities_registers_notify` | 1 | ditto, second helper | `AssertionError: _budget_activities() omits notify` |
| `test_registered_notify_fake_honours_the_results_contract` | 13 | error path + payload boundaries | `Failed: bundle registers no notify fake -- cannot assess its return contract` |

The fake-contract row pins, for every bundle that will register notify:
the fake must ACCEPT the production `NotifyInput` — built with the
optional-field boundaries `deadline=None` (HOLD) and `project=None`
(non-F4 host) — and RETURN the `Results` contract
(`sdlc.notify.contract`). Why this row exists: on success
`GateHost._notify` iterates `out.results` OUTSIDE its try/except
(`gates.py:166`), so a garbage-returning fake (`None`, a bare list) kills
the workflow on a path the "unresolved" fallback made unreachable; and
registering the PRODUCTION notify does not satisfy the row either (the
ruled fix is a no-op fake). `Results.model_validate(out)` accepts a
`Results` instance or an equivalent payload dict; rejects anything else.

Registered-name extraction reads temporalio's own
`__temporal_activity_definition.name` — the same metadata
`Worker(activities=...)` resolves; `fn.__name__` diverges for every
aliased fake (`fixed_price` registers as `price_usage`).

## 2. Iteration evidence

| Command (one pytest per Bash call, per run-ops lessons) | Result |
|---|---|
| `.venv/Scripts/python.exe -m pytest tests/replay/test_notify_registration_chaos.py -q` (full tb) → `.workspace/tmp/notify-flake-chaos-red.txt` | exit 1; 29 `FAILED` lines in short summary |
| same `-q --tb=no` → `...-red2.txt` | exit 1 (re-run after row tweaks) |
| `--collect-only -q` | `tests/replay/test_notify_registration_chaos.py: 44` |
| after `ruff format` re-ran → `...-red3.txt` | exit 1, 29 `FAILED` (RED stable) |
| `ruff check` / `ruff format --check` on the file | clean / clean |

The pytest counts summary line is eaten by the console host even when
redirected (known quirk, brief §Environment facts) — counts above are from
the `FAILED` short-summary lines + the collection count: 29 + 15 = 44.

Notify schedulings per golden (probe; total 34): greenfield_happy 3,
brownfield_happy 3, arch_revise_final 5, arch_timeout_reject 4,
plan_revise_approve 4, waves 3, seeded 1, budget_clarify_reject 1,
budget_arch_reject 2, research_greenfield 1, cancel_during_code 2,
max_gate_rounds_1 4, partial_awaiting_architecture 1.

## 3. Concurrency axis — honest coverage, nothing fabricated

Registration completeness IS the deterministic concurrency pin: no pending
task for an unregistered type can exist → no WFT collision. The stress
reproduction (full-file load) is nondeterministic by the task card's own
ruling ("per-scenario runs are the SG-1 gate; full-file runs are
flake-classified") and is supporting evidence, not a gate — no
threading/sleep rows were fabricated (canvas-run-mode chaos precedent §4.4).

## 4. Landing-green guards PROPOSED (not in the file — pure-RED charter)

1. **Duplicate-name guard**: the same activity name registered twice in one
   bundle is a Worker-construction error — the fix could introduce it by
   adding the notify fake in two places (e.g. inside
   `fake_agent_activities` AND the bundle). Probe: zero duplicates in any
   bundle today. If wanted, one row over all scenarios asserting
   `len(names) == len(set(names))`.
2. **Golden byte-identity**: constraint 3 is carried by the golden tests
   themselves + `git status`; a dedicated row would duplicate. Recorded
   here so the fixer knows it was considered, not forgotten.

## 5. Flagged for the bug-lead

- **SCOPE GATE (§0.3)**: plan_research ruling — failing-compatible fake vs
  defer. My sweep row stays red until either lands.
- **Concurrent tree change observed**: `M pyproject.toml` (setuptools
  package-data for `**/*.yaml`,`**/*.md`) appeared in the working tree
  during my run — NOT mine, not reverted, verify authorship before
  integration (concurrent seat).
- The 12-vs-13 and two-helpers-only traps in §0.1/§0.2 should feed the
  assessment correction (`.specify/bugs/notify-flake/assessment.md`).

## 6. Confirmations

- **Only `tests/replay/test_notify_registration_chaos.py` authored** (161
  lines, untracked, no commits made — bug-lead verifies and commits). No
  `src/`, no golden/history/scenario edits, no fixture churn.
- Scratch/evidence files under `.workspace/tmp/notify-flake-chaos-*`
  (probe script + three run logs) — orchestrator scratch surface.
- Statics: ruff check + format clean on the file; fast tier unaffected
  outside the new file's own RED.
