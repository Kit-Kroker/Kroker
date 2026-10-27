VERDICT: approve

1. **T012 (tests/test_agents_registry.py)** — the task cites
   `_TARGET_MODELS["test"]` as the edit target. No `_TARGET_MODELS` exists
   anywhere in the tree (grep over `tests/`: zero hits); the constant is
   `_HARNESS_MODELS` (defined `tests/test_agents_registry.py:16`, the test
   entry at `:18`, consumed by the shipped-models assertion at `:93–97`).
   The line range (`:15–18`), the comment at `:15` and the docstring at
   `:70–71` are all exact — only the identifier is wrong. One-token fix
   (`_TARGET_MODELS` → `_HARNESS_MODELS`), but a cited edit target that
   does not exist is exactly what this review exists to catch, and T012 is
   the round's highest-blast-radius commit (the worker boot mirror).
2. **T012 (tests/test_registry_mirror.py)** — minor: the drifted value
   `zai-coding-plan/drifted` is cited at `:52`; it is at `:51` (`:52` is
   the closing paren). Unambiguous (single occurrence), off by one.
3. **T007 (tests/test_benchmark_corpus.py)** — minor: the `make_case`
   pattern is cited at `:188`; the `def make_case(...)` line is `:187`
   (`:188` is the first body line). Off by one.
4. **T038** — minor: "per the benchmark launch runbook" names no artifact
   in the tree (no file or section is called a runbook). The facts behind
   it are real — compose Temporal on 7233, `--build-arg KROKER_COMMIT`
   (`Dockerfile:125–127`), `sdlc benchmark run` documented in
   `BENCHMARK.md:783` — but the pointer should name where the recipe
   actually lives (BENCHMARK.md run section + Dockerfile).
5. **Dependencies (prose nit)** — "T003/T004 can run in parallel after
   T002" though both write sections of the same `baseline.md` and neither
   carries `[P]` (whose definition requires different files). The `[P]`
   system itself is consistent; the sentence should say interleaved/serial
   or drop the parallel claim.

# Tasks Quality Checklist: glm-5.2 Arm Retirement (round 019, pass 1)

**Purpose**: Validate tasks.md by spec-kit's checklist method — bite-sized,
dependency-ordered tasks with exact file paths, explicit test commands, no
placeholders, full requirement traceability — plus the reviewer brief's
cross-artifact checks (FR/SC coverage, plan-step and stop-guard reach,
RED-first ordering, format, [P] collisions, commit completeness, cited
targets).
**Created**: 2026-10-27
**Feature**: [tasks.md](../tasks.md) · [spec.md](../spec.md) ·
[plan.md](../plan.md) · [research.md](../research.md) ·
[data-model.md](../data-model.md) · [contracts/corpus-status.md](../contracts/corpus-status.md)
· [quickstart.md](../quickstart.md)

## Requirement Traceability (FR/SC → tasks)

- [x] CHK001 - Does every FR-001..FR-011 have at least one task?
  [Traceability, Spec §Requirements] — Yes: FR-001→T012/T017/T019–T025/T030
  + T041; FR-002→T019–T025/T030; FR-003→T011–T015; FR-004→T016/T017;
  FR-005→T027/T031; FR-006→T019–T025/T030 (comment values from
  baseline.md); FR-007→T027(a)/T028/T032; FR-008→T003/T040;
  FR-009→T007–T010; FR-010→T035–T039; FR-011→T038 (card, not executed).
- [x] CHK002 - Does every SC-001..SC-006 have at least one task?
  [Traceability, Spec §Success Criteria] — Yes: SC-001→T041; SC-002→T026
  (repo loads) + T032/T034 (private); SC-003→T028/T032 vs contract §2/§3;
  SC-004→T040; SC-005→T007 RED / T008 GREEN + T013/T042 vs baseline;
  SC-006→no-spend discipline (SG-7 binding) + T043's evidence table.
- [x] CHK003 - Are the GATE 1 rulings carried into task values (pair,
  per-case treatments, FR-006 note texts)? [Traceability, Spec §Rulings] —
  Yes: strong glm-5.3 / weak flash throughout; notes match the records
  (cat-cafe 0.8333 vs 0.4722 n=1; geotext 0.2222 vs 0.7778 inverted;
  readtime 0.2500 vs 0.1667 — all verified against `acceptance.yaml`;
  lice 30/31; theatre 0.0179 vs 0.0179; parked "not_assessed (parked)").

## Plan-step and stop-guard reach

- [x] CHK004 - Is every plan step 0–7 reached by tasks? [Traceability,
  Plan §Steps] — Yes: Step 0→T001–T006; Step 1→T007–T010; Steps 2–3→
  T011–T017; Step 4→T018–T029; Step 5→T030–T034; Step 6→T035–T039;
  Step 7→T040–T044.
- [x] CHK005 - Is every stop-guard SG-1..SG-8 reached by a task?
  [Measurability, Plan §Stop-guards] — Yes: SG-1→T040; SG-2→T027(a,b,d)/
  T028/T031; SG-3→T027(c)/T031; SG-4→T013/T042; SG-5→T014/T042;
  SG-6→T002; SG-8→T011. SG-7 is bound by the Conventions blanket
  ("SG-1..SG-8 is binding") plus the `C$`/quickstart §1 note (do not touch
  `kroker-dev` or the compose worker); no task does what it forbids.

## RED-first ordering and dependency order

- [x] CHK006 - Is FR-009 RED before GREEN (T007 before T008)? [Consistency,
  Plan rule 3] — Yes, with the exact failing set pinned (T1–T4 fail, T5–T7
  pass) and the RED output pasted into the report.
- [x] CHK007 - Is FR-004 RED before GREEN (T016 before T017)? [Consistency] —
  Yes; T016's call signature matches `build_case_dict(*, case_id, prd,
  contract, language, judge_model, network_required, repo_url)`
  (`deveval.py:201–210`) exactly, and the test file already imports it.
- [x] CHK008 - Are the real-case tests updated before the case edits (T018
  before T019–T025), failing first? [Consistency] — Yes; T018 runs the two
  rewritten tests against the unedited cases (must fail), T026 confirms
  green after the re-pairs. RED and fix commit together (T029), per plan
  rule 3.
- [x] CHK009 - Are phase dependencies stated and sound? [Clarity, tasks
  §Dependencies] — Yes, except the T003/T004 prose nit (gap 5); Phase 5
  after 3 and 4 is justified (re-label stamps the T017 HEAD; contract §3
  assumes FR-009 landed).

## Format, parallelism, commits

- [x] CHK010 - Does every task follow `- [ ] T### [P?] [US?] … path`?
  [Clarity, tasks §Format] — Yes; all 44 tasks carry an id, paths are
  concrete, [P]/[US] used where applicable.
- [x] CHK011 - Do any two [P] tasks touch the same file? [Consistency] —
  No: T016 (`test_deveval_importer.py`) ∥ T012 (five other files);
  T019–T025 (seven distinct `case.yaml`); T035/T036/T037
  (`BENCHMARK.md`/`README.md`/`config.yaml`). Verified against the Parallel
  Examples.
- [x] CHK012 - Does every commit task list every file its phase changes?
  [Completeness] — Yes: T001 (all 14 planning files, matching the
  checklists dir contents), T006, T010 (corpus.py + tests + BENCHMARK.md),
  T015 (the five FR-003 files), T017, T029 (7 case.yaml + 7
  acceptance.yaml + 2 test files), T033 (PRIV case + record), T039
  (BENCHMARK/README/config.yaml; the T038 card is outside git, stated),
  T044.

## Cited targets (spot-checks, 20+ verified)

- [ ] CHK013 - Do all cited identifiers and file:line targets exist?
  [Traceability] — All file:line targets verified: `agents/test/agent.yaml:3`,
  `models.py:375`/`:190`, `conftest.py:180`, `test_registry_mirror.py:58`/`:86`,
  `deveval.py:228`, `test_benchmark_corpus.py:18–26`/`:100–125`,
  `test_golden_case_loads.py:44–50`, `README.md:310`/`:316`,
  `config.yaml:6–13`, `matrix.py:136`, the 2026-10-02 marker
  (`BENCHMARK.md:20`), `build_case_dict` signature, the four named test
  files + `tests/doctor` all exist, `addopts` has `-q`
  (`pyproject.toml:122`), `make_case` at `:187`. But `_TARGET_MODELS`
  (T012) does not exist — gap 1; `:52` and `:188` are off by one — gaps
  2–3; the "benchmark launch runbook" pointer — gap 4.
- [x] CHK014 - Are the expected outputs in tasks consistent with the
  approved artifacts? [Consistency] — Yes: T027's checks (a)–(d) match
  contract §2 and data-model §2's gated fields including the pass-2 lice
  correction ("lice included" for the strong-arm check); T028/T032 match
  contract §3 (`0 of 8`, `0 of 2 private`, `EXIT_PRIVATE = 2`); T041 is
  quickstart §5.2 verbatim; T039 is quickstart §5 item 2a; T002's
  live-model expectation (`None`) matches quickstart §2.1.
- [x] CHK015 - Are any placeholders left (TBD/TODO/unfilled `<...>`)?
  [Completeness] — No; every `<id>`/`<file>` is a defined loop variable of
  its task.

## Pass 2

All five pass-1 gaps re-checked in tasks.md; all closed. No new gaps
introduced by the edits, so the verdict is approve.

1. **T012 identifier — closed.** tasks.md:178 now reads
   `_HARNESS_MODELS["test"]` (defined `:16`, entry `:18`), matching
   `tests/test_agents_registry.py` exactly (dict def at :16, the test-role
   entry at :18; the shipped-models assertion at `:93–97` consumes the
   dict, so the single entry edit propagates).
2. **T012 drifted-value line — closed.** tasks.md:183 cites `:51`, where
   `model="zai-coding-plan/drifted"` actually sits (`:52` is the closing
   paren).
3. **T007 make_case line — closed.** tasks.md:124 cites `:187`, the
   `def make_case(...)` line.
4. **T038 pointer — closed.** The non-existent "benchmark launch runbook"
   is replaced by concrete citations: "`BENCHMARK.md` run section near
   `:783`, and `Dockerfile:125–127` for the worker image built with
   `--build-arg KROKER_COMMIT`". Both verified: `BENCHMARK.md:783` is the
   run-modes row documenting `sdlc benchmark run`; `Dockerfile:125–127`
   is the `--build-arg KROKER_COMMIT` comment plus `ARG`/`ENV`.
5. **Dependencies prose — closed.** tasks.md:434 now says "T003 and T004
   run one after the other, because both write `baseline.md` sections, and
   they may run in either order after T002" — no parallel claim on a
   shared file, consistent with the `[P]` definition (neither carries
   `[P]`).

Touched-but-unaffected: the five edits were in-place single-line changes
(task ids, ordering, file lists, expected values and all other citations
unchanged — T038 still at line 369, the Dependencies block at 434), so the
pass-1 checks hold: FR/SC coverage, plan-step and stop-guard reach,
RED-first ordering (T007<T008, T016<T017, T018<T019–T025), format,
[P] non-collision, commit completeness, and the expected-output consistency
with contract §2/§3, data-model §2 and quickstart §5/§5.2 (T039/T041
references re-verified intact). File is proper UTF-8; a `§`/`–`/`≥`
rendering glitch seen in one console read was a PowerShell codepage
artifact, not file corruption.
