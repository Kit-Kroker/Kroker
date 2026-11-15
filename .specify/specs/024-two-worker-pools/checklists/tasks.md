VERDICT: approve

# Gaps (all non-blocking — none blocks execution; fix wording alongside normal task flow)

1. **[non-blocking] T012's dependency on T010 is unrecorded — tasks.md §Dependencies ("US4 (T011–T012) … can run after T003, in parallel with US2").** T012 calls `require_harness_poller`/`HarnessQueueUnpolled`, which are implemented in T010 — the *last* task of the US2 chain it is declared parallel to. A parallel executor following the prose hits an ImportError; numeric order protects a sequential one. Fix: state "T012 after T010" (T011 can stay parallel — it is stub-only).
2. **[non-blocking] T025's monkeypatch may not reach the call sites — tasks.md T025 ("Monkeypatch `sdlc.pools.on_harness`"), inherited from R7(a).** Patching the module attribute only bites if sites resolve `on_harness` via the module at call time; sites written `from ..pools import on_harness` (the natural style for T026/T027's `**on_harness(ACT, q)`) bind the name at import. Specify either module-qualified calls at the 33 sites, or patching the attribute in each of the 13 site modules (walk `sys.modules`). Failure is loud, not silent (the task's own "at least one forced queue was applied" assertion), so this is executability polish, not a correctness hole.
3. **[non-blocking] T017 and T031 are combined RED-then-fix / RED→green tasks**, while tasks.md §Tests declares only PROOF and docs as exceptions to "every implementation task is preceded by a RED test task". Add them to the declared exceptions (or split) so the stated rule and the task list agree.
4. **[non-blocking] T041's trust-layer diff names a non-existent path and a fruitless grep term.** `src/sdlc/containment` does not exist, and `pre_tool` appears in no `src/sdlc` Python file (it is a ROADMAP-level name, ROADMAP.md:573). `git diff --stat` tolerates the path and the task says to adjust the list by grep, so it remains executable — but the initial list should name the real trust surfaces (the harness module family, gates, `src/sdlc/graph/node_types.py`) or say "grep `-il containment src/sdlc`".
5. **[non-blocking, watch] T032 is the heaviest M** — five workflow-family drivers (a)–(e) under one two-worker server plus history assertions. The named reuse (`T/replay/harness.py`, `T/replay/scenarios.py`, `T/maintenance/conftest.py`, 023b's stub child, `S/demo/fakes.py`) keeps an M credible, but permit an in-round split of (a)–(e) into subtasks if it overruns one sitting, so the size summary does not hide an L.

**Reviewer-plan gaps carried into tasks:** plan-1 gap 1 → T019 (rollback remedy) + T042 (residual) ✓; gap 2 → T021 (`wc -l` ≤ 975) + T030 (`S/cli.py` ≤ 975) ✓; gap 3 → T018 + quickstart §5 (`config -q`) ✓; gap 4 → T020 runs §1a ✓; gap 5 → T032(e) ReflectWorkflow ✓; gap 6 → recorded in R1, no task needed ✓; plan-2 gap 7 (GATE 2 surface list) is a plan-level edit, not a tasks item. **None missing.**

---

# Tasks Quality Checklist: Round 024 — two worker pools (E-91)

**Purpose**: Validate `tasks.md` by the checklist method — format, RED ordering, coverage of every P-FR/SC and plan step, dependency/[P] correctness, split fidelity, size honesty, standalone executability — against the artifacts, the plan and the tree.
**Created**: 2026-11-15 (tasks pass 1) | **Actor**: SPEC & PLAN REVIEWER | **Depth**: formal gate

## Format

- [x] CHK001 - Does every task follow `- [ ] Tnnn [P?] [USn?] description (size)`, with sizes S/M declared and no L? [Clarity, tasks §Format + §Size summary] — verified: 42 tasks, `[P]` on T011/T013/T015/T017/T025/T035–T038, `[USn]` where a story owns the task, every task sized; the size summary's arithmetic (20+22, 28 S + 14 M) matches the list.
- [x] CHK002 - Are exact file paths used throughout (no bare "the worker file")? [Clarity] — verified; see CHK013–CHK015 for the line-level spot-checks.

## RED-before-implementation and PROOF

- [x] CHK003 - Is every implementation task preceded by a RED test task (or an in-task RED phase)? [Consistency, tasks §Tests] — verified: T002→T003, T004→T005, T006→T007, T008→T009, T011→T012, T013→T014, T015→T016, T022→T023, T024→T026/T027/T028, T029→T030. Two tasks (T017, T031) combine RED and fix inside one task — undeclared exception, noted as Gap 3, spirit preserved.
- [x] CHK004 - Do the PROOF tasks carry STOP clauses and no work-around instruction? [Completeness, tasks §Tests; T010, T039] — verified: T010 "If (b) or (c) cannot be made to hold, STOP and report: R6 is re-planned"; T039 "Any red here is a STOP, not a fix-forward". Matches plan risk 1.
- [x] CHK005 - Is T025's xfail mechanism sound (strict xfail while vacuous, internal forced-queue assertion, un-xfail at T028)? [Consistency, T025→T028] — verified as a coherent RED chain; the patch-binding mechanics are noted as Gap 2.

## Coverage

- [x] CHK006 - Is every P-FR-001..013 covered by ≥1 task? [Traceability] — verified: 001→T003/T008/T009; 002→T002–T005 (+T006 partition filters); 003→T006–T009; 004→T006/T008 (+T033 peak ≤ cap); 005→T022–T024/T032; 006→T028/T032; 007→T029–T031 (on T010's proof); 008→T011/T012; 009→T013/T014 (+T033 same-second starts); 010→T018; 011→T023/T025/T034; 012→standing constraints + T041 diff evidence; 013→T019/T035–T038/T040.
- [x] CHK007 - Is every SC-001..007 covered? [Traceability] — SC-001→T001/T020/T025/T041; SC-002→T032; SC-003/004→T033; SC-005→T031; SC-006→T034; SC-007→T020/T041 (+T021's `wc -l`).
- [x] CHK008 - Is every plan step A1..J2 mapped to a task (plan §Traceability)? [Traceability] — A1→T001, B1→T002/T003, B2→T004/T005, C1→T006/T007, C2→T008/T009, C3→T010, D1→T011/T012, D2→T015/T016, E1→T018, E2→T019, F1→T013/T014, F2→T017, F3→T020, G1→T021, G2→T022/T023, G3→T026/T027, G4→T028, G5→T024, H1→T029/T030, H2→T031, H3→T032, H4→T025/T034, H5→T033, J1→T035–T038/T040, J2→T041/T042. Complete.
- [x] CHK009 - Are the consult-derived items present (janitor flock, axis prune, barrier fake, rollback remedy, R12 notes)? [Coverage] — T015–T017, T033, T019, T019/T042 respectively.

## Dependencies and [P]

- [x] CHK010 - Does any [P] task share a file with a task it is parallel to? [Consistency, tasks §Dependencies + §Parallel] — no: T011/T013/T015/T017 touch four disjoint test-file pairs and disjoint source files; T025 (`T/replay/test_pools_replay.py`) ∥ T024 (`T/test_pools_call_sites.py`); T035–T038 are four distinct docs files. The shared-file sequencing section correctly serializes `S/pools.py` (T003/T007/T010), `S/worker.py` (T005/T007/T009), `S/stages/code/step.py` (T021→T026→T028), T027→T028 on three shared workflow files, and the two shared test files.
- [x] CHK011 - Are all semantic dependencies recorded? [Completeness] — one omission: T012 needs T010's function while being declared parallel to US2 → Gap 1. Everything else (T032 after T028+T030, T033 after T030, T034 after T028, docs after T030, proofs last) is stated and correct.

## Split fidelity

- [x] CHK012 - Do T001–T020 contain no routing wiring? [Scope, tasks §024-i; plan §Split] — verified: pools.py's helpers exist but are unwired; worker boot reads the queue env only to *boot* a second poller (plan-sanctioned pool existence); no start path, input field or call site changes; T019 carries the "routing lands in 024-ii" banner; T020 leaves ROADMAP NFR-2 untouched.
- [x] CHK013 - Does 024-ii need only 024-i? [Dependency] — T021–T042 consume only `S/pools.py`, the boot plan, the registration and T010's poller check, all from 024-i.

## Executability — spot-checks against the tree

- [x] CHK014 - Are the line references in T023/T026/T027/T028/T030 exact (floor: 10)? [Clarity] — all verified this session: the 8 model sites of T023 (core/models.py:369, triage.py:75, assessment.py:131, tidyup.py:77, deployment.py:66, crew.py:66, benchmarks/models.py:348, maintenance/models.py:84); all 19 graph/stage sites of T026; all 14 child-workflow sites of T027; all 11 inheritance sites of T028; T030's cli.py:793/839/889, benchmarks/cli.py:336, maintenance/cli.py:252, schedules/apply.py:62 and `graph/start.py:59`. ≥40 refs, zero misses.
- [x] CHK015 - Do T005's referenced pinning tests exist? [Clarity, T005] — verified: `tests/test_vcs_activities.py` exists and line 25 sits inside its pinned activity-name set (which includes `check_test_drift`); `tests/test_worker_registration.py` / `test_worker_registry_gate.py` exist for the `test_worker*.py` hint.
- [x] CHK016 - Do T021's five names exist in `src/sdlc/stages/code/step.py`? [Clarity, T021] — verified: `ACT` (:63), `LONG_ACT_HEARTBEAT_MINUTES` (:68), `LONG_ACT_TIMEOUT_HOURS` (:69), `LONG_ACT` (:70), `_long_act` (:93) — inside the stated "~60–105" band.
- [x] CHK017 - Does T012's target surface exist as described? [Clarity, T012] — verified: `check_temporal` at `doctor/checks.py:272-291` exactly, `_TEMPORAL_TIMEOUT_S` at :249, and the doctor row list with `Check("temporal", check_temporal, True)` at :397.
- [x] CHK018 - Are the docs-task anchors exact? [Clarity, T037/T038/T040] — verified: AP-2.5 at `docs/roadmap/agent-architecture-plan.md:41`; the session-resume boundary bullet at `docs/roadmap/crew.md:69-71`; ROADMAP NFR-2 at :462, the ADR-9 row at :527, §8 item 1 at :569.
- [x] CHK019 - Are the reuse anchors real? [Clarity, T001/T020/T032/T034] — verified: `tests/test_read_fixtures_fresh.py`, `.specify/specs/023b-daper-acts-verifies/baseline-failures.txt`, `tests/maintenance/conftest.py`, `tests/replay/harness.py`, `greenfield_happy` in `tests/replay/scenarios.py:614`, `crew/layouts/code.yaml:26` (5400 s).
- [x] CHK020 - Is T041's P-FR-012 diff evidence executable as written? [Clarity, T041] — partially: the command runs (git tolerates a non-matching pathspec) and the task orders a grep-driven adjustment, but `src/sdlc/containment` does not exist and `pre_tool` appears in no `src/sdlc` Python file → Gap 4 (non-blocking).

## Constraints and honesty

- [x] CHK021 - Do the standing constraints restate the repo rules (stage contracts, trust layer, replay fixtures, W-3, ceiling, no paid run)? [Consistency, tasks §Standing constraints] — verified, including the precise replay rule ("`git status --short tests/replay/` shows only new test files"), consistent with `tests/replay/AGENTS.md` rule 1.
- [x] CHK022 - Is any task secretly an L? [Measurability, §Sizes] — no: every M is bounded by a named file set or an enumerated assertion list; the only candidate, T032, is bounded by named existing harnesses → Gap 5 (watch).
- [x] CHK023 - Could a fresh executor run each task without extra context? [Clarity] — yes for all 42: each names its files, its test assertions, its grep anchors and its done-condition; the two soft spots are Gaps 2 and 4.

## Summary

- 23 checks; 21 pass clean; CHK003, CHK011, CHK020 carry the non-blocking Gaps 3, 1 and 4 respectively; Gap 5 is a size watch on CHK022, Gap 2 a mechanics note on CHK005.
- No blocking gap: coverage is complete (13 FRs, 7 SCs, 25 plan steps), the split is clean, ordering and parallelism are safe for a sequential executor and — with Gap 1's one-line fix — for a parallel one, and every mandated spot-check passed against the tree.
