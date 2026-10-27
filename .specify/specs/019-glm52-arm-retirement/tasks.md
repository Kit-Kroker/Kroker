# Tasks: glm-5.2 Arm Retirement (round 019)

**Status**: Reviewer-approved (tasks checklist, pass 2, 2026-10-27).
- **Pass 1**: fixes-needed with 5 gaps: a wrong identifier in T012, three
  off-by-one or vague citations, and the Phase 1 parallelism prose. All
  were fixed.
- **Record**: [checklists/tasks.md](checklists/tasks.md).
- **Commits**: none yet. T001 commits every planning artifact, by
  convention.

**Input**: `.specify/specs/019-glm52-arm-retirement/` â€” spec.md (GATE 1
approved, all defaults), plan.md (reviewer-approved pass 2), research.md
(D-1..D-9), data-model.md (Â§1â€“Â§4), contracts/corpus-status.md (Â§1â€“Â§3),
quickstart.md (Â§1â€“Â§5).

**Tests**: required where code changes. Two places are RED first, per
plan rule 3: FR-009 (contract Â§1) and FR-004. Test edits that pin real
cases (D-8) are made before the case edit, so they fail first and then go
green.

**Conventions for every task**:
- `WT` = `D:\own\Kroker-019glm52retire`.
- `PRIV` = `D:\own\sdlc-private-cases`.
- `C$` = run inside the quickstart Â§1 throwaway container. Never run
  `uv sync` there. Use `uv run --no-sync â€¦`.
- **Commit recipe**:
  1. Write the message to a file in the session scratchpad, never in the
     repo.
  2. `git add <path>` once per path (one path per argument).
  3. `git commit -F <file>`.

  The message is a subject line and a body. No trailers of any kind.
- No `--no-verify`. If a pre-commit hook rewrites files, re-add exactly
  those paths and commit again.
- A stop-guard (plan Â§Stop-guards, SG-1..SG-8) is binding. On fire: stop,
  leave the tree as it is, report to the orchestrator.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no unmet dependency).
- **[Story]**: US1 (no dead model), US2 (truthful records), US3 (record of
  why).

---

## Phase 1: Setup (pre-flight, plan Step 0)

- [x] T001 Commit the planning artifacts. Paths, one per `git add`:
  - `.specify/specs/019-glm52-arm-retirement/spec.md`
  - `.specify/specs/019-glm52-arm-retirement/plan.md`
  - `.specify/specs/019-glm52-arm-retirement/research.md`
  - `.specify/specs/019-glm52-arm-retirement/data-model.md`
  - `.specify/specs/019-glm52-arm-retirement/quickstart.md`
  - `.specify/specs/019-glm52-arm-retirement/tasks.md`
  - `.specify/specs/019-glm52-arm-retirement/contracts/corpus-status.md`
  - `.specify/specs/019-glm52-arm-retirement/checklists/requirements.md`
  - `.specify/specs/019-glm52-arm-retirement/checklists/plan.md`
  - `.specify/specs/019-glm52-arm-retirement/checklists/tasks.md`
  - `.specify/specs/019-glm52-arm-retirement/checklists/reviewer-brief-plan-1.md`
  - `.specify/specs/019-glm52-arm-retirement/checklists/reviewer-brief-tasks-1.md`
  - `CLAUDE.md`
  - `.specify/feature.json`

  Subject: `docs(spec): round 019 glm-5.2 arm retirement - spec, plan, tasks`.
  The body names GATE 1 (all defaults, 2026-10-27) and the reviewer
  approvals.
- [x] T002 Re-probe the live catalog per quickstart Â§2.1, a read-only
  `docker exec kroker-worker-1`. Record the seven zai-coding-plan rows in
  `.specify/specs/019-glm52-arm-retirement/baseline.md` Â§Catalog.
  **SG-6** fires if `glm-5.3` or `glm-5.3-flash` is not `None` (live).
- [x] T003 Write `.specify/specs/019-glm52-arm-retirement/baseline-records.sha256`.
  - Content: one line per file under `D:\own\Kroker\runs\benchmarks`,
    format `<sha256>  <forward-slash path relative to runs/benchmarks>`,
    sorted by path.
  - Host-side, read only. Use a script in the session scratchpad, not the
    repo, and run it with Python's `-I` flag.
  - Record the file count in `baseline.md` Â§Manifest.
- [x] T004 Fill `.specify/specs/019-glm52-arm-retirement/baseline.md`
  Â§Records. For each of the seven repo cases (`benchmarks/cases/<id>/acceptance.yaml`)
  and `PRIV/cases/theatre-box-office/acceptance.yaml`, record from the
  `git show HEAD:` (or `git -C PRIV show HEAD:`) content:
  - verdict, reason and note;
  - separation strong and weak arm, means and run ids;
  - `not_comparable`, `oracle_id` and `kroker_commit`.

  These values feed the FR-006 comments (data-model Â§1).
- [x] T005 `C$` (quickstart Â§1, `KROKER_COMMIT` = current HEAD8). Record in
  `baseline.md`:
  - **Â§Corpus**: the full output of `uv run --no-sync python -m sdlc.cli benchmark corpus`.
    Expected tally: `1 of 8 accepted or provisional`.
  - **Â§Fast tier**: `uv run --no-sync pytest`, the pass/fail counts and
    every failing node id.
  - **Â§Replay**: the result of `uv run --no-sync pytest -m temporal tests/replay`.

  Do not add an extra `-q`, because addopts already has it.
- [x] T006 Commit `.specify/specs/019-glm52-arm-retirement/baseline.md` and
  `.specify/specs/019-glm52-arm-retirement/baseline-records.sha256`.
  Subject: `docs(019): pre-flight baseline - catalog, records, manifest`.

**Checkpoint**: the baseline is on record. Nothing else has been touched.

---

## Phase 2: Foundational

None. US2's staleness rule (Phase 3) has no prerequisite beyond Phase 1.
It runs before the re-label (Phase 5) so that the window between edit and
re-label is already covered by drift detection.

---

## Phase 3: User Story 2, part A â€” arm-drift staleness (FR-009, plan Step 1) ðŸŽ¯ code

**Goal**: `benchmark corpus` marks a record stale when its separation arms
no longer match the case's arms (data-model Â§3).

**Independent test**: `uv run --no-sync pytest tests/test_benchmark_corpus.py -k arm_drift`.

- [x] T007 [US2] RED. Add seven tests to `tests/test_benchmark_corpus.py`,
  named `test_arm_drift_t1_strong_changed`, `â€¦_t2_weak_changed`,
  `â€¦_t3_weak_newly_declared`, `â€¦_t4_no_strong_record_now_declared`,
  `â€¦_t5_null_separation_never_arm_stale`, `â€¦_t6_parked_not_arm_stale` and
  `â€¦_t7_unchanged_is_fresh_and_counted`, exactly per contract Â§1.
  - **Helper**: a local `_arm_case(cases_root, cid, role, strong, weak, rec_strong, rec_weak, separation=True, verdict="provisional")`.
    - Writes `case.yaml` with two arms when both strong and weak are set,
      or one arm when weak is None. Each arm has `role_models: {dev: m, test: m, devops: m}`.
      Also `models: [m]` and `judge_model: j`.
    - Writes a stub `oracle/test_sample.py`.
    - Calls `save_acceptance` with `oracle_id=oracle_identity(oracle_dir)`
      and `separation=SeparationCheck(strong=ArmEvidence(arm=rec_strong) if rec_strong else None, weak=ArmEvidence(arm=rec_weak) if rec_weak else None)`,
      or `separation=None` for T5.
    - Follows the existing `make_case` pattern at `tests/test_benchmark_corpus.py:187`.
  - **T6**: the parked record uses the sentinel
    `SeparationCheck(passed=None, detail="separation not assessed for parked case")`.
  - **T7**: assert that `render_corpus_status(rows)` counts T7's
    provisional row and not T1's. Build T1 and T7 in one cases root.
  - **Run**: `C$ uv run --no-sync pytest tests/test_benchmark_corpus.py -k arm_drift`.
    It **must** show exactly T1â€“T4 failing and T5â€“T7 passing. Paste the
    output into the task report. If the result differs, stop and report;
    do not adjust the expectations.
- [x] T008 [US2] GREEN. In `src/sdlc/benchmarks/corpus.py` `corpus_status()`,
  inside the `else:` branch, after the oracle-drift `if/elif`, add the
  arm-drift check (data-model Â§3, research D-6).
  - `spec.role == CaseRole.CORPUS`, `record.separation is not None`, and
    the recorded `(strong arm or None, weak arm or None)` tuple differs
    from `(spec.strong_arm, spec.weak_arm)` â†’ `stale = True`.
  - Never overwrite an oracle-drift `True` with `False`.
  - Extend the docstring's "Stale logic" list with the new bullet.
  - It must work in both branches (`cases_root` given, and `None` / both
    roots), because both build `spec`.
  - **Run**: `C$ uv run --no-sync pytest tests/test_benchmark_corpus.py`.
    All green.
- [x] T009 [US2] In `BENCHMARK.md`, in the section that documents the
  corpus status / Stale column (find it with
  `grep -n "Stale\|stale" BENCHMARK.md`), add one sentence. Stale now has
  two causes: oracle drift and arm drift (the record's separation arms â‰ 
  the case's `strong_arm`/`weak_arm`). Add the two known limits
  (research D-6): names only, and `separation: null` records are exempt.
- [x] T010 [US2] Run `C$ uv run --no-sync ruff check src/sdlc/benchmarks/corpus.py tests/test_benchmark_corpus.py`,
  `uv run --no-sync ruff format --check src/sdlc/benchmarks/corpus.py tests/test_benchmark_corpus.py`
  and `uv run --no-sync mypy`. Then commit `src/sdlc/benchmarks/corpus.py`,
  `tests/test_benchmark_corpus.py` and `BENCHMARK.md`.
  Subject: `feat(benchmarks): corpus status marks arm drift stale`. The
  body cites FR-009 and the REDâ†’GREEN evidence.

**Checkpoint**: `benchmark corpus` on the unedited tree still prints
`1 of 8` and no stale row. Research D-6 says no row flips today; check it
with `C$ â€¦ benchmark corpus` and diff against `baseline.md` Â§Corpus.

---

## Phase 4: User Story 1, part A â€” shipped defaults (FR-003, FR-004, plan Steps 2â€“3)

**Goal**: no shipped default names glm-5.2.

**Independent test**: the worker's registry mirror tests and the importer
test pass. `grep -nE "^[^#]*glm-5\.2" agents/*/agent.yaml` prints nothing.

- [x] T011 [US1] Read `src/sdlc/core/AGENTS.md` before touching
  `src/sdlc/core/models.py`. If it states a rule this edit breaks, stop
  (SG-8).
- [x] T012 [US1] FR-003 test role flip, in one change set:
  - `agents/test/agent.yaml:3` â†’ `model: zai-coding-plan/glm-5.3`
  - `src/sdlc/core/models.py:375` â†’ `"test": RoleConfig(harness=HarnessKind.OPENCODE, model="zai-coding-plan/glm-5.3"),`
  - `tests/conftest.py:180` mirror fixture â†’ `model: zai-coding-plan/glm-5.3`
  - `tests/test_agents_registry.py:15â€“18`: `_HARNESS_MODELS["test"]` (defined `:16`, entry `:18`) â†’
    `"zai-coding-plan/glm-5.3"`. Update the comment at line 15 and the
    docstring at `:70â€“71` to say test moved to glm-5.3 in round 019.
  - `tests/test_registry_mirror.py:58`: the assertion that the error names
    the `PipelineConfig` default becomes `"zai-coding-plan/glm-5.3"`. The
    drifted value at `:51`, `zai-coding-plan/drifted`, stays.
  - `tests/test_registry_mirror.py:86`: the mirrored `"test"` RoleConfig
    becomes `model="zai-coding-plan/glm-5.3"`.

  Leave `src/sdlc/core/models.py:190` (`# e.g.` comment) as it is (out of
  scope).
- [x] T013 [US1] Run `C$ uv run --no-sync pytest tests/test_agents_registry.py tests/test_registry_mirror.py tests/test_cli_role_model.py tests/doctor`
  (all green), then the full fast tier `uv run --no-sync pytest`. Compare
  against `baseline.md` Â§Fast tier. **SG-4** fires on any new failure.
- [x] T014 [US1] Run the replay gate:
  `C$ uv run --no-sync pytest -m temporal tests/replay`. **SG-5** fires if
  it is red and was green at T005.
- [x] T015 [US1] Commit `agents/test/agent.yaml`, `src/sdlc/core/models.py`,
  `tests/conftest.py`, `tests/test_agents_registry.py` and
  `tests/test_registry_mirror.py`.
  Subject: `agents: move the shipped test role to zai-coding-plan/glm-5.3`.
  The body says glm-5.2 is catalog-deprecated, cites Q3=A, and records the
  risk that test == dev model (research D-7).
- [x] T016 [P] [US1] RED for FR-004. Add
  `test_build_case_dict_default_model_is_glm_5_3` to
  `tests/test_deveval_importer.py`. It calls
  `build_case_dict(case_id="x", prd="# t\nline", contract="c", language="python", judge_model="j", network_required=False, repo_url="/srv/x")`
  and asserts `["models"] == ["zai-coding-plan/glm-5.3"]`. Run
  `C$ uv run --no-sync pytest tests/test_deveval_importer.py -k default_model`.
  It must fail.
- [x] T017 [US1] GREEN. Change `src/sdlc/benchmarks/importers/deveval.py:228`
  to `"models": ["zai-coding-plan/glm-5.3"],`. Re-run T016's command
  (pass), then `uv run --no-sync pytest tests/test_deveval_importer.py tests/test_deveval_corpus.py`.
  Commit `src/sdlc/benchmarks/importers/deveval.py` and
  `tests/test_deveval_importer.py`.
  Subject: `fix(benchmarks): DevEval importer defaults to glm-5.3`.

**Checkpoint**: shipped defaults are clean and the fast tier is at
baseline.

---

## Phase 5: User Story 1, part B + User Story 2, part B â€” repo case re-pair and re-label (FR-002, FR-005, FR-006, FR-007, plan Step 4)

**Goal**: seven repo cases declare the Q0 pair. Each `acceptance.yaml` is
re-labelled with no spend and matches contract Â§2.

**Independent test**: contract Â§2 lines plus data-model Â§2 gated fields
per case, and contract Â§3 `benchmark corpus`.

- [x] T018 [US1] RED. Update the real-case tests to the new pair:
  - In `tests/test_benchmark_corpus.py`, rename `CORPUS_BASE_CELL_IDS`
    (`:18â€“26`) to `CORPUS_WEAK_CELL_IDS`. Its values become
    `<id>#opencode#zai-coding-plan-glm-5.3-flash`.
  - In `test_seven_corpus_cases_have_two_arms_and_matching_base_cells`
    (`:100â€“125`), assert:
    - `strong_arm == "zai-coding-plan-glm-5.3"`;
    - `weak_arm == "zai-coding-plan-glm-5.3-flash"`;
    - the arm set is `{"zai-coding-plan-glm-5.3", "zai-coding-plan-glm-5.3-flash"}`;
    - `weak_cell.cell_id == CORPUS_WEAK_CELL_IDS[cid]`;
    - `strong_cell.cell_id.endswith("#zai-coding-plan-glm-5.3")`.

    Replace the R4-r1 comment with an R019 comment that says cell ids come
    from arm names (`matrix.py:136`), not `models:`.
  - In `tests/test_golden_case_loads.py:44â€“50`: strong cell
    `cat-cafe-monitoring#opencode#zai-coding-plan-glm-5.3`, weak cell
    `cat-cafe-monitoring#opencode#zai-coding-plan-glm-5.3-flash`, with the
    same comment fix.
  - Run `C$ uv run --no-sync pytest tests/test_benchmark_corpus.py tests/test_golden_case_loads.py`.
    The two rewritten tests must fail. Paste the output.
- [x] T019 [P] [US1] Re-pair `benchmarks/cases/cat-cafe-monitoring/case.yaml`
  per data-model Â§1:
  - `strong_arm`, `weak_arm`, `arms`, `models`;
  - delete the `extra_args_by_model` block including its comment line;
  - add the FR-006 comment block above `strong_arm:`, with values from
    `baseline.md` Â§Records: "provisional, flash 0.8333 vs glm-5.2 0.4722,
    n=1".
- [x] T020 [P] [US1] Re-pair `benchmarks/cases/deveval-geotext/case.yaml`
  per data-model Â§1. Its FR-006 note is "rejected no_separation, flash
  0.2222 vs glm-5.2 0.7778 (inverted ordering)".
- [x] T021 [P] [US1] Re-pair `benchmarks/cases/deveval-readtime/case.yaml`
  per data-model Â§1. Its FR-006 note is "rejected no_separation, flash
  0.2500 vs glm-5.2 0.1667".
- [x] T022 [P] [US1] Re-pair `benchmarks/cases/deveval-lice/case.yaml` per
  data-model Â§1. Its FR-006 note is "rejected reference (30/31), no
  separation recorded".
- [x] T023 [P] [US1] Re-pair `benchmarks/cases/deveval-hone/case.yaml` per
  data-model Â§1. Its FR-006 note is "not_assessed (parked)".
- [x] T024 [P] [US1] Re-pair
  `benchmarks/cases/deveval-particle-swarm-optimization/case.yaml` per
  data-model Â§1. Its FR-006 note is "not_assessed (parked)".
- [x] T025 [P] [US1] Re-pair `benchmarks/cases/deveval-stocktrends/case.yaml`
  per data-model Â§1. Its FR-006 note is "not_assessed (parked)".
- [x] T026 [US1] Run
  `C$ uv run --no-sync pytest tests/test_benchmark_corpus.py tests/test_golden_case_loads.py tests/test_benchmark_matrix.py tests/test_benchmark_arms.py`.
  It must be green: T018's tests pass and the cases load (SC-002 for the
  repo). Then run `grep -nE "^[^#]*glm-5\.2" benchmarks/cases/*/case.yaml`,
  which must print nothing.
- [x] T027 [US2] Re-label the seven repo cases, one at a time, in the order
  cat-cafe-monitoring, deveval-geotext, deveval-readtime, deveval-lice,
  deveval-hone, deveval-particle-swarm-optimization, deveval-stocktrends.
  - `C$` with `KROKER_COMMIT` = HEAD8 of the T017 commit.
  - Command: `uv run --no-sync python -m sdlc.cli benchmark accept --case <id>`.
  - After each case, check:
    - **(a)** The printed line equals contract Â§2.
    - **(b)** The file's `separation.strong.arm == zai-coding-plan-glm-5.3`
      and `separation.strong.run_ids == []`, lice included.
    - **(c)** Neither `reference.detail` nor `floor.detail` starts with
      `oracle environment failed`, and both `tests_total > 0`.
    - **(d)** `kroker_commit` equals HEAD8.
  - On an (a), (b) or (d) miss: `git checkout -- benchmarks/cases/<id>/acceptance.yaml`
    and fire **SG-2**.
  - On a (c) miss: rerun once. A second miss fires **SG-3**, after the
    same checkout.
  - Log the old â†’ new `oracle_tests`, reference counts, floor counts and
    `not_comparable` for `verification.md` (logged only, never gating).
- [x] T028 [US2] Run `C$ uv run --no-sync python -m sdlc.cli benchmark corpus`.
  Check contract Â§3: tally `0 of 8 accepted or provisional, 0 of 2
  private`, no row `stale: yes`, and smoke and probe rows identical to
  `baseline.md` Â§Corpus. A mismatch fires **SG-2**.
- [x] T029 [US1] Commit, one path per `git add`:
  - the seven `benchmarks/cases/<id>/case.yaml`;
  - the seven `benchmarks/cases/<id>/acceptance.yaml`;
  - `tests/test_benchmark_corpus.py`;
  - `tests/test_golden_case_loads.py`.

  Subject: `bench(cases): re-pair glm-5.2 arms to glm-5.3 / glm-5.3-flash`.
  The body gives the per-case old â†’ new verdict and tally 1 â†’ 0 of 8, and
  cites Q0=A, Q4â€“Q11=R and FR-005 (no spend).

**Checkpoint**: repo corpus clean and truthful.

---

## Phase 6: User Story 1 + 2 â€” private case (Q2, plan Step 5)

- [x] T030 [US1] Re-pair `D:\own\sdlc-private-cases\cases\theatre-box-office\case.yaml`
  per data-model Â§1 (the `extra_args_by_model` block is deleted). Its
  FR-006 note is "rejected no_separation, flash 0.0179 vs glm-5.2 0.0179
  (both 1/56 dead at merge; pipeline artefact addressed in round 017)".
  Then run `grep -nE "^[^#]*glm-5\.2" D:/own/sdlc-private-cases/cases/*/case.yaml`,
  which must print nothing.
- [x] T031 [US2] Run `C$ uv run --no-sync python -m sdlc.cli benchmark accept --case theatre-box-office`
  with the same checks (a)â€“(d) as T027. On a miss:
  `git -C D:/own/sdlc-private-cases checkout -- cases/theatre-box-office/acceptance.yaml`,
  then SG-2 or SG-3.
- [x] T032 [US2] Run `C$ uv run --no-sync python -m sdlc.cli benchmark corpus`
  (both roots). The tally stays `0 of 8 â€¦, 0 of 2 private`, the
  theatre-box-office row is `not_assessed`, and no row is stale.
- [x] T033 [US1] Commit in PRIV with `git -C D:/own/sdlc-private-cases add cases/theatre-box-office/case.yaml`,
  then `â€¦ add cases/theatre-box-office/acceptance.yaml`, then
  `git -C D:/own/sdlc-private-cases commit -F <file>`.
  Subject: `R019: re-pair theatre-box-office to glm-5.3 / glm-5.3-flash`.
  The body gives the verdict rejected no_separation â†’ not_assessed.
- [x] T034 [US1] Run `C$ uv run --no-sync pytest tests/test_private_leak.py`.
  It must be green: no private text leaked into this repo.

---

## Phase 7: User Story 3 â€” the record of why (FR-010, FR-011, plan Step 6)

**Goal**: a dated, findable explanation.

**Independent test**: quickstart Â§5 item 2a.

- [x] T035 [US3] Add an `R019` break marker to `BENCHMARK.md`, a
  blockquote beside the existing 2026-10-02 marker near the top. It says:
  - date 2026-10-27; cause: zai-coding-plan catalog deprecated glm-5.2
    (and glm-4.7, glm-5-turbo, glm-5.2-highspeed); opencode refuses
    resolution;
  - old pair strong flash / weak glm-5.2 â†’ new pair strong glm-5.3 / weak
    flash (GATE 1 Q0=A);
  - an 8-row per-case old â†’ new verdict table (values from `baseline.md`
    and T027/T031);
  - tally 1 â†’ 0 of 8;
  - carried flash runs now count as weak evidence, with the cross-commit
    caveat (research D-3);
  - the shipped test role moved to glm-5.3 (dev == test model);
  - glm-5.2 run records are kept as history and are now `not_comparable`.

  The file must stay â‰¤ 1000 lines: `python scripts/check_file_size.py`.
- [x] T036 [P] [US3] Change `README.md:310` from
  `--role-model dev=zai-coding-plan/glm-5.2` to
  `--role-model dev=zai-coding-plan/glm-5.3`. Leave README `:316` (the
  `zai:glm-5.2` route note) as it is, because it documents the proposer
  route (out of scope).
- [x] T037 [P] [US3] Rewrite the judge comment in `benchmarks/config.yaml:6â€“13`.
  It must state the actual reason for `anthropic:claude-sonnet-5`: a
  different family from every author (ADR-6), and the gemini free-tier 503
  and 429 losses recorded in the case judge comments. Remove the stale
  `anthropic:glm-5.2` and Gemini rationale. Do not change the value.
- [x] T038 [US3] Write the follow-up card
  `D:\own\Kroker\.workspace\tasks\2026-10-27-r019-reprove-separation-reruns.md`
  (outside git). It contains:
  - the exact commands
    `uv run --no-sync python -m sdlc.cli benchmark run --case <id> --all-arms`
    (recipe: `BENCHMARK.md` run section near `:783`, and `Dockerfile:125â€“127` for the worker image built with
    `--build-arg KROKER_COMMIT`) for cat-cafe-monitoring,
    deveval-geotext, deveval-readtime and theatre-box-office;
  - both arms on one commit, n â‰¥ 3 per arm (`MIN_RUNS_PER_ARM`);
  - a paid-run marker: user clearance required;
  - glm-5.3 429 exposure, which is the Q0 proof;
  - the dashboard mock refresh (`fleet-snapshot.json`,
    `interfaces/dashboard/frontend/src/api/mock/index.ts`,
    `scripts/dump_dashboard_fixtures.py`), out of scope here;
  - the arm-definition-hash idea (research D-6 limit 1) as a candidate.
- [x] T039 [US3] Run quickstart Â§5 item 2a (README grep prints nothing, the
  R019 marker is present with 8 rows, file size OK). Commit `BENCHMARK.md`,
  `README.md` and `benchmarks/config.yaml`.
  Subject: `docs(benchmarks): R019 glm-5.2 retirement break marker`.

---

## Phase 8: Polish and close (plan Step 7)

- [x] T040 Re-check the manifest. Recompute T003's manifest into the
  scratchpad and `diff` it against
  `.specify/specs/019-glm52-arm-retirement/baseline-records.sha256`. The
  diff must be empty. **SG-1** fires otherwise.
- [x] T041 Run the SC-001 sweep from quickstart Â§5.2:
  - the mechanical YAML grep must print nothing;
  - the Python-string grep prints only `src/sdlc/core/models.py:190`;
  - the broad `git grep -n "glm-5\.2" -- benchmarks/cases agents benchmarks/config.yaml src/sdlc/core/models.py src/sdlc/benchmarks/importers/deveval.py`
    shows only the allowed hits listed there.
- [x] T042 `C$` gates:
  - `uv run --no-sync pytest` (compare with baseline: SG-4);
  - `uv run --no-sync pytest -m temporal tests/replay` (SG-5);
  - `uv run --no-sync ruff check .`;
  - `uv run --no-sync ruff format --check .`;
  - `uv run --no-sync mypy` (no new errors against base);
  - host: `python scripts/check_file_size.py`.

  Run each pytest invocation in its own command, never two chained.
- [x] T043 Write `.specify/specs/019-glm52-arm-retirement/verification.md`.
  - For each of FR-001..FR-011 and SC-001..SC-006: the evidence (command
    plus result, or commit hash).
  - The T027/T031 logged count drift table.
  - The RED outputs from T007, T016 and T018.
  - Gate results.
  - Known limits and risks (research D-3 confounder, D-6 limits, D-7
    test == dev).
- [x] T044 Closing commit:
  `.specify/specs/019-glm52-arm-retirement/verification.md` and
  `.specify/specs/019-glm52-arm-retirement/tasks.md` (all boxes ticked).
  Subject: `docs(019): verification - glm-5.2 arms retired, records re-labelled`.
  Report to the orchestrator:
  - the branch head and the PRIV commit;
  - tally 1 â†’ 0 of 8;
  - the follow-up card path.

  Do not merge. Integration is the orchestrator's call.

---

## Dependencies & Execution Order

- **Phase 1** (T001â€“T006) runs first and in sequence. T003 and T004 run one after the other, because both write `baseline.md` sections, and they may run in either order after T002.
- **Phase 3** (US2-A, T007â€“T010) depends on Phase 1.
- **Phase 4** (US1-A, T011â€“T017) depends on Phase 1. It is independent of
  Phase 3 in code, but runs after it so the fast-tier baseline comparison
  stays attributable. T016/T017 (importer) are independent of T012â€“T015.
- **Phase 5** (T018â€“T029) depends on Phases 3 and 4, because its re-label
  stamps the T017 HEAD and contract Â§3 assumes FR-009 has landed.
  - T019â€“T025 are [P] with each other (separate files), after T018.
  - T027 is strictly sequential per case.
- **Phase 6** (T030â€“T034) depends on Phase 5 for the shared container
  recipe and the tally baseline.
- **Phase 7** (T035â€“T039) depends on Phases 5 and 6 for the verdict table
  values. T036/T037 are [P] at any time after Phase 1.
- **Phase 8** depends on everything.

## Parallel Examples

- After T018: T019, T020, T021, T022, T023, T024 and T025 (seven different
  `case.yaml` files).
- Phase 7: T036 (`README.md`) and T037 (`benchmarks/config.yaml`) alongside
  T035 (`BENCHMARK.md`).
- Phase 4: T016 (importer RED) alongside T012 (role flip): different files.

## Implementation Strategy

- **MVP** = Phases 1, 3, 4 and 5. The repo has no dead declaration, and its
  records are truthful.
- Phase 6 extends this to the private store, and Phase 7 records the why.
- Each phase ends with its own commit and checkpoint, so a stop-guard
  leaves the branch at a coherent commit.
