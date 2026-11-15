# Verification — round 023a (DAPER maintenance loop: plans, gated, never acts)

Status: **complete** (T037 close-out). SC-001..007 mapping from the T036
battery outputs below, then the standing records. Battery commit `a39c97d0`;
every command run on the final tree.

## SC mapping (fixture/deterministic tier — the round's acceptance surface)

| SC | Evidence (test ids + battery outputs) | Verdict |
|---|---|---|
| SC-001 — baseline opens 0; 100% one incident per signal kind; recurrences attach | `test_workflow_us1.py::test_cycle_one_records_baseline_and_opens_nothing` (pre-existing findings → 0 incidents); `::test_a_break_becomes_one_incident_one_plan_one_gate` (build, e2e: exactly one); `test_workflow_us2.py::test_mechanical_reproduced_on_two_cycles_reaches_policy_approval` (secret/env, e2e: recurrence attaches — `seen_count` reaches 2 on the SAME incident, never a second one); `test_incidents.py` (all three kinds seeded through the real `step()`: `build_break_finding`, `env_file_findings`, `critical_advisory`; recurrence/attachment and prev-window flood cases). Advisory is unit-tier only by design: the workflow tier runs `advisory_source=none` (no OSV egress in tests) — recorded, not hidden. | **Met** on the fixture tier |
| SC-002 — zero repository writes by the loop | `test_workflow_us1.py` — `_repo_fingerprint` (`git for-each-ref` + status) asserted byte-equal across detect→plan→gate, snapshotted AFTER the test's own seeding commit (the honest boundary; noted in the test). | **Met** |
| SC-003 — zero timeout-approvals; no timeout-approve/policy-off enablement | `test_workflow_us2.py::test_silence_past_gate_timeout_times_out_never_approves` (silence past `gate_timeout_hours` → `timed_out`, `decided_by='timeout'`, never `approved_not_executed`); `test_cli.py` — `--gate-policy`/`--on-timeout` do not exist (argparse exit 2, R9), so no enablement can carry them. | **Met** |
| SC-004 — no overlapping cycles; no duplicate incidents/gates; one follow-up per burst | `test_workflow_us3.py::test_three_nudges_during_a_cycle_coalesce_into_one_follow_up` (burst of 3 → counter +2 exactly, verified stable after a settle window); `::test_worker_restart_mid_cycle_duplicates_nothing` (worker crash mid-cycle via cancelled run task + `max_cached_workflows=0`; exactly one incident, numbering intact). | **Met** |
| SC-005 — incidents + baseline survive roll-over byte-equal | `test_workflow_us3.py::test_history_rolls_over_at_idle_carrying_incidents_and_baseline` (`run_id` change proves `continue_as_new`; incidents `model_dump_json()` byte-equal at the boundary; baseline still recorded); `::test_pending_gate_defers_the_roll_over` (a pending gate defers, same history). | **Met** |
| SC-006 — replay fixtures and benchmark records byte-identical; fast tier at the recorded baseline | T036: `pytest -q tests/replay/` exit 0 and `git status --short tests/replay/` empty (fixtures untouched, byte-identical); fast tier's sorted-FAILED diff vs `baseline-failures.txt` **identical** after the one legitimate pin-move (`a39c97d0`: the worker-set pin gains 023a's two workflows — a pin travelling with its reviewed change, not drift). | **Met** |
| SC-007 — one live cycle | **Not run — the owner's run (quickstart §5)**, per the round's binding ruling: no paid cycle without the owner's word; the deterministic fixture tier above is the acceptance surface. | **Deferred to owner** |

## Standing records

- **Benchmark provenance (plan risk 5):** `PROMPTED_ROLES` is registry-derived
  (`src/sdlc/benchmarks/provenance.py:126`, the 012 ruling). The registry gains
  the `maintainer` role, so **new** benchmark records show `PROMPTED_ROLES`
  17 (was 16). Existing committed records are byte-identical (SC-006). This is
  a deliberate registry delta, not drift.
- **R11 outcome:** the EXISTING decision verbs resolve maintenance gates —
  `test_inbox_decide.py` part (b) passes over `channels/transport` on the
  temporal tier (`sdlc reject` → incident `rejected`, `decided_by='human'`,
  comment in `note`). The `sdlc maintain decide` fallback verb was **not
  needed and not built** (recorded at T023, `03b2bd42`).
- **SC-007:** owner's run — quickstart §5. The orchestrator asks at exec
  time; nothing paid ran in this round.
- **Threshold boundary (T025, carried):** the SOFT auto-approve fires only
  when `effective > threshold` (strict). R8's consequence is binding ("only
  mechanical findings reproduced on two consecutive cycles clear policy" at
  the default 0.8); `data-model.md` §R9's `>=` wording conflicts at the
  boundary and the research consequence won. Flagged here so 023b's
  data-model revision can align the wording.
  Correction (2026-11-15, 023b T051): the conflicting `>=` was in research
  R8 (its "Decider and auto-approve" bullet, now edited in place with a
  dated note), not in data-model §R9 — §R9 is the no-gates-field rule and
  never carried a threshold claim.

## PRD FR-501..503 re-read against shipped behaviour (T035, PRD untouched)

The PRD rows, verbatim:

> - FR-501: A per-project proactive workflow SHALL run the DAPER cycle on a
>   timer and on demand (nudge signal).
> - FR-502: Repair `code_fix` actions SHALL execute as brownfield factory runs
>   (children), never as direct patches; ops actions SHALL be risk-classed.
> - FR-503: Repair execution below the confidence threshold SHALL require
>   human approval via the standard gate contract; timeout SHALL mean inaction.

Mismatches found — all deliberate 023a/023b scope splits recorded in
ROADMAP/ARCHITECTURE, none silently dropped:

| Row | Shipped 2026-11-15 | Verdict |
|---|---|---|
| FR-501 | `MaintenanceWorkflow` (`maint-<p>`) runs baseline → detect → plan → gate per nudge, coalesced (R2); the timer half is the `MaintenanceKickWorkflow` schedule asset (E-14) — the schedule signals the same nudge, so "timer and on demand" is one mechanism, shipped. **The cycle's Execute and Report halves are not built (023b)** — the PRD's "the DAPER cycle" is half-met. Detect is narrower than the §7 design: triage signals only (CI, quarantined tasks, error budgets, deploy liveness are 023b+, banner records the narrowing). | Partial, recorded (ROADMAP FR-501 ⚠️) |
| FR-502 | Not built in 023a: no repair executes — approve lands `approved_not_executed`; ops actions are **proposal-only, never executed** (023a GATE 2 ruling); risk classes and brownfield children are 023b. The "never as direct patches" invariant holds vacuously — nothing patches. | Unmet, deliberate (023b) |
| FR-503 | The gate half is shipped: below-threshold plans (strictly `> threshold` auto-approves per R8 — an at-threshold plan stays human-gated) gate through the standard contract (`repair:<n>` SOFT, `detect_escalation` HARD), decidable via the existing inbox verbs; silence past `gate_timeout_hours` is `timed_out`, never approved (SC-003). "Repair execution" presumes execution — binding in 023b. | Gate half met; execute half 023b |
