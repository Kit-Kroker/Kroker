# ROADMAP — Last-verified log

Per-round verification history moved verbatim out of the `Last verified` cell of
[`ROADMAP.md`](../../ROADMAP.md) (task `2026-11-03-roadmap-last-verified-log`).
Newest first; **append new entries at the top** — never edit the ROADMAP cell
beyond its one-sentence latest entry. The final entry (2026-10-11, Phase 3) is
out of date order as inherited; left as-is.

Trailing note carried by the old cell: (docs(benchmarks): the axis in the living docs (T010))

## 2026-11-11

2026-11-11 (round 021, FR-402 RecallSnapshot closed — MVP + US2 + US3 + US4 executed per tasks.md T001-T036: every stage-level `ctx.recall` now scrubs its items (FR-012, the same hook retain uses), re-hashes over the scrubbed content with the one shared definition (`memory/query_hash.recall_snapshot_canonical`/`recall_snapshot_hash`, `recall_snapshot/v1` wire tag), and persists idempotently as `<root>/<run_id>/recall/<hash>.json` via `LocalFileStore` inside the existing `recall_snapshot` activity — no new command, no `workflow.patched` anywhere; `RecallSnapshot` gains defaulted `snapshot_hash`/`ref`/`persist_failed` + a validator, so pre-021 recorded results and the checked-in memory-on history replay unedited (FR-009/SC-005); `MemoryHost._recall` passes `run_id` and emits `MEMORY_RECALLED` (hash/uri/flags, never items) through a getattr-guarded `ReportHost._emit` cross-read; `read_recall_snapshot` reads back verified (ValueError on foreign kind or hash mismatch); the memo key's fifth slot extends the watermark with the snapshot hash through an escape-joined `wm|ref` (separator-free inputs encode exactly as the plan's plain join — the verbatim join was forgeable and the QA suite pinned unforgeability; empty ref keeps the pre-021 key byte-for-byte, FR-007); persistence or backend failure degrades to an item-free, distinctly-hashed, never-raising snapshot (FR-006/008), the double fault included; degraded answers stay cached but under their own key (GATE 2 ruling 5); `MEMO_PARITY_KEYS` deliberately re-pinned to `wm-e74|<degraded hash>` — FakeMemory cannot parse `wm-e74` (R-4, card filed) — captured, not hand-computed, goldens byte-identical; evidence: quickstart Q1-Q6 green, replay suite 35 passed with fixtures untouched, fast tier at its recorded baseline; residuals: `recall_leads` excluded (ruling 2, card), live-Hindsight re-runs miss by design (ruling 1, card, ADR-5 corrected), memo-cache tenant scope and the FakeMemory watermark cards filed)

2026-11-11 (FR-105 closed by PRD amendment, no code change — the shipped merged fix loop IS the design: re-verified against `stages/code/step.py` — one loop, `budget = max_fix_attempts + 1` (`:550`), `_fix_loop_issues(qa, qa_raw, review, adversary)` folding deterministic tests + clean-context QA + review/adversary blocking findings into one repair prompt (`qa/step.py:68`, consumed `code/step.py:896`); conditional session resume `_should_resume_session` (`:161-166` — stack mismatch / context ceiling / FR-802 `max_session_resumes=3`), operator revise resets the session (`:934`); test-drift backstop escalates directly, spending no attempts (`:898-905`); exhaustion → `task:{id}` human gate (`:916-966`) with revise bounded by `max_gate_rounds` — and against `stages/analyze/` (analysis runs once post-integration, `AnalysisReport` carries no verdict, untraced criteria surface as the advisory `traceability` check at merge `merge/step.py:455-464`; no analyze→code edge in `graphs/default.graph.yaml:32-34`), so the "review/analyze → Developer repair" clause is met by the review half per-task and by merge-gating for the analyze half; PRD FR-105 rewritten to describe this — one loop, default `max_fix_attempts=2`, conditional resume, analyze gates at merge — superseding the spec-v2 two-loop design (Developer 2 / Resolver 3); the "Resolver" was never a separate role, `PipelineConfig.roles` carries only dev/test/devops harness roles; decision recorded as ADR-25 (`docs/adr.md`); the number stays 2 deliberately — no local benchmark records justify 3 and the knob is a calibration input (`fix_attempt_label`, `calibration/labels.py:37`), the per-task `fix_attempts` records are the instrument to revisit it; BENCHMARK.md §4.3 drift note closed; `code.md` CODE-1.5 verified accurate, unchanged)

2026-11-11 (FR-106 re-checked against actual code and flipped to done, with §1 stage 12 — 12 of 15 stages live: `src/sdlc/gate.py` carries the pure absolute/advisory classification with `ABSOLUTE_FLOOR` (`security_no_critical` + `security_scan_collected`, FR-915) re-asserted on input and the 9-entry `MERGE_REQUIRED_CHECKS` manifest where a missing name synthesizes a failing MISCONFIGURED check at its manifest classification (C3; the old stage-12 row still said "7 checks" — `plan_drift` landed 2026-09-09 `c88a0ce3` and `review_lenses_present` 2026-09-10 `00f2d32a`); `stages/merge/step.py` fails absolute closed (`rejected:merge:absolute-gate-failed`, no override path), routes advisory failures to the human merge gate as audited `GateOverride`s, and consults `MergeVerdict` only under SOFT policy after a clean pass; the four absolute checks are built from `ScopedTestReport`/`ScopedLintReport`/`ScopedSecurityReport` measured between the pinned base and the integration head (`stages/merge/scoping.py`, MERGE-1.10) with diff coverage computed from `changed_files` (`merge/activities.py`); `stages/analyze/` enforces criterion→test traceability propose-vs-enforce (`untraced_criteria`); evidence: 158 tests green across `test_quality_gate`, `test_security_floor`, `test_security_collection_gate`, `merge/test_scoped_absolute_checks`, `test_untraced_criteria`, `test_measure_coverage`, `test_scoped_lint`, `test_scoped_tests`, `test_scoped_security_scan`, `test_integration_checks`, `tests/merge/`, `tests/analyze/`; residuals stay open where they belong — coverage advisory and vacuous until `coverage_threshold` is set (default 0.0, `core/models.py:418`, config not defect), non-Python diff-scoped absolute checks wait on E-30a/b/c (FR-108, additive off the critical path), per-criterion outcome recording is the E-51/E-52 data gap, metric traceability is FR-1103/E-66)

## 2026-11-10

2026-11-10 (round 020, FeatureWorkflow deletion: PR-1 and PR-2 executed end-to-end on `020-delete-featureworkflow-2`; every replay fixture re-captured from GraphWorkflow with a provenance-only golden diff; the replay suite, worker registration, inbox types and slice contracts re-pointed; fast tier back to its 8-id known baseline and the temporal tier chunked green with only the four ruled priced-usage drift failures; gate 1 cleared on the empty-store ruling; awaiting gate 2 + worker restart)

## 2026-11-03

2026-11-03 (R019 follow-up paid re-prove series closed — both arms rerun on one commit `7a43462c`, 3 valid cycles per case: the `glm-5.3` / `glm-5.3-flash` pairing does **not** separate — cat-cafe 0.829 vs 0.704 (margin 0.125, n=6/arm), geotext 0.667 vs 0.593 (0.074), theatre 0.018 vs 0.018 (0.000), readtime `not_assessed` (flash died at clarify 3/3); tally stays **0 of 8** but now on live same-commit evidence; weak-arm fragility systemic (7 lost weak runs); arm re-selection is the recorded follow-up (flash-strong-no-weak or cross-provider pair under ADR-6); two defects fixed mid-series on main: hindsight recall ceilings 30s→120s/100s (`5d888d38`) and the registry adversary moved to `anthropic:claude-sonnet-5` (`7a43462c`) — its model id collided with the new weak arm and silently killed every weak cell at the ADR-6 boundary; verdicts on main `9a302401`, theatre in the private store `64a96ac`, break marker in BENCHMARK.md)

## 2026-10-29

2026-10-29 (round 018 canvas-v5 UI closed - the console is v5: six screens over `@kroker/ui` (Fleet, inbox, run page Graph/Board/Cost, Graphs catalog + Design editor, Compare, Interfaces), the retired v4 surfaces deleted with tombstones (stage dots, fleet table rows, the yaml/schema editor panes, CONSOLE-3/7), four stateless read routes (`/fleet/summary`, `/graphs/shipped`, `/compare`, `/interfaces`) served through `register_read_routes` and recorded into fixtures the mock replays (rule 4), the palette commands-only with every v5 command live, and FR-601 closed - the Gates-tab placeholder is superseded by the rail/header/inbox surfaces; verification in the spec round's verification.md)

## 2026-10-26

2026-10-26 (round 017 baseline-unlock closed — the pre-AP0 unlock, BIP-4.2 groundwork: the analyze stage no longer auto-rejects every benchmark run (report F8) — criteria are traced by a static test/file/task_unchanged/command inventory under `ANALYZE_EVIDENCE_PATCH="017-analyze-evidence"` with inexpressible criteria recorded as a plan-authoring result; runs now carry `StageReach`/`tasks_total`/`blocking_checks` and two same-stage stalled arms grade `not_assessed: stalled` instead of a misleading near-zero (R1's 1/56 shape); research spend reaches the trace, `RunSummary.roles`/`stages` and the stage record via a dead-attempt ledger, never entering the budget gate's bag (FR-034 split, BENCHMARK.md A-1); `plan_drift` ignores generated dirs; `plan` models ignore generated artifacts in drift; the paid pre-flight `bench-todo-api-greenfield-1793006961` on `b23f2514` verified SC-001/SC-002 MET ($2.17 — the coding harness died on an opencode-bootstrap EBUSY `models.json` mount, fixed `e9d8c348`, so the first clean baseline number is still to be taken); glm-5.2 smoke arms retired for glm-5.3/glm-5.3-flash (`2e813a28`, catalog erratum `ac58b434`))

## 2026-10-19

2026-10-19 (spec 016 decomposition case closed — `1e697522`: the second private case authored in an isolated store (`SDLC_PRIVATE_CASES_ROOT`, two-root resolver, leak-guard hook, opt-in raw-stream capture, judge output budget, `run_tree_check`, tier/feature on requirement mappings, `decomposition_report.py`); oracle identity `a66c0c4e` hand-reviewed (56 tests, reference 56/56, floor 0/56, 18 ablation patches + a framework-free variant green); R0 smoke passed on the fifth attempt — the first four surfaced two main bugs fixed via bug crews (golden-tick race `2b2f175b`, heatmap 0/0 marks `1e697522`) and lost opencode-auth mounts restored to the override; R1 ran both arms — flash and glm-5.2 each graded **1/56** with the run dying at `merge`, margin 0 → theatre-box-office **rejected no_separation** at n=1; honest tally unchanged at **1 of 8 accepted or provisional, 1 of 2 private** (cat-cafe, provisional); a captured opencode stream is scrubbed into `tests/fixtures/opencode/` (FR-041 unblocked); verification in the spec round's verification.md)

## 2026-10-17

2026-10-17 (spec 015 corpus acceptance, run half closed — R4-r2 `fa1d58a1`: R0 smoke passed on pin `64cd9f54` attempt 14; R1 screen kept deveval-geotext 0.778 and deveval-readtime 0.167, parked hone (saturated) and stocktrends (degenerate), pso lost twice at plan-validation (dangling task deps, a registered proposer defect class); R4 erratum + R4-r1 relabeled the arm pair on public-benchmark evidence — glm-5.3-flash strong, glm-5.2 weak; R4-r2 regenerated the acceptance records offline from the stored cells (the flash-arm runs had already executed 2026-10-16 under the old labels): cat-cafe-monitoring **provisional** (flash 0.833 vs 5.2 0.472, margin +0.361, n=1/arm), deveval-geotext and deveval-readtime **rejected no_separation** — the honest tally is **1 of 8 accepted or provisional, 1 of 2 private**; verification in the spec round's verification.md §8–§10)

## 2026-10-11

2026-10-11 (spec 015 erosion and verbosity, Phase 2 item 2.9 landed: a second objective quality axis — erosion as the CC>10 share of complexity mass, verbosity as rule-flagged lines over LOC, both from the produced diff at the integration head at run end — stored as one `scope=AXIS` record per started cell, read through the run model into two grid columns, group means per rule-set version and one totals clause, never entering a quality, composite or gate figure; every pre-015 run reads `n/m(no record)` on the axis forever; verification in the spec round's verification.md)

## 2026-10-10

2026-10-10 (spec 013 benchmark scoring output, Phase 2 of the benchmark improvement plan landed except item 2.9: stored records are read through a run model, `report.md` opens with the run-by-run grid, the heatmap is four layers with fixed colour scales and grey under five observations, each gate is compared against the oracle, the success criteria are computed from the scored runs' own summaries, the score command and the end-of-run report share one writer, stored opencode waste counters read as not measured with a capture mark on new digests, and the opencode stream parser (FR-041) is open pending a captured stream; verification in the spec round's verification.md)

## 2026-10-08

2026-10-08 (spec 012 benchmark record trustworthiness, Phase 1: record provenance, cell records, one file per cell, per-grade oracle environments, attempt-record timings/verdicts, rejection causes, and pre-012 untrusted marking all landed, verification in the spec round's verification.md; fast tier green bar three known git-trio failures, temporal replay identical to baseline; three smoke runs recorded, one cell record and one file per cell confirmed live and the empty-score defect proven fixed live on clarify, the last run aborted on a shared-Hindsight read-timeout (infra) and the round closed on that evidence)

## 2026-10-06

2026-10-06 (spec 011 cost visibility + run budget: FR-601 re-checked, the Cost tab is built (interfaces/dashboard/frontend/src/features/cost/) and FR-601 stays open on Gates only; FR-701 re-read with budget-at-start and the gate counted scope; SC-10 re-checked, unchanged; CLI --budget-usd and the dashboard start form budget field confirmed live)

## 2026-10-06

2026-10-06 (FR-305, FR-601, FR-603 re-checked for the decision-inbox landing, spec 010: the inbox screen is built and resolves all four kinds, the CLI `inbox` verb confirmed live, FR-601 kept open on the unbuilt Gates and Cost tabs)

## 2026-09-12

2026-09-12 (P2 demonstrated end-to-end: diff-scoped gates landed `90fa513`…`b56a009`, brownfield run `merged-not-deployed:PR #16`, operator-merged `45aa2b8`; FR-106's absolute checks now judge the change against the pinned base)

## 2026-09-11

2026-09-11 (FR-601, FR-704 and NFR-4 re-checked against `interfaces/dashboard/frontend/src/views/` and `src/sdlc/observability/`)

## 2026-09-02

2026-09-02 (E-50 against `src/sdlc/{assessment/gates,dispositions}` + `workflows/assessment.py`, full unit suite + temporal e2e green, four final-review defects fixed and re-verified)

## 2026-08-17

2026-08-17 (E-49 plan 3 against `src/sdlc/assessment/risk/crosscap.py` + unit suite and Temporal e2e green)

## 2026-08-16

2026-08-16 (E-49 plan 2 against `src/sdlc/assessment/risk/`, `agents/risk/`, `src/sdlc/assessment/verification.py`, Temporal e2e green)

## 2026-08-16

2026-08-16 (E-49 plan 1 against `src/sdlc/assessment/risk/` + unit suite green)

## 2026-08-14

2026-08-14 (E-47c against `src/sdlc/assessment/discover/` + `src/sdlc/assessment/scan/naming.py` + unit suite green)

## 2026-08-13

2026-08-13 (E-47b against `src/sdlc/assessment/discover/` + `src/sdlc/assessment/scan/configpaths.py` + unit suite green)

## 2026-08-13

2026-08-13 (E-46 plan 3 + review fixes against `src/sdlc/assessment/scan/`, unit + temporal e2e green)

## 2026-08-13

2026-08-13 (E-46 plan 3 against `src/sdlc/assessment/scan/` + unit suite green)

## 2026-08-13

2026-08-13 (E-46 plan 2 against `src/sdlc/assessment/scan/` + unit suite green)

## 2026-08-10

2026-08-10 (E-45 against `src/sdlc/{assessment,workflows/assessment.py,triage/admission.py}` + unit/e2e tests green)

## 2026-08-09

2026-08-09 (E-44 against `src/sdlc/{tidyup,workflows/tidyup.py,triage/delta.py}` + unit/component tests green; E-42 against `src/sdlc/workflows/{gates,triage}.py` + `pytest -m temporal`, with three review defects fixed; E-47a 2026-08-08 against `src/sdlc/capability/`; E-78 2026-08-07 against `src/sdlc/board/`; E-40/E-43 2026-08-06; the rest 2026-08-05, against `src/sdlc/`, `interfaces/`, `tests/`, `config/`, `agents/`)

## 2026-10-11

2026-10-11 (spec 015 corpus acceptance, Phase 3 of the benchmark improvement plan: code half complete; oracle identity tracking, smoke command and run gate, root-cause matrix and labels, cat-cafe grown to 36 tests with reference solution, acceptance checking command, corpus status command and Phase 3 exit tally implemented; offline acceptance records committed for the seven corpus cases; honest tally stands at 0 of 8 accepted or provisional, 0 of 2 private; awaiting run phase R0–R3 clearance)
