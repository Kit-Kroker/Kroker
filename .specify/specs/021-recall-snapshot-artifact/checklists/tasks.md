VERDICT: approve

One gap, doc-level, one table cell; no task's work, order or files changes.

1. **§Traceability, FR-001 row is incomplete (FR-001 → T024, T025 missing).**
   FR-001 requires persistence for recalls "healthy **or degraded**". T010
   implements only the healthy routing through `_persisted` — it says so
   explicitly ("Failure handling is done in T025 (US3)") — and the
   degraded-backend snapshot is routed through `_persisted` by T025, tested
   by T024(c) ("the degraded snapshot is persisted, with `ref` set and
   `persist_failed is False"). The row reads `FR-001 | T009, T010`, so the
   degraded half of FR-001 maps to nothing in the coverage table. Fix: the
   cell becomes `T009, T010, T024, T025`. (Same class as the plan pass-1
   gap 2: the row must name the tasks that implement the requirement.)

# Tasks Quality Checklist: RecallSnapshot persisted input (round 021, pass 1)

**Purpose**: validate tasks.md by spec-kit's tasks checklist method — strict
format, executability without extra context, dependency order,
traceability, no placeholders — plus the reviewer brief's consistency
checks (plan-id coverage, FR/SC coverage, GATE 2 rulings, no new activity,
test-first, `[P]` truth, story labels, path existence).
**Created**: 2026-11-11 | **Feature**: [tasks.md](../tasks.md) ·
[plan.md](../plan.md) (approved pass 2, GATE 2 applied) · [spec.md](../spec.md)
(GATE 1 + GATE 2 + FR-012) | **Base**: `main` at `067e1408`.

## Format

- [x] CHK001 - Is every task in the strict format
  `- [ ] Txxx [P?] [USn?] description with exact path`? [Clarity] — T001–T038
  sequential, ids unique, unchecked, every task names concrete paths,
  commands or both; new files explicitly marked new (three test files,
  `baseline-failures.txt`).
- [x] CHK002 - Placeholders? [Clarity] — None (sweep clean over tasks.md).

## Plan coverage (T010–T070 → tasks.md)

- [x] CHK003 - Is every plan task implemented and cited `(plan Txxx)`?
  [Traceability] — All 26 plan ids: T010→T002/T003, T011→T004/T005,
  T012→T006, T013→T009/T010/T024/T025, T014→T011/T012, T020→T007,
  T021→T013/T014, T022→T016/T017, T023→T017, T030→T019, T031→T020,
  T032→T021, T035→T022, T040→T018, T041→T028, T042→T004, T043→T002/T009/
  T011/T024, T044→T016/T027, T045→T013/T027, T050→T008/T026/T036,
  T060→T030, T061→T031, T062→T032, T063→T034, T064→T033, T070→T001/T035/
  T036. Nothing dropped. T015/T023/T026/T029 are run-checks validated
  against quickstart rows (Q1/Q2/Q4, Q3, Q2/Q5, Q6) — consistent with the
  020 convention.

## FR / SC coverage

- [ ] CHK004 - FR-001..FR-012 and SC-001..SC-005 covered? [Coverage] — All
  seventeen rows present; sixteen complete (FR-002→T002–T005; FR-003→T003
  no-edit + T008 unedited-files check; FR-004→T013/T014/T016–T021;
  FR-005→T009/T010; FR-006→T002/T024/T025; FR-007→T027/T029; FR-008→T024/
  T025; FR-009→T004/T008/T026/T036; FR-010→T016/T017; FR-011→T013/T014;
  FR-012→T009/T010; SC-001→T011–T014; SC-002→T016; SC-003→T029;
  SC-004→T024/T025; SC-005→T008/T026). **FR-001's row is incomplete**
  (gap 1): degraded persistence (T025, tested by T024c) is unlisted.

## GATE 2 rulings reflected

- [x] CHK005 - FR-001/SC-001 narrowed to `ctx.recall`? [Consistency] — Spec
  FR-001 rewritten ("stage-level … `ctx.recall` … `recall_leads` out of
  scope, GATE 2 ruling 2"); no task touches `recall_leads`; T032's roadmap
  note records the exclusion with its card.
- [x] CHK006 - T031/T032 use plan T061/T062 text? [Consistency] — T031
  replaces exactly the sentence range quoted in plan T061 ("Recall is
  itself a cached activity" … "point-in-time reads") and cites the same
  card; T032 ticks FR-402 and uses plan T062's note verbatim-by-reference.
- [x] CHK007 - Four cards checked, not created? [Traceability] — T033 only
  checks existence (STOP if missing), matching plan T064 ("done at GATE 2;
  the implementer only checks"). Verified in the tree: all four
  `.workspace/tasks/2026-11-11-{recall-snapshot-pinned-reuse,
  recall-leads-snapshot-and-degrade,memo-cache-tenant-scope,
  fakememory-nonnumeric-watermark}.md` exist.
- [x] CHK008 - `cache_put` kept for degraded stages? [Consistency] — No
  task removes or skips it; T016 only stubs `cache_get`/`cache_put` for the
  key test (GATE 2 ruling 5, research R-5).
- [x] CHK009 - FR-012 scrub implemented and tested? [Coverage] — T010 maps
  `scrub()` (`S/memory/scrub.py:18`) over the backend snapshot's items
  before hashing/persisting; T009 asserts a seeded `sk-` secret comes back
  scrubbed and the persisted bytes contain the scrubbed text; T011's
  round-trip keeps the invariant.

## Activity / command discipline

- [x] CHK010 - No task adds an activity or `workflow.patched`? [Consistency]
  — Stated as a binding rule (STOP on need); T010's `_persisted` is a
  module-level helper inside the existing activity; T012's reader is
  explicitly "not an `@activity.defn`"; T013 monkeypatches
  `workflow.execute_activity` (test-only).
- [x] CHK011 - Only T008, T026, T028, T029, T036 run `pytest -m temporal`?
  [Consistency] — Exactly those five (line 187 is a phase-goal header whose
  independent test is executed by T029); no task runs the `temporal` CLI;
  no git command writes (T029's `git diff --exit-code` is read-only).

## Test-first discipline

- [x] CHK012 - Tests precede implementation for every new behaviour?
  [Measurability] — T002→T003, T004→T005, T009→T010, T011→T012, T013→T014,
  T016→T017, T024→T025, each with "seen failing" phrasing. T027's
  pass-on-arrival is justified in place (it pins already-implemented
  behaviour; the commit message records it). T018/T028 are adaptations of
  existing tests, listed exactly, assertions unchanged.

## Parallel claims

- [x] CHK013 - Is every `[P]` true (disjoint files, no unmet dependency)?
  [Consistency] — T002∥T006∥T007 (new test file / store.py / trace.py);
  T009∥T013 (different test files); T016∥T024 (memo-key test vs
  artifact-test, US2∥US3 files disjoint per §Dependencies); T019∥T020∥T021
  (three stage files, after T017+T018); T027∥T028 (event/memo tests vs
  test_graph_golden.py); T030∥T031∥T032∥T033 (AGENTS.md / ARCHITECTURE.md /
  ROADMAP.md / existence check). Same-file sequels correctly unmarked
  (T004 after T002, T011 after T009 — both stated in §Parallel examples).

## Story labels

- [x] CHK014 - Labels match the spec's US1–US4? [Traceability] — Phase
  headers restate the spec story titles verbatim; [US1] on T009–T014,
  [US2] on T016–T022, [US3] on T024–T025, [US4] on T027–T028; setup,
  checkpoints and validations unlabelled, matching the 020 convention.

## Path and citation spot-checks (25+ verified at `067e1408`)

- [x] CHK015 - Do cited paths and `file:line` exist (or marked new)?
  [Traceability] — Verified: `S/workflows/memory_host.py:47` and the
  disabled branch `:50-51`; `S/memory/activities.py:51` (RecallInput),
  `:61` (`recall_snapshot`), `:91` (retain's scrub line, FR-012 spec cite);
  `S/workflows/role_host.py:88`, `:114-120`; `S/core/context.py:36-45`
  (Protocol with keyword-only `prompt_digest`); `S/core/models.py:92`
  (ArtifactRef); `S/artifacts/store.py:22` (`_SUBDIRS`);
  `S/observability/trace.py:16` (the enum; `MEMORY_RETAINED` at `:27`, so
  T007's "next to" anchor is valid); `S/memory/scrub.py:18`; stage call
  sites `clarify/step.py:199`, `plan/step.py:122`, `architecture/step.py:204`;
  clause anchors `clarify.md` after `:40`, `plan.md`/`architecture.md` after
  `:19` (all carry memo-key wording today);
  `T/replay/test_graph_golden.py:28-50`, `:121`, `:148` (the exact
  `args[-1] == "wm-e74"` assertion T028 replaces);
  `T/test_memory_models.py:12`, `T/test_memory_activities.py:61`
  (`test_recall_snapshot_degrades_on_backend_error`); the six stub cites and
  four `SimpleNamespace` cites of T018 (all exact, verified in the plan
  review); the pre-021 payload shape in T004 matches the recorded
  `research_retain_grounded.json` result (query-hash prefix, bank,
  watermark "0", empty items, `degraded:false`); the four GATE 2 cards
  exist; `CLAUDE.md`'s SPECKIT block already points at the 021 plan (T034's
  premise is true).

## Notes

- The task graph is sound: US1 MVP → US2 (memo key) → US3 (failure paths) →
  US4 (identity pins), with the artifact boundary honoured (T019–T021 and
  T022 ordered so the clause change ships with the behaviour change) and
  the replay signal checked three times (T008, T026, T036) before anything
  else moves.
- Fix the single FR-001 cell and this file is approvable without another
  full pass.

## Pass 2 (2026-11-11)

Gap 1 re-checked, plus the requested sweeps. **Resolved.**

1. **RESOLVED — FR-001 traceability cell.** tasks.md §Traceability line 251
   now reads `| FR-001 | T009, T010, T024, T025 |`. The degraded half of
   FR-001 (routing the outer-`except` degraded snapshot through
   `_persisted`) maps to T025 with T024(c) as its test, closing the one
   coverage hole.

Sweeps: placeholder sweep over tasks.md clean (TODO/TBD/TKTK/FIXME/???/
NEEDS CLARIFICATION: zero hits); id sweep clean — task ids T001–T036 all
defined and sequential, and the only T040+ ids (T040–T045, T050, T060–T064,
T070) appear inside `(plan Txxx)` citations, all defined in plan.md. No
stale references.

**tasks.md is approved.** All pass-1 checklist items (CHK001–CHK015) stand;
CHK004 now passes with the FR-001 cell complete.
