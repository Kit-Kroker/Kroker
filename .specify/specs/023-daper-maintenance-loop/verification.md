# Verification — round 023a (DAPER maintenance loop: plans, gated, never acts)

Status: **in progress** — the PRD re-read (T035) is below; the SC-001..007
mapping from T036's battery outputs, the provenance note and the standing
records (R11, SC-007) are appended by T037 at close-out.

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
