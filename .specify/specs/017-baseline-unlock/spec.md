# Feature Specification: Baseline Unlock

**Feature Branch**: `017-baseline-unlock`

**Created**: 2026-10-25

**Status**: Approved (GATE 1, user via orchestrator, 2026-10-25): approved as
written; the Calls Made in Design list was checked against the session's
rulings and nothing was contested. The design was brainstormed with the user one
question at a time, agreed with the advisor seat at every open question
(`.workspace/tmp/advisor-unlock-1..10.md`), and APPROVED by the reviewer
seat on pass 4 (`.workspace/tmp/reviewer-017-design-1..4.md`). The source
design is `.workspace/tmp/017-baseline-unlock-design-draft.md`. User rulings
are recorded under Rulings. Uncommitted by convention: the round's first task
commits it.

**Input**: An orchestrator brief of 2026-10-25, "Unlock-round for the
benchmark baseline (pre-AP0)". It named four items as hypotheses to verify
in code: (1) the analyze stage rejects every benchmark run (report F8,
`.workspace/tasks/016-followups.md`); (2) grading of runs whose merge
failed; (3) the spend-accounting cluster
(`.workspace/tasks/2026-10-05-research-spend-of-raising-attempts-unreported.md`,
`.workspace/tasks/2026-10-06-budget-gate-counts-all-recorded-spend.md`);
(4) judge retry with backoff on provider transients. Code references are
against main `e435bd10`.

## Context

The next phase runs the baseline (BIP-4.2 / AP-0.1): multi-hour cohorts
whose records anchor every later comparison. Round 016's R1 showed the
records cannot yet be trusted. Both arms graded near zero (1/56 in the
glm-5.2 run) and the case was
rejected `no_separation`. Every benchmark run's analyze record is FAIL. A
research spend gap leaves the cost records short.

**What unlocked means (user).** After this round the baseline can be run and
its records trusted: analyze no longer auto-rejects runs, a run whose
pipeline stalls no longer reads as a plain zero-quality model, and spend or
judge-retry noise cannot distort grades.

**Failure criterion (user).** If, after every item closes, the first
baseline run still produces zeros or distorted grades caused by the harness
itself (not the models), the round failed. "Harness distortion" is the closed
list under Success Criteria (SC-001). Everything outside it is a model
result and keeps its score.

### What the code showed (each hypothesis checked)

1. **Analyze (item A), confirmed with two causes.** The gate
   (`src/sdlc/stages/analyze/models.py:36-51`) counts a criterion as traced
   only when the analyst returns its exact `(task_id, criterion)` text with a
   non-empty `tests` list.
   - (a) Many plan criteria can never have a test: "requirements.txt
     exists", "LICENSE is MIT", "T-06: This task adds NO files to the repo".
   - (b) The analyst cannot see most test names. The integration diff is cut
     at 60,000 characters (`src/sdlc/vcs/git.py:93,120-122`), and the test
     summary (`src/sdlc/stages/analyze/step.py:102-106`) lists failing tests
     only. The instructions forbid inventing names
     (`agents/analyst/instructions.md`), so whole sets come back untraced
     (theatre 87/87 and 40, geotext 46, cat-cafe 79; stored `error` fields
     in `runs/benchmarks/*/*.jsonl`).
2. **Merge-failed grading (item B), the hypothesis is wrong as stated.**
   - Both R1 merges were blocked by the lint check (`blocked (absolute):
     lint_clean`, 110 and 112 introduced, mostly in `tests/`). Git did not
     fail.
   - The oracle grades `sdlc/<run_id>/integration` whatever the merge gate
     decides (`src/sdlc/benchmarks/oracle.py:290`).
   - 1/56 is that tree failing the held-out oracle, while 12 of 18 tasks
     (glm-5.2, `bench-theatre-box-office-1792359046`) and 9 of 18
     (glm-5.3-flash, `-1792347162`) had a passing last-attempt qa record.
   - The oracle record carries `detail: null`. The cause of 1/56 is not
     established, and the theatre scratch repo is not on the host.
3. **Spend accounting (item C), confirmed.**
   - A research sub-question attempt that raises loses its spend
     (`src/sdlc/stages/research/stage.py:329-330`,
     `src/sdlc/stages/research/step.py:117-125`).
   - Research stage spend reaches the stage record
     (`src/sdlc/stages/research/step.py:150-175`) but emits no
     `MODEL_USAGE` event, so the run summary's role rollup
     (`src/sdlc/observability/summary.py:54`) misses it.
   - The budget gate (`src/sdlc/workflows/role_host.py:273-305`) never fires
     in a benchmark run, because no run budget is set (default 0.0,
     `src/sdlc/core/models.py:422`; early return at `role_host.py:279`).
4. **Judge retry (item D), already on main** (S-batch 2026-10-19).
   `src/sdlc/benchmarks/judge.py:113-114,225-243` retries 429, 500, 502,
   503, 504 and httpx timeouts at 5, 30 and 120 s, with SDK retries zeroed
   through `single_retry_layer`. When retries run out the record gets
   `score=None, judge="error"`, never 0 (`judge.py:294-298`). What remains
   is checking downstream readers.
5. **Added (item E).** `plan_drift` counts generated artifacts
   (`__pycache__/`, `*.egg-info/`, `.pytest_cache/`) as unhinted touches
   (`src/sdlc/stages/plan/models.py:63`), and these feed the merge
   `plan_drift` check (`src/sdlc/stages/merge/step.py:95-119`).

## Terms

- **Evidence form**: one of the four ways a criterion can be traced: a test,
  file present, file absent, or task changed no files (FR-002).
- **Inexpressible criterion**: a plan criterion that no evidence form can
  express (for example "no other files are created", "pip install
  succeeds"). It stays untraced, and that is a plan-authoring result, not a
  harness distortion.
- **Stage reach**: the facts block recorded beside a run's oracle score
  (FR-020).
- **Stall**: a run whose last recorded stage did not complete (FR-024).
- **Pre-017 record**: any record without the fields this round adds. Readers
  treat it exactly as today.

## User Scenarios & Testing

### User Story 1 - Analyze traces what the tree actually proves (Priority: P1)

The benchmark owner reads a run's analyze record. Every criterion the tree
satisfies through a test, a file, an untouched named path, or a task with an
empty diff is traced. The record states plainly which criteria nothing could
express.

**Why this priority**: analyze FAIL on every run is the visible F8 failure,
and SC-001 item 1 makes it a round failure.

**Independent Test**: run the analyze step on deterministic fixtures
(FR-060) and read the buckets and the `criteria_trace` payload.

**Acceptance Scenarios**:

1. **Given** an integration diff over 60,000 characters whose tests cover every criterion, **When** analyze runs, **Then** every criterion is traced by a test from the static test inventory, and none is untraced because its test name was cut from the diff.
2. **Given** a criterion "LICENSE is MIT" where `LICENSE` is an unchanged base file, **When** the analyst cites `{kind: file, ref: LICENSE, expect: present}`, **Then** the criterion is traced by file.
3. **Given** "no pyproject.toml is created" and a run that did not touch `pyproject.toml`, **When** the analyst cites `{kind: file, ref: pyproject.toml, expect: absent}`, **Then** it is traced; **and when** it cites `foo/bar.txt` instead, **Then** containment rejects the citation and the criterion is untraced.
4. **Given** "T-06: This task adds NO files to the repo" and task T-06 with an empty own diff, **When** the analyst cites `{kind: task_unchanged}`, **Then** the criterion is traced; **and given** T-06 changed a file or its branch point cannot be derived, **Then** it is untraced.
5. **Given** a criterion whose only evidence is a command, **When** analyze runs, **Then** it counts in `traced_by_command`, it is untraced for PASS, and the error text marks it "(command only)".
6. **Given** an inexpressible criterion, **When** analyze runs, **Then** it is untraced and FAILs analyze, and the record names it.
7. **Given** a cited test name in any of the forms `tests/test_x.py::TestC::test_y`, `test_y` (unique) or `test_y[param]`, **When** it is validated, **Then** it matches the inventory entry `tests/test_x.py::TestC::test_y`.
8. **Given** a pre-017 workflow history, **When** it replays, **Then** it replays unchanged.

---

### User Story 2 - A stalled run reads as stalled, beside its honest score (Priority: P1)

The benchmark owner reads a near-zero run. The oracle score is unchanged,
and next to it the record shows how far the run got. When both arms stalled
at the same point, the case's verdict says "not separable: stalled at
<stage>" instead of rejecting it for no separation.

**Why this priority**: R1 rejected a case on two runs that stalled. A
baseline built on such verdicts measures the pipeline, not the models.

**Independent Test**: recompute acceptance verdicts from fixture records:
two stalled arms, two finished-but-bad arms, and one pre-017 run.

**Acceptance Scenarios**:

1. **Given** any graded run produced after this round, **When** its record is written, **Then** it carries `stage_reach` and its oracle score is the same number the oracle produced.
2. **Given** two arms whose every run has partial credit ≤ 0.05, the same `last_stage`, and that stage not completed (merge FAIL with deploy disabled, the R1 shape), **When** the verdict is computed, **Then** it is `not_assessed`, reason `stalled`, note "not separable: stalled at merge".
3. **Given** two arms that both passed merge, the case's final stage, and produced equally broken code, **When** the verdict is computed, **Then** the stalled rule does not fire, and the verdict is what it is today (`degenerate` or `rejected no_separation`).
4. **Given** any run without `stage_reach`, **When** the verdict is computed, **Then** the stalled rule does not fire and past verdicts recompute identically.
5. **Given** an oracle run on a tree that fails collection (pytest exit 2, or JUnit errors at least half of the total), **When** it is graded, **Then** `quality.detail` names it ("collection/import errors: E of N") and the exit code is a `components` entry.

---

### User Story 3 - Benchmark cost records carry all research spend (Priority: P2)

The benchmark owner compares cost across arms. Research spend is counted in
full, including attempts that crashed, and the run summary's role rollup
agrees with the stage records. The budget gate behaves exactly as before.

**Why this priority**: cost is a graded axis. Missing research dollars skew
the comparison, but this skews grades less than items A and B.

**Independent Test**: a fixture sub-question that raises an uncaught
`ModelHTTPError` on its first attempts and then succeeds. Read the stage
record, the trace rollup and `_role_usage`.

**Acceptance Scenarios**:

1. **Given** a sub-question whose first two attempts raise after spending tokens, **When** the stage records, **Then** `research_spend` includes both dead attempts' tokens and calls, priced once.
2. **Given** a completed research stage, **When** the run summary is built, **Then** its `research` role and total include the stage's spend.
3. **Given** a budgeted production run, **When** research spends, **Then** `_check_budget`'s sum is unchanged from today (no research spend in `_role_usage`), and the E-75 §4.3 attribution invariant still holds.
4. **Given** the ledger write fails (lock timeout), **When** an attempt raises, **Then** the original exception re-raises unchanged and the retry policy behaves as today.

---

### User Story 4 - A judge failure is never a zero (Priority: P2)

**Independent Test**: feed every report reader a record with `score=None,
judge="error"`.

**Acceptance Scenarios**:

1. **Given** a judge record with `score=None, judge="error"`, **When** the grid, report, acceptance and rubric rollups read it, **Then** each treats it as not graded, never as 0.

---

### User Story 5 - plan_drift ignores generated artifacts (Priority: P3)

**Acceptance Scenarios**:

1. **Given** a task diff touching `__pycache__/x.pyc`, `pkg.egg-info/PKG-INFO` and two hinted files, **When** plan drift is computed on a new history, **Then** the generated paths are not in `touched_unhinted` and the check does not fire.
2. **Given** a pre-017 history, **When** it replays, **Then** plan drift is computed exactly as before.

---

### User Story 6 - The pre-flight comes back clean before the baseline (Priority: P1)

**Acceptance Scenarios**:

1. **Given** every FR-060 fixture, **When** the suite runs in kroker-dev, **Then** all pass.
2. **Given** one todo-api run on the rebuilt worker (user confirms the paid launch), **When** it finishes, **Then** none of the SC-001 distortions appears. Every analyze untraced criterion is classified by hand from `criteria_trace` as inexpressible (reported) or expressible (a distortion, so the round fails).

### Edge Cases

- **A task branch is missing at analyze time, or its branch point cannot be
  derived.** Its per-task diff is "unknown" and `task_unchanged` is
  unvalidated (fail-closed). Nothing deletes task branch refs before
  terminal teardown (`src/sdlc/workflows/feature.py:297-327`), so this is a
  defensive path.
- **An inventory exceeds its size bound.** A truncation note goes into the
  prompt. A `present` path missing from a truncated tree listing counts as
  unvalidated, never as passed.
- **Mixed evidence on one criterion.** Precedence is test, then file
  (present, absent, `task_unchanged`), then command. Each criterion lands in
  exactly one bucket. Evidence that fails validation is not evidence.
- **A criterion key is missing or wrong.** The workflow falls back to an
  exact-text match.
- **Sub-question ids repeat across refine rounds.** The ledger is folded as
  totals, never per finding.
- **A worker shutdown during a research attempt.** The `CancelledError` path
  writes the ledger with a synchronous append.
- **Stall at a per-task stage.** `last_stage_outcome` for code or qa is
  `pass` only if every task's last record of that stage passed, `fail` if
  any failed, `other` otherwise.

## Requirements

### Functional Requirements

**Item A: analyze**

- **FR-001**: `CriterionTrace` MUST gain an optional `evidence` list of
  `{kind: "file" | "task_unchanged" | "command", ref: str | None, expect:
  "present" | "absent" | None}`. `ref` and `expect` apply to `file`, and
  `expect` defaults to `present`. `task_unchanged` carries neither and
  applies to the criterion's own task. Existing `tests` stays.
- **FR-002**: A criterion MUST count as traced only through one of four
  evidence forms (a closed set), each validated deterministically with no
  code execution:
  1. **test**: the cited name matches the static test inventory (FR-004 b)
     under FR-003 normalization;
  2. **file present**: the path is in the tree listing (FR-004 c);
  3. **file absent**: the path is not in the run's changed-file inventory
     (FR-004 a; not added, modified or deleted by the run) AND the path or
     its basename appears as a case-sensitive substring of the criterion
     text (containment);
  4. **task changed no files**: the criterion's task has an empty own diff
     in the per-task inventory (FR-004 d).
- **FR-003**: Test-name matching MUST be normalized. A pytest node id, a
  bare name that is unique in the inventory, a parametrized suffix
  `[...]`, and class methods all match the inventory entry
  `path::[Class::]name`.
- **FR-004**: One new activity on the integration worktree MUST build four
  inventories with no code execution:
  - (a) changed files, `git diff --name-only` against the base;
  - (b) a static test inventory from a stdlib `ast` scan of the test files
    in the integration tree;
  - (c) the tree listing, `git ls-files` at the integration head;
  - (d) per-task changed files, `git diff --name-only` of each task's branch
    (`TaskResult.branch`, `src/sdlc/workflows/models.py:60`) against that
    task's own starting commit, not the run base.

  Further rules for the inventories:
  - The task's starting commit is the branch point the task worktree was
    created from (`src/sdlc/workflows/task_host.py:273-292`). The builder
    MAY stamp it into `TaskResult` additively. When it cannot be determined
    deterministically, or the diff fails, the task's entry is "unknown".
  - Each inventory MUST have an explicit size bound and a truncation note.
    (a) and (b) MUST go into the analyst prompt outside the 60,000-character
    patch cap. (c) MUST NOT be sent in the prompt. (d) is sent only as
    "<task_id>: N files changed" (or "unknown").
- **FR-005**: Command evidence MUST be recorded and never executed. A
  criterion whose only evidence is a command counts in `traced_by_command`
  and stays untraced for PASS (ruling R-1).
- **FR-006**: Each authoritative criterion MUST get a stable key (for example
  `T01#3`) shown in the prompt. Matching MUST be by key, with exact text as a
  fallback.
- **FR-007**: The analyze record MUST gain additive counts `traced_by_test`,
  `traced_by_file` (present, absent and `task_unchanged`),
  `traced_by_command` and `untraced` (command-only plus empty), with each
  criterion in exactly one bucket by the precedence in Edge Cases.
  - PASS iff `untraced == 0`.
  - The failing error text MUST keep naming the untraced count and the first
    three (012 §6.1) and MUST mark command-only criteria "(command only)".
- **FR-008**: The analyze record MUST gain an additive, bounded
  `criteria_trace` field: a list of `{key, bucket, evidence: [{kind, ref,
  expect, valid}]}`, with refs cut to a fixed length, a capped criterion
  count and a truncation note. It lives on the record, not a sidecar.
- **FR-009**: The analyst instructions MUST describe the evidence forms and
  keys, keep the "never invent" rule and extend it to files and tasks.
- **FR-010**: The changed pass rule and the new activity MUST sit behind a
  `workflow.patched` marker. Pre-017 histories MUST replay unchanged.
- **FR-011**: A criterion no form can express MUST stay untraced. The record
  MUST name it like any other untraced criterion.

**Item B: stage reach and the separation verdict**

- **FR-020**: The run's oracle/cell record MUST gain an additive, optional
  `stage_reach` block. Fields:
  - `last_stage`, `last_stage_outcome` (pass | fail | other, per Edge
    Cases), `final_stage` (the last stage of the case's configured stage
    set);
  - `tasks_total`, `tasks_qa_passed`, `tasks_not_finished`;
  - `merge_outcome`, `merge_blocking_checks`.

  Facts only. No derived "integration suspect" flag is stored.
- **FR-021**: The plan record MUST gain an additive `tasks_total`, written
  where `len(artifact.tasks)` is in hand (`src/sdlc/stages/plan/step.py:148-163`).
- **FR-022**: The merge record MUST gain an additive `blocking_checks:
  list[str]` from the structured `GateReport.blocking`
  (`src/sdlc/workflows/gate.py:56,155-167`) at all four merge record sites
  (`src/sdlc/stages/merge/step.py:485-521, 538-556, 623-641, 643-657`).
- **FR-023**: `stage_reach` MUST be computed in the parent inside the
  existing `summarize_cell` call (`src/sdlc/benchmarks/workflow.py:368-370`,
  `src/sdlc/benchmarks/cell.py:53-76`), with no new activity calls.
  - A task is finished iff its last code attempt record and its last qa
    record are PASS.
  - `tasks_not_finished = tasks_total − finished`.
  - The task's final done or quarantined status is NOT carried, because that
    would change the child workflow's command sequence.
- **FR-024**: `Run` (`src/sdlc/benchmarks/runs.py:58-97`) MUST gain an
  optional `stage_reach`, and `ArmEvidence` MUST gain `stall_points`.
  `decide()` (`src/sdlc/benchmarks/acceptance.py:147-199`) MUST apply a new
  rule in the order reference → floor → not-assessed checks → saturated →
  **stalled** → degenerate → no weak arm → no_separation → pass.
  - The rule fires only when all four hold:
    1. every run in both arms has `stage_reach`;
    2. every run's partial credit is ≤ 0.05;
    3. all runs share one `last_stage`;
    4. that stage did not complete: `last_stage_outcome` is not pass, or
       `last_stage != final_stage`.
  - Its result is `not_assessed` with a new additive `Reason` value
    `stalled` and note "not separable: stalled at <stage>".
- **FR-025**: The oracle MUST capture its test command's exit code (today
  discarded, `src/sdlc/benchmarks/oracle.py:327-329`) and the JUnit `errors`
  count. On pytest exit 2 or 4, or when errors are at least half of the
  total, `quality.detail` MUST name it, and the exit code MUST be an additive
  `components` entry. This rule MUST be checked against FR-027 before build.
- **FR-026**: The oracle score MUST never be altered, rescaled or replaced.
- **FR-027 (finding first)**: Before FR-024 and FR-025 are built, the round
  MUST establish why the R1 integration trees scored 1/56. Sources are
  whatever survives (container scratch repos, Temporal history, records). If
  nothing survives, the pre-flight run (US6) supplies the evidence. A rerun
  of R1 is a paid action and needs user confirmation. If the cause is a
  harness defect, it joins SC-001 and goes to the bug crew.

**Item C: cost records**

- **FR-030**: Every exit of `_research_subquestion_impl` by raising MUST add
  the attempt's non-zero in-frame `run_usage` to a per-run dead-attempt
  ledger in the existing store (`src/sdlc/stages/research/budget_store.py`,
  `$SDLC_RUNS_ROOT/<run_id>/research/`), add-only, then re-raise.
  - Shape: one outer `except BaseException` wrapper around the handler
    chain. It covers the bare re-raise (`stage.py:329-330`), uncaught
    `ModelHTTPError` and httpx errors, and `CancelledError`.
  - The degrade handlers return rather than raise (`stage.py:307-342`), so
    they never write.
- **FR-031**: The ledger write MUST be best-effort. Any write error,
  including the lock's `TimeoutError` (`budget_store.py:50-66`), is logged
  and swallowed. The original exception MUST always re-raise. On the
  `CancelledError` path the write MUST be a synchronous append. The retry
  policy (`RESEARCH_SQ_ACT`, `research/step.py:56-78`) MUST NOT change.
- **FR-032**: One small activity MUST read the ledger totals (per model:
  tokens and calls), and the workflow MUST add them to `research_spend`
  once, as totals.
  - Pricing goes through `_fold_research_usage`, which gains a `calls`
    parameter (default 1).
  - The fold runs after the last fan-out and synthesis and before every
    record site (`research/step.py:294, 372, 389`).
  - Findings are never re-folded. The fold sits behind `workflow.patched`.
- **FR-033**: Research stage spend MUST be emitted as `MODEL_USAGE` events
  with `role="research"` through a new emit-only path.
  - The path makes no activation attribution and no `_role_usage` fold
    (ruling, finding 3). It MUST NOT use `ReportHost._track_usage`
    (`src/sdlc/workflows/report_host.py:56-100`).
  - It reuses the `usd` that `_fold_research_usage` already computes, with
    no new pricing activities, behind the same marker as FR-032.
  - It does not double-count the architect's research tool, which already
    reaches `_track_usage(role="research")` (`role_host.py:258-267`).
- **FR-034** (amended A-1): The split of surfaces MUST be documented as
  intended. Trace-derived surfaces include research spend: the run summary,
  the live `run_state` roles and `cost_usd_total` (already trace-derived,
  `src/sdlc/workflows/run_host.py:147-151,174`), the Cost tab total, and
  benchmark cost records. `_role_usage`-derived surfaces do not, as today:
  `_check_budget`, the `budget_counted_usd` figures (`run_host.py:117,185`),
  and per-activation `graph_view` spend (`src/sdlc/workflows/graph.py:115`).
  The E-75 §4.3 invariant `attributed + unattributed == sum(_role_usage)`
  MUST still hold.

**Item D: judge**

- **FR-040**: Every reader of judge records (grid, report, acceptance,
  rubric rollups) MUST treat `score=None` / `judge="error"` as not graded,
  never as 0. Verify first; change only a reader that gets it wrong.

**Item E: plan_drift**

- **FR-050**: Generated artifacts MUST be filtered out of `touched` before
  plan drift is computed.
  - The filter uses one shared ignore list that merges
    `src/sdlc/stages/qa/activities.py:582-585` and
    `src/sdlc/benchmarks/oracle_id.py:8` (`IGNORED_DIRS`). No third list.
  - The filter sits behind `workflow.patched`, because `compute_plan_drift`
    runs workflow-side (`src/sdlc/stages/code/step.py:778`).
  - A unit test MUST pin the unpatched path, because no replay fixture
    carries plan_drift today.

**Verification**

- **FR-060 (fixtures)**: The round MUST add deterministic fixtures for:
  - analyze on untestable criteria and a diff over 60,000 characters;
  - test-name normalization (node id, bare, parametrized, class method);
  - file present on a base file;
  - file absent with and without containment;
  - `task_unchanged`: an empty-diff task (passes), a missing branch or
    underivable branch point (untraced), and a sequential task whose diff
    excludes inherited changes;
  - a command-only criterion;
  - a research sub-question raising an uncaught `ModelHTTPError` across
    retries, and a ledger write failure;
  - the emit-only path against `_check_budget` and the attribution
    invariant;
  - a judge transient and a `score=None` record through every reader;
  - plan_drift with cache dirs, patched and unpatched;
  - separation with two stalled arms, two finished-but-bad arms and one
    pre-017 run;
  - an oracle tree that fails collection.
- **FR-061**: The replay gate (`-m temporal`) MUST stay green on every
  existing history.

### Key Entities

- **CriterionTrace / Evidence** (analyze artifact): gains `evidence`.
- **Analyze record**: gains bucket counts and `criteria_trace`.
- **Plan record**: gains `tasks_total`.
- **Merge record**: gains `blocking_checks`.
- **StageReach** (on the oracle/cell record, read into `Run`): the FR-020
  facts.
- **ArmEvidence**: gains `stall_points`.
- **Reason**: gains `stalled`.
- **Research dead-attempt ledger**: an add-only on-disk file beside the
  research budget counters.
- **Oracle record**: gains an exit code component and a collection-error
  detail.

## Run Gates and Estimate

- No paid run is part of building this round.
- One paid pre-flight run (todo-api, US6) closes it. It needs user
  confirmation at launch, on a worker rebuilt with `--build-arg
  KROKER_COMMIT`.
- A rerun of R1 for FR-027 is optional, needs user confirmation, and is
  used only if no stored evidence survives.

## Success Criteria

- **SC-001**: The first baseline run shows none of these harness
  distortions (the closed list):
  1. an analyze FAIL on a criterion that an evidence form can express and
     the tree satisfies;
  2. a near-zero oracle result with no `stage_reach`, or `no_separation`
     when both arms stalled at the same stage;
  3. any harness cause found by FR-027;
  4. benchmark cost records missing research spend (dead attempts or role
     rollup);
  5. a judge transient recorded as 0, or `None` counted as 0;
  6. `plan_drift` firing on generated artifacts.

  Everything else (lint failures, failing produced tests, oracle failures of
  incomplete code, analyze FAIL on inexpressible criteria) is a model or
  plan-authoring result.
- **SC-002**: On the US6 pre-flight, analyze traces every expressible
  criterion the tree satisfies (baseline: 14 of 14 runs FAIL, report F8).
- **SC-003**: Recomputing every stored `acceptance.yaml` gives identical
  verdicts (no pre-017 run has `stage_reach`).
- **SC-004**: Every pre-017 record loads, and every existing history
  replays.
- **SC-005**: `_check_budget`'s sum on a fixture run is identical before and
  after this round.

## Rulings

- **Item 1 (user)**: analyze may cite a file or command as evidence.
- **Item 2 (user)**: option (c), both side by side. The record keeps the
  honest near-zero score and carries stage reach next to it. Additive fields
  only.
- **Item 3 (user)**: limited to complete benchmark cost records. The budget
  gate's counting rule is deferred.
- **R-1 (user)**: a cited command does NOT count toward analyze passing. It
  is recorded and visible; the criterion stays untraced.
- **R-2 (user, option a)**: "this task changed no files" is its own evidence
  form, validated against that task's own diff, computed before merge while
  the branch exists. Criteria no form can express stay untraced, and the
  spec says so plainly.
- **Finding 7 (user)**: stalled resolving to `not_assessed` is part of
  ruling (c). `rejected no_separation` must not be produced for common
  pipeline stalls.
- **Finding 3 (user)**: emit-only research spend, with no `_role_usage`
  fold. The deferral stands.
- **Success definition (user, advisor-amended)**: a closed list of
  distortions (SC-001) and a pre-flight before the baseline (US6).

## Amendments after GATE 1 (plan, 2026-10-25; listed for GATE 2)

- **A-1 (FR-034, factual correction, reviewer plan pass 1 finding 1).** The
  spec listed the live `run_state` role view as `_role_usage`-derived. It is
  trace-derived (`run_host.py:147-151`, 011 R-1), so research spend appears
  there too. Only the gate's counted figure comes from the bag. This changes
  no design and no ruling: research spend is still emit-only, and the budget
  gate is untouched.

## Calls Made in Design (for the user to check at GATE 1)

- The spec number and slug `017-baseline-unlock`.
- Item E is in scope. Hindsight cross-run memory, the coverage-path
  mismatch and payload overflow are out.
- Containment on `file absent`. The `present | absent` form. No free-form
  inventory claims.
- ε = 0.05 for the stalled rule. The stalled rule is ordered before
  degenerate.
- `tasks_not_finished` instead of a quarantine count. `tasks_total` on the
  plan record.
- FR-025's collection-error signal (exit 2 or 4, errors ≥ half of total).
- The ledger is folded as totals for every dead attempt, not only for failed
  sub-questions.

## Assumptions

- Task branches persist until terminal teardown. The reviewer verified this
  (`src/sdlc/vcs/worktree.py:111-172`, `feature.py:297-327`).
- Analyze precedes merge in both orchestrators (`feature.py:519-531`,
  `src/sdlc/workflows/graphs/default.graph.yaml:34`).
- In the arms run so far, the analyst runs on a fixed proposer model (R1:
  `zai:glm-5.3`), not the arm under test, although an arm's `role_models`
  can override it (`src/sdlc/benchmarks/workflow.py:88-112`).
- Verification runs in kroker-dev after its `/app` bind is checked.

## Known Limits (stated, not fixed)

- Beyond containment, the workflow checks that a cited path or test exists,
  not that it is relevant to the criterion. `criteria_trace` makes this
  auditable.
- An attempt killed by SIGKILL, a worker crash or a hard activity timeout,
  before the wrapper runs, loses its in-flight research tokens.
- The research gate-REJECT path (`research/step.py:318-319`) writes no stage
  record, and its dead-attempt spend is also missing from the trace.

## Out of Scope

- The budget gate's counting rule (deferred card
  `2026-10-06-budget-gate-counts-all-recorded-spend.md`).
- Hindsight cross-run memory (V5), the coverage-path mismatch, aggregate
  payload overflow.
- The `files_hint` fence (A1).
- Any change to what the merge gate's absolute checks demand (012 ruled them
  right-reasoned).
- Unifying the trace-derived and `_role_usage`-derived spend surfaces.

## Dependencies

- Main `e435bd10`. Defects found in main during the round go through the bug
  crew (user ruling 2026-10-17).
- `.specify/specs/012-benchmark-record-trust/gate-diagnosis.md` (prior
  analyze and merge diagnosis), `.specify/specs/011-cost-and-failure-tails/`
  (ruling R6, the surface split's origin), and the E-75 §4.3 attribution
  invariant.
