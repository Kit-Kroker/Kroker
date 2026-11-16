# Implementation Plan: SC-2 instrument and fleet runs — round 025

**Branch**: none (shared tree; spec dir `025-sc2-instrument-fleet-runs`) | **Date**: 2026-11-16 | **Spec**: [spec.md](spec.md)

**Input**: spec.md (GATE 1 cleared 2026-11-16; amendments after consults at its end). Consults folded in: `consults/advisor.md` (D1–D7), `consults/skeptic.md` (A1–E3). `S/` = `src/sdlc/`, `T/` = `tests/`.

## Shape

**Two halves, one tasks.md.** Part A is normal SDD code (RED tests, review gates), size L, steps A–F. Part B is operations (steps G–K), **paid**, runs only after Part A is merged and verified, behind **GATE 2** (this plan's protocol and the ceiling) and then the owner's standing delegation, each run announced first. Part A touches no workflow code; Part B changes no code.

## Summary

The instrument is a **pure derivation from data a run already writes**:

1. `build_run_summary` (`S/observability/summary.py`) already receives every event with its `at`. `GATE_AWAITED` is emitted only when a gate actually opens for a human (`S/workflows/gates.py:237-244`); a SOFT gate that auto-approves emits none. So `raised_at` per `(gate, round)` is read from the trace and stored on `GateOutcomeSummary`. `CLARIFICATION_ASKED`/`ANSWERED` give a batch's raise and answer times (`S/workflows/question_host.py:60-106`). **No new event, signal or workflow code**, so no replay patch marker (advisor D1/D4).
2. The summary stores **raw times only** plus a marker `operator_instrumented`. A new pure module `S/benchmarks/operator_time.py` derives per-run operator time, owning the cap constant (600 s, Q1). Changing the cap re-derives, never re-runs (FR-004).
3. `S/benchmarks/sc_rollup.py` (275 lines) gains SC-2 rows via that module, supplementary lines and the commit set. `score.py` is unchanged except passing records through (already does).

## Technical Context

**Language**: Python 3.13. **Deps**: none new. **Storage**: none new; `RunSummary` JSON gains defaulted fields. **Testing**: fast tier for all of A (`pytest`), plus the existing replay/golden tests as the replay proof; no `-m temporal` test is added. **Ceiling**: every touched file stays far under 1000 lines (`core/models.py` 632, `summary.py` 199, `sc_rollup.py` 275).

## Constitution check

| Rule | Status |
|---|---|
| Cross-stage calls banned; producer owns artifacts | OK: `operator_time.py` lives in `benchmarks/` and imports `core.models` types only. `core/` gains fields on summary envelopes (envelopes are `core/`'s job per AGENTS.md) |
| Trust layer unchanged | OK: no gate, containment, pre_tool or policy code is touched (FR-009) |
| Chain replay byte-identical | OK by construction: only the pure summary builder and aggregation change (advisor D4). Proof: existing replay suite stays green (step E) |
| RED before implementation | Every code task has a RED task before it |

**Surfaced for GATE 2** (decisions the owner should see): (1) SOFT-tier evidence — whether P4 may close on it (spec FR-015); (2) the pre-existing SC-6 undercount if a merge override carries a reviewer name (advisor D1 hazard 1; logged, not fixed); (3) the fleet needs a dedicated clean checkout and a commit freeze from smoke to the last run; (4) cat-cafe's conditionality and the research provider's third-party spend; (5) no per-run budget switch exists, so the per-run stop is manual.

## Step list

- **A (models)**: `GateOutcomeSummary.raised_at`, `ClarificationOutcome.raised_at/answered_at`, `RunSummary.operator_instrumented` (all defaulted; additive). A pre-025 summary loads with the marker false.
- **B (builder)**: summary.py builds a `{(gate, round): at}` map from `GATE_AWAITED` after the dedup loop (not in `_ENRICH_OPTIONALS`), sets the marker true, and stamps clarification raise/answer times per question from the events.
- **C (derivation)**: `operator_time.py`: states `not_measured | zero | measured`; human = `decided_by` not in {policy, timeout}; clarification batches keyed `(stage, asked_at)` count once; engaged = min(decided − raised, cap); wait = uncapped; overlap noted as upper bound.
- **D (rollup)**: SC-2 (shipped) and SC-2-all rows, supplementary lines (zero-interaction count, human-touched median and max, uncapped wait median, SC-4 fraction beside, policy mix, evidence tier), n/a floor shared with `MIN_RUNS`; commit set by joining summaries to records on `run_id`, flagging BOTH more than one commit AND any summary with no matching record; renders markdown, HTML, JSON.
- **E (proof and docs)**: legacy-summary load test; fixture-dump drift check; replay suite; `docs/operations/fleet-runs.md` (protocol, announcement template, pre-registered case/infra rule, checklist); full battery vs the 11-failure baseline.
- **F (A close-out)**: verification.md §025-A.
- **G (pre-flight, GATE 2 → ops)**, **H (smoke)**, **I (runs)**, **J (report)**, **K (ROADMAP/P4 read)**: tasks T020 onward.

## Skeptic/advisor disposition

| Finding | Disposition |
|---|---|
| Advisor D1 derive `raised_at` from `GATE_AWAITED.at` | Adopted (A–B). Merge override covered by keying on `(gate, round)`; marker for legacy |
| Advisor D1 hazard 1 (`decided_by` may be a reviewer name) | Adopted: human = not policy/timeout. SC-6 undercount logged, not fixed |
| Advisor D2 batch = one interaction | Adopted (A.6, T005) |
| Advisor D3 scope = all human `GATE_DECIDED` + clarification batches; overlap = upper bound | Adopted; no interval union |
| Advisor D4 raw times in summary, cap in rollup, marker field | Adopted |
| Advisor D5 pre-authorise run 7; show human-touched median and max | Adopted (spec B.3, D) |
| Advisor D6 z.ai-only for deveval; smoke/cat-cafe need Anthropic; no `--no-judge` | Adopted (B.9). **Q3 answered: no judge-skip code**; verified by `check_smoke` (`S/benchmarks/smoke.py:78-88`). Adversary off by default (`core/models.py:465`); pre-flight asserts it |
| Advisor D7 expect few loops; don't pick cases for loops | Adopted; SC-3 n/a is a recorded miss |
| Skeptic A1 survivorship (shipped-only) | Adopted: SC-2-all companion; "at target" needs both (FR-012) |
| Skeptic A2 owner speed; cap hides effort | Partly: uncapped wait shown beside (FR-013). Self-reported effort note: **recorded in the per-run operator note**, not instrumented |
| Skeptic B1 SOFT vacuity | Adopted as evidence-tier line (FR-015); P4-close-on-SOFT surfaced for GATE 2. Not a block on rollup `MET` rendering: the owner already ruled SOFT with explicit reporting |
| Skeptic B2 suggested clarifications | Adopted: SC-4 beside SC-2 |
| Skeptic C1 n=6 vs floor | Adopted: pre-authorised run 7; SC-2-all has n=6 |
| Skeptic C2 smoke case padding | Adopted: todo-api is smoke-only, unscored |
| Skeptic C3 restart vs stop limit | Adopted: restart needs a fresh go; smoke is the pre-run integration check |
| Skeptic C4 commit provenance | Adopted via records join (no new `RunSummary` field) |
| Skeptic D1 post-hoc classification | Adopted: pre-registered binary rule + sensitivity row |
| Skeptic D2 concurrency vs stop | Adopted: sequential until two done, then ≤2; in-flight finish |
| Skeptic D3 SC-3 floor | Adopted: per-case loop counts + first-pass rate |
| Skeptic E1 smoke needs judge | Confirmed and adopted (B.9) |
| Skeptic E2 smoke runs both arms | Confirmed (`cli.py` `dispatch_smoke` has no arm filter): budgeted as two arms; failure stops for owner |
| Skeptic E3 ceiling from smoke proxy | Adopted: judge cost scaled by rubric count; z.ai is flat so no dollar line; per-run stop manual |

## Traceability

| Requirement | Step / task | Validation |
|---|---|---|
| FR-001/002 raise+decide recorded, no new events | A,B / T001–T004 | `tests/test_run_summary_build.py` |
| FR-003/004/005 operator time, cap, not-measured vs 0 | C / T005–T006 | `tests/test_operator_time.py` |
| FR-006/007/008 SC-2 row, note, policy mix | D / T007–T008 | `tests/test_benchmark_sc_rollup.py` |
| FR-009/010 no behaviour change, legacy loads | E / T011–T012 | legacy-load test; replay suite; battery |
| FR-011 rider | K / T033 | ROADMAP diff (path already correct) |
| FR-012..015 companions, commit set, evidence tier | D / T007–T010 | rollup tests |
| FR-020..025 protocol, pre-flight, announce, halt, one commit, fleet report | E,G–K / T013, T020–T033 | doc review; pre-flight evidence; announcements; fleet report |
| SC-A1..A3, SC-B1..B4 | F, J / T014, T032 | verification.md §025 |
