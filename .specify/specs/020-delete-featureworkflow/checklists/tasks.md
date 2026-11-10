VERDICT: approve

All three pass-1 gaps are resolved (see "## Pass 2" at the end).

1. **T012 / T013 — missing `(plan T018)` citation.** Plan task T018
   (`LegacyRunError`, dashboard 410 / CLI exit 1 / operator tool error) is
   implemented by tasks T012 (tests) and T013 (implementation), but neither
   names it: T012 opens "Write the tests first for `LegacyRunError`" and
   T013 "Implement `LegacyRunError` …" with no plan id. Every other plan
   task T010–T092 is cited exactly once; T018 is the only executed-but-
   uncited one. Add `(plan T018)` to T013 (or T012).
   **→ RESOLVED in pass 2**: both T012 (tasks.md:214) and T013
   (tasks.md:220) now open with `(plan T018)`.
2. **T029 — missing `(plan T053)` citation.** Plan task T053 (rewrite
   `ARCH-1.x` / `PLAN-1.x` in `architecture.md` / `plan.md`, same commit as
   T052) is implemented by T029, which cites no plan id. T027 carries
   `(plan T052)`; T029 should carry `(plan T053)`.
   **→ RESOLVED in pass 2**: T029 (tasks.md:391) now opens with
   `(plan T053)`.
3. **Conventions (line 53) — stale task ids in the temporal rule.** "Never
   run any `temporal` CLI command except in **T034 and T061**." The gate
   tasks are **T016 and T036**; T061 does not exist (this file runs T001 to
   T038), and T034 itself says "No `temporal` command runs in this task".
   As written the rule licenses a nonexistent task and a bookkeeping task
   while not naming the only two tasks that may run the CLI. Must read
   "except in T016 and T036".
   **→ RESOLVED in pass 2**: the rule now reads "except in T016 and
   T036"; no `T034 and T061` / `T061` reference remains.

All three were one-line doc fixes; no task's work, order or files changed.

# Tasks Quality Checklist: Delete FeatureWorkflow (round 020, pass 1)

**Purpose**: validate tasks.md by spec-kit's tasks checklist method —
strict format, executability without extra context, dependency order,
traceability, no placeholders — plus the reviewer brief's consistency
checks (plan-id coverage, FR/SC coverage, blocking gates, replay-safety
and classification concreteness, ordering, `[P]` truth, story labels,
path existence).
**Created**: 2026-11-08 | **Feature**: [tasks.md](../tasks.md) ·
[plan.md](../plan.md) (approved pass 3) · [spec.md](../spec.md)

## Format

- [x] CHK001 - Is every task in the strict format
  `- [ ] Txxx [P?] [USn?] description with exact path`? [Clarity] — Yes:
  T001–T038, sequential, ids unique, every description names concrete
  paths, commands or both.
- [x] CHK002 - Placeholders? [Clarity] — None (TODO/TBD/TKTK/FIXME/???
  sweep clean over tasks.md).

## Plan coverage (T010–T092 → tasks.md)

- [x] CHK003 - Is every plan task implemented? [Traceability] — Yes, all
  32 plan tasks have work in tasks.md: T010→T003, T011→T004, T012→T005,
  T013→T006, T014→T007, T015→T009, T016→T010, T017→T011, T018→T012/T013,
  T019→T014 (+T015), T030→T016, T040→T017, T041→T018, T042→T019,
  T043→T020, T044→T021, T045→T024, T046→T022/T023, T050→T025, T051→T026,
  T052→T027, T053→T029, T054→T030, T059→T031, T070→T026, T080→T032,
  T081→T033, T082→T034, T089→T035, T090→T036, T091→T037, T092→T038.
  Nothing dropped.
- [ ] CHK004 - Does each cite `(plan Txxx)`? [Traceability] — 30 of 32
  cite; **plan T018 (T012/T013) and plan T053 (T029) do not** (gaps 1–2).

## FR / SC coverage

- [x] CHK005 - FR-001..FR-016 covered? [Coverage] — FR-001→T016;
  FR-002→T036; FR-003→T025; FR-004→T008/T009/T010/T011; FR-005→T024;
  FR-006→T030; FR-007→T027/T028/T029; FR-008→T022/T023 (plus the plan's
  analysis table); FR-009→T022/T023; FR-010→T017–T021; FR-011→T019;
  FR-012→T003+T026; FR-013→T032; FR-014→T033; FR-015→T009 (kept wire +
  fixture regeneration) and T033's SC-002 grep (allowed-list entries);
  FR-016→T034.
- [x] CHK006 - SC-001..SC-007 covered? [Coverage] — SC-001→T016/T036/
  T037/T038; SC-002→T033 (grep pasted to verification §SC-002); SC-003→
  T019; SC-004→T020+T031; SC-005→T008+T037; SC-006→T014/T031; SC-007→T032.

## Gate discipline

- [x] CHK007 - Are the gate re-runs (T016, T036) BLOCKING with a STOP?
  [Measurability] — Yes: T016 "**FAIL is a STOP**: … start no Phase 6
  task"; T036 "**FAIL is a STOP**: no deploy, and no `v*` tag"; the
  runbook's pass rule has no override.
- [ ] CHK008 - Does no other task run a `temporal` command? [Consistency]
  — The gate tasks are the only temporal users, but the standing
  convention (line 53) names the wrong ids ("T034 and T061"), one of
  which does not exist and the other of which denies running temporal
  (gap 3). T037 uses `docker compose` only; T022/T023 replay via pytest.

## Concreteness

- [x] CHK009 - Replay-safety work concrete? [Clarity] — T022 names the
  test, the history, the marker-strip rule (`MARKER_RECORDED` events with
  `e74-graph-child:` ids) and the RED expectation; T023 names the exact
  replacement (`deprecate_patch`), the deletions and the docstring update.
- [x] CHK010 - 76-file classification concrete? [Clarity] — T003: five
  classes, `path::test_name` counterpart format for every `delete`,
  per-`migrate` replacement note, tally line totalling 76; T026 executes
  it one commit per class with `pytest -q` against the T002 list.

## Ordering

- [x] CHK011 - Re-capture before any PR-2 `src/` edit? [Consistency] —
  Phase 6 (T017–T021) precedes the first PR-2 `src/` edit (T023); T018
  additionally guards itself with `git diff --stat main -- src/` empty.
- [x] CHK012 - Inbox removal after gate run 1? [Consistency] — T024 sits
  in Phase 7, after the Phase 5 gate (T016); the plan's rationale (hidden
  pending gates while runs drain) is preserved.
- [x] CHK013 - Dependency order otherwise sound? [Consistency] — Yes,
  including: T025 before T026 (imports break only in the window the
  classification commits close; no full-tier run happens in between);
  T027+T028+T029 as one commit; T031 (full verification) after T026 —
  which fixes the plan's Phase C/D ordering wart; T035 → T036 → T037.

## Parallel claims

- [x] CHK014 - Is every `[P]` true (disjoint files, no unmet dependency)?
  [Consistency] — T004/T005/T006/T007: disjoint test files. T011 after
  T009's wire, frontend only. T022 vs T024: disjoint files in Phase 7.
  T032/T033: `S/workflows/AGENTS.md` vs docs, disjoint. The PR-1 example
  correctly serialises the one shared file (`S/dashboard/api.py`: T010 vs
  T013).

## Story labels

- [x] CHK015 - Labels match the spec's stories? [Traceability] — US1 =
  fresh gate evidence (T016/T036/T037); US2 = no grace-edit tax (Phase 8);
  US3 = legacy rows (Phase 3); US4 = goldens (Phase 6); US5 = replay-safe
  restart (Phases 4/7). Setup/verification/bookkeeping tasks are
  unlabelled, matching the plan.

## Path and citation spot-checks (20+ verified at `d57c381d`)

- [x] CHK016 - Do cited paths and `file:line` exist (or marked new)?
  [Traceability] — Existing, verified: `T/replay/test_feature_replay.py`,
  `T/replay/harness.py` (incl. `FEATURE_STARTER`, `_start_feature`,
  `_feature_workflows`), its three replayer importers, the six helper
  files at the cited lines, `T/calibration/test_gate_requires_calibration.py`,
  `T/test_soft_gate_auto_approval.py`, `T/calibration/test_calibration_plumbing.py`
  (:188–202), `S/workflows/graph_nodes/{gate,precode}.py`,
  `T/replay/histories/greenfield_happy.json`,
  `T/durability/test_priced_usage_parity.py`, `T/replay/test_graph_golden.py`,
  `T/replay/test_graph_golden_chaos.py:61-70`, `T/test_dashboard_fleet.py`
  (`_ORDER_BY_SUPPORTED` at fleet.py:64), `T/test_dashboard_api.py`,
  `T/test_channel_transport.py`, `T/test_operator_errors.py`,
  `S/operator/tools.py`, `T/graph_workflow/test_pipeline_child_upgrade.py`
  (`StubFeature`), `S/workflows/pipeline_child.py`, `S/channels/inbox.py:91/:111`,
  `T/test_worker_registration.py`, `S/worker.py:3/:122/:286`,
  `T/graph_workflow/test_cold_import.py`, `test_store_import_pin.py`,
  `T/review/test_adversary_workflow.py:151`,
  `S/stages/{architecture,plan}/step.py:279/:174` and both `__init__.py`
  (`_StageModule`, `"step"` in `__all__`, `__getattr__` branch),
  the four slice/step-split test files at the cited line ranges,
  `S/stages/architecture/architecture.md`, `S/stages/plan/plan.md`,
  `S/workflows/role_host.py:327`, `S/workflows/AGENTS.md` (grace section;
  `_codebase_map`/`_base_sha`/`_integration_wt`/`_integration_head` rows),
  `docs/roadmap/pipeline-as-data.md`, all four `FE/` paths. Explicitly
  new: `T/replay/test_capture_graph.py`, `T/replay/test_graph_replay.py`,
  `T/replay/AGENTS.md`, `scripts/check_golden_rebaseline.py`,
  `T/durability/fixtures/priced_usage_pre_e74.json`,
  `T/test_cli_legacy_run.py`, and the two `.workspace/tasks/` cards (T034).
  One ordering nit, not a gap: T030's comment cites the
  `2026-11-08-revisable-stage-deletion.md` card that T034 (Phase 9)
  creates later in the same PR.

## Notes

- The three gaps are citation-level; the work, order, files and gates are
  correct. Fix line 53 and add two `(plan …)` citations, and this file is
  approvable without another full pass.

## Pass 2 (2026-11-08)

The three pass-1 gaps re-checked. **All resolved.**

1. `(plan T018)` now cited by both implementing tasks: T012
   (tasks.md:214, tests) and T013 (tasks.md:220, implementation).
2. `(plan T053)` now cited by T029 (tasks.md:391, the primary-checkout
   clause rewrite).
3. The conventions rule reads "**Never run any `temporal` CLI command
   except in T016 and T036.**"; the stale `T034 and T061` wording is gone
   and no `T061` reference remains anywhere in the file.

Plan-id coverage re-verified after the edits: all 32 plan tasks
T010–T092 are now cited exactly once (T045's citation sits inside T024,
wrapped across two lines: "(plan T045, FR-005)"). Nothing else in
tasks.md changed — format, FR/SC coverage, gate STOPs, ordering,
`[P]` claims, story labels and the 20+ path spot-checks from pass 1
stand as recorded.

**tasks.md is approved.**
