# Research: Benchmark Record Trustworthiness (012)

Base: main `7f5191d0`. Sources: the spec, the audit report
(`docs/reports/2026-10-06-benchmark-improvement-plan.md`, read-only), a
read of the tree, advisor `.workspace/tmp/012-advisor-answer.md`, skeptic
`.workspace/tmp/012-skeptic-answer.md`.

Each decision: what was chosen, why, what was rejected. "Verify" lines are
checks the executor runs before relying on a claim; a failed check is a
stop, not a workaround.

## What the tree shows (read before the decisions)

| Fact | Where |
|---|---|
| Five separate derivations of the cases location. Only two honour `SDLC_CASES_ROOT`. | honour: `benchmarks/oracle.py:161`, `benchmarks/tasks.py:75`. ignore: `benchmarks/judge.py:221` (used by `load_case_assets` and imported by `report.py:11`), `benchmarks/cli.py:265` and `:297`. `calibration.py:240` derives `_CALIB_DIR` the same way. |
| `load_case_assets` skips a missing file by design. | `judge.py:236-240` |
| The judge lookup key is what each stage passes (`clarifier`, `architect`, `qa`, ...) and matches the manifest keys. The corpus has no missing registered file today. | `stages/*/step.py` `ctx.judge(...)` calls; all ten `benchmarks/cases/*/case.yaml` checked |
| `STAGE_TO_RUBRIC` is keyed on `planning`; records say `plan`. It serves the trust column only. | `calibration.py:243` |
| The benchmark parent swallows a child failure and then grades whenever the case has a language. A missing score becomes FAIL. | `benchmarks/workflow.py:297-325`, `:163` |
| The integration branch is created before any code task runs, so "the oracle can check it out" is true for a run that produced nothing. | `vcs/integration.py:37-51`, `oracle.py:209` |
| The oracle runs bare `pytest` in the worker's own environment (`env=None`). QA and merge use a per-worktree virtual environment; the oracle does not. | `oracle.py:224`, `stages/qa/activities.py:128` |
| One cell writes four files today: oracle (arm name), code (model id), and two proposer files (`#proposer#<model>`). | `recorder.py:94-103`; `runs/benchmarks/bench-todo-api-greenfield-1791051721/` |
| The code, qa and review records all start at the attempt start, and code and qa end when they are written, after review. | `stages/code/step.py:562, 772, 784-785, 811-812` |
| The qa outcome is the task's combined verdict. The review record passes no spend. | `code/step.py:814`, `stages/review/step.py:147-163` |
| `PROMPT_SHAS` exists: sha256 of each role's `instructions.md`, keyed by registry stage name. | `agents/roles.py:252` |
| The merge record with quality 0.0 on benchmark runs is the absolute-gate branch; it does not say which check blocked. The analyze 0.0 is `untraced_criteria`. | `stages/merge/step.py:486-512`, `stages/analyze/step.py:151-163`; stored todo-api records |
| Readers count `outcome is FAIL` (heatmap, agreement matrix) and `compute_summaries` groups every record except oracle-task. | `heatmap.py:110`, `agreement_matrix.py:63`, `scoring.py:33` |
| `stages/code/step.py` is 991 lines. | ceiling 1000 |

## R-1 One cases location (FR-001)

**Decision.** A leaf module `src/sdlc/benchmarks/paths.py` with
`cases_dir()` and `calibration_dir()`. `cases_dir()` reads
`SDLC_CASES_ROOT` at call time and falls back to the checkout path.
`calibration_dir()` is the sibling of the cases directory
(`cases_dir().parent / "calibration"`), so one override moves both. Every
derivation in the table above is replaced by a call. `judge._CASES_DIR`
is removed.

**Why.** F1 is one bug copied five times. A leaf with no imports from the
other benchmark modules cannot form a cycle.

**Rejected.** A second environment variable for calibration: one more
thing to forget in the image.

**Verify.** When done, `grep -rnE '"benchmarks" / "(cases|calibration)"'
src/sdlc` returns only `paths.py`. (`score.py:17` and `experiments.py:38`
also use `parents[3]`, for the repository root; they locate
`benchmarks/config.yaml` and the experiments store, are not case
locations and do not move.) `grep -rnE "_CASES_DIR|_cases_dir|_CALIB_DIR"
src tests` shows every site and every test that uses an old name; tests
move to the environment variable.

## R-2 A registered file that is missing or empty fails (FR-002)

**Decision.** Two layers, one rule.

1. `check_case_assets(rubrics, vetoes, case_dir) -> list[str]` in
   `paths.py`: for each registered rubric and veto, the file must exist
   and hold non-whitespace text. Returns one message per problem naming
   the kind (rubric or veto), the key and the path.
2. The benchmark run command calls it before it contacts Temporal and
   exits non-zero with the messages.
3. `load_case_assets` raises on the same condition, so a run started any
   other way stops at its first activity, before any cell exists. It
   raises Temporal's `ApplicationError(..., type="MissingCaseAsset",
   non_retryable=True)`: the activity runs under a five-attempt policy,
   and a plain exception would be retried five times before failing.

**Why.** Zero model spend in both paths (SC-008). The activity is the
guard for callers that are not the CLI.

**Rejected.** Checking only the rubrics of stages the run will execute
(skeptic L4 condition 3). The spec says a registered file must exist; a
manifest that names a file it does not ship is a broken manifest whether
or not the stage runs. The corpus is clean today, and a corpus test keeps
it clean.

**Not affected.** Cases with empty maps (the six DevEval imports). Drift
records have no manifest and never reach this code.

## R-3 Stage-to-rubric mapping (FR-003, FR-004, FR-005)

**Decision.** `STAGE_TO_RUBRIC` gains `plan` and keeps `planning` (the
heatmap's canonical name still uses it). A test pins every key against
the set of stage names the pipeline writes plus the heatmap's canonical
names, and pins every value against the calibration bucket names in use.
A second test asserts that each key a stage passes to the judge is a key
the corpus manifests use.

**Why.** F15 is a one-line fix; the test is what stops the next rename.
The judge lookup itself is correct and is not changed.

**Rejected.** Collapsing the three vocabularies (record stage, manifest
key, calibration bucket) into one table. It is a rename across stages,
manifests and stored calibration reports for no Phase 1 gain.

## R-4 Graded, not graded, grading failed (FR-006 to FR-009, FR-013)

**Decision.** The line is "the code stage finished", not "a branch
exists". This replaces the spec's first wording (skeptic L5: BREAKS,
confirmed in `vcs/integration.py`).

- After the child ends, an activity `summarize_cell` reads the records
  the cell wrote and returns the last stage reached and whether any
  post-code stage (analyze, merge, deploy) wrote a record. Intake and
  retro write trace events only, never a record, so they are in neither
  list.
- **Code finished** = a post-code stage record exists.
- Code not finished → **not graded**: the oracle is not run and no oracle
  or oracle-task record is written.
- Code finished → the oracle runs.
  - Diff against base empty → **graded**, 0 passed, score 0.0, no test
    run (FR-013: a real zero, by construction).
  - A score comes back → **graded**.
  - No score (environment build failed, timeout, no report) → **grading
    failed**: an oracle record with no score, the reason in `error`,
    outcome `not_evaluated`.
- A case with no oracle → status `no_oracle`.
- One **cell record** per cell (new scope) carries: pipeline finished
  (child returned without raising), code finished, last stage, grading
  status, the child's result text or failure text.

**Why.** The audit's eight aborted runs stopped in research or clarify:
no post-code record, so they become not graded. The F3 run (init commit
only, aborted) becomes not graded as well. A run that finishes code and
is rejected at merge has an analyze or merge record, so it is graded,
which is the spec's edge case.

**Rejected.**
- "Integration branch has commits beyond base" as the only test: a cell
  that dies after one of four tasks would be graded as if it were a
  finished implementation.
- The child's return value as the signal: early stops can return
  normally, and failures are swallowed.
- Fields on the oracle record instead of a cell record (advisor D2):
  every reader that does not know the new field would still see a FAIL
  row.

**Verify (before coding).** (a) On the stored records, list the stages
present for one aborted and one finished run and confirm the rule
separates them. (b) Confirm the analyze stage runs after the code stage
even when a task was quarantined; if a finished code stage can end the
run with no post-code record, stop and report (the rule needs a code
stage completion record instead).

## R-5 "Not evaluated" is an outcome value (FR-025)

**Decision.** `BenchmarkOutcome.NOT_EVALUATED = "not_evaluated"`, used
with `quality.score = None` and the reason in `error`.

**Why.** The advisor recommended score `None` with an existing outcome,
with the caveat to check how readers count. They count `outcome is FAIL`
(`heatmap.py:110`, `agreement_matrix.py:63`), so any existing value is
counted as something it is not. Inside the benchmark package a new value
matches none of the existing comparisons and drops out of them without
edits.

**One reader outside the package does not drop it.**
`scripts/aggregate_benchmarks.py` (used by the documentation build
through `scripts/docs/gen_pages.py`) reads the record files as raw JSON.
It treats every outcome that is not the string `pass` as a failure
(`:143`, `:156`), sums wall-clock over every record of a run (`:131`),
and prints `model` as the label (`:254`). Unchanged, it would count a
`not_evaluated` record as a failure, add the cell record's whole-cell
duration on top of the stage durations, and label oracle rows
`deterministic`. It is brought into the reader work (R-11): cell records
are skipped, `not_evaluated` is neither pass nor fail, the label is the
arm when present.

**Rejected.** Omitting the record: it loses the evidence the stage was
reached.

**Verify.** `BenchmarkHost._record` emits `outcome=record.outcome.value`
on a stage-ended trace event. Grep the dashboard backend and client for
consumers of that string; if one maps it to a closed set, stop and report.

## R-6 Per-grade oracle environment (FR-010 to FR-012)

**Decision.**

1. **Reproduce first.** Two hypotheses, both checkable without a run:
   (i) something importable as `app` in the worker's site-packages (an
   editable install or a `.pth` left by a harness running `pip install -e
   .` outside a virtual environment); (ii) the scratch repository's base
   branch already holds a previous run's `app.py`. Check the stored
   scratch repository and the worker image; write the outcome to
   `f3-reproduction.md` in the spec directory.
2. **Isolate regardless.** Each grade provisions a virtual environment
   inside its own temporary worktree with the existing
   `_ensure_python_env`, installs the oracle's own test dependencies from
   a case-owned `oracle/requirements.txt` (fallback: `pytest` only), and
   runs the oracle command with an allowlisted environment: the venv's
   script directory first on `PATH`, `VIRTUAL_ENV` set,
   `PYTHONNOUSERSITE=1`, no `PYTHONPATH`, no `PYTHONHOME`. The temporary
   directory, venv included, is deleted in the existing `finally`.
3. **Guard.** Empty diff against base returns the zero grade before any
   provisioning (R-4).
4. **Seam.** Provisioning is one module-level function the fast tests
   replace; the real one is exercised by a `slow`-marked test.

**Why.** The oracle is the only test runner in the pipeline that still
uses the worker's environment. A container per grade (the report's
SlopCodeBench reference) needs a container runtime inside the worker,
which the image does not have.

**Rejected.** A guard without isolation: a non-empty diff can still
import stale code. Moving `_ensure_python_env` to a neutral module: the
merge stage already imports it from the qa slice; a move touches three
slices for no behaviour change. The benchmark package imports it the same
way.

**Consequence.** A produced project that only worked because the worker
happened to have its dependencies now fails the oracle. That is the
correct result, and it is a reason post-012 and pre-012 oracle scores are
not comparable. The grade's detail text says the environment was isolated.

**Verify.** `_ensure_python_env` returns a full environment built from
`os.environ`; the oracle must not pass it through unfiltered. Confirm a
fresh worktree of an integration branch never contains a committed
`.sdlc-venv`; if it can, remove it before provisioning.

## R-7 Provenance (FR-014 to FR-016)

**Decision.**

- Activity `resolve_provenance` runs once at benchmark start. Order: git
  in the Kroker source root (`rev-parse HEAD`, `status --porcelain`); then
  `KROKER_COMMIT` and `KROKER_TREE_DIRTY` from the environment; then
  `unknown`. The image gets a `KROKER_COMMIT` build argument.
- The result rides `BenchmarkConfig` (`kroker_commit`, `tree_dirty`) into
  every cell, and `stage_record` copies it onto the record. Oracle and
  cell records get it from the same values.
- On the record: `kroker_commit: str | None`. Absent/`None` means a
  pre-012 record. A 012 writer always writes a commit id or the literal
  `unknown`; a validator on the builder path enforces it.
  `tree_dirty: bool | None`, where `None` means not determinable.
- Prompt hash: `stage_record` fills `prompt_sha` from a role-keyed map
  built from the registry (`sha256` of the role's `instructions.md`, the
  same bytes `PROMPT_SHAS` hashes). A record whose role has no registry
  instructions, or whose model is `deterministic`, gets an explicit
  `none:<reason>` value, never `""`.

**Why.** Resolving once makes every record of a run agree even if the
worker restarts. `stage_record` runs in workflow code and cannot read
git; the configuration is the path rubrics already take.

**Known limit (GATE 2 item).** The hash covers `instructions.md`, not the
prompt builders in `stages/*/prompts.py`. A change there shows as a
different commit, or as `tree_dirty = true`; it does not change the hash.
The skeptic asked for a combined digest (L6 condition 1). Not done: it
adds a second hashing scheme next to one that tests pin, and the commit
plus the dirty flag already separate such runs. Filed as a follow-up.

**Verify.** Which role names do record writers pass, and which of them
have registry instructions (harness roles `dev`, `test`, `devops`
included)? The prompted-role set in the contract is filled from that
check, and a test pins it. Inside `kroker-dev` a bind-mounted git
worktree cannot run git (its `.git` points at a host path): the
environment fallback is what the smoke run uses.

## R-8 One cell label (FR-017, FR-018, ruling R1)

**Decision.**

- The record gains `arm` (the arm name) and `cell_id`
  (`case#harness[:lead]#arm`, the existing `BenchmarkCell.cell_id`).
  `BenchmarkConfig` carries both; `stage_record` and the oracle and cell
  record builders set them.
- `model` keeps one meaning: the model that did the record's work. Oracle
  and cell records write `deterministic` there.
- `_cell_id_for` returns `record.cell_id` when present and the old
  derivation otherwise, so pre-012 files are still found and a 012 cell
  is one file.
- Two helpers in `models.py`, `cell_key(record)` and `arm_label(record)`,
  with the pre-012 fallback inside. `compute_summaries` groups by
  `(case, stage, cell_key)`. The five matrices that build
  `harness#model` keys use the helpers.
- A summary row for 012 records shows the cell and lists the distinct
  models of that stage.

**Why.** Today `model` means the arm on oracle records and the role's
model elsewhere; that double meaning is F11. The helpers put the fallback
in one place (skeptic L1 conditions 1 to 3).

**Rejected.** Overwriting `model` with the arm name: loses FR-018.

## R-9 Timings, verdicts, review spend (FR-019 to FR-022)

**Decision.** In `stages/code/step.py`, two timestamps and no new
helpers:

- `_code_ended` taken when the coding work is done, immediately before
  the test run. The code record ends there.
- `_qa_ended` taken when the qa step returns. The qa record spans
  `_code_ended` to `_qa_ended`. The review step receives `_qa_ended` as
  its start and ends at its own write, which happens inside the review
  step right after the reviewer returns.
- qa outcome = tests passed and qa reported no issues. Containment drift
  stays in the task verdict, not in qa's.
- `stages/review/step.py` creates a spend bag, passes it to the role call
  and to the record, the way the adversary lens already does.

**Why.** Three records per attempt then partition the attempt's time
instead of each claiming all of it. Growth in `code/step.py`: two new
timestamp lines, plus up to four lines for the qa outcome expression and
a guard around the qa record when the lens did not run (FR-022).
Budget: 991 → at most 997.

**Visible outside benchmark runs.** The recorder emits a stage-ended
trace event for every record before it checks for benchmark mode
(`workflows/benchmark_host.py:96-113`), and adds `cost_usd` to it when
the record has a dollar cost. Once the review record carries spend, the
review stage-ended event gains `cost_usd` in ordinary runs too, and the
`duration_s` of code, qa and review events changes to the corrected
spans. Both are corrections, not regressions, and neither changes the
command sequence.

**Rejected.** Moving the audit recorders out of `step.py` to make room
(advisor D7): `stages/code/AGENTS.md` states they stay there, and the
change fits without it.

**Verify.** `_now()` wraps `workflow.now()` (deterministic). When the qa
lens is disabled or absent, confirm no qa record is written; if one is,
that is FR-022 work in the same task. Replay: payload changes only, no
new command.

## R-10 Analyze and merge gates (FR-023 to FR-026, ruling R2)

**Decision.** Diagnose from stored evidence, then apply one rule per
gate.

- Evidence. The stored merge and analyze records carry no cause, no
  pipeline export exists for benchmark children (`runs/pipeline/` holds
  other runs only), and gate feedback is kept in an external memory
  service. What does exist: the integration branch of every stored run in
  the scratch repository, and console logs under `runs/ops/`. So the
  diagnosis re-runs the merge slice's deterministic checks (lint, the
  integration test run, coverage, security scan) against a temporary
  worktree of a stored integration branch, and reads the traceability rule
  against the stored plan and produced tests. The analyst's own report is
  not stored; the diagnosis says what cannot be established without it.
  No new run.
- Known so far: merge fails in the absolute branch (`tests_clean` /
  `build_integration_green` or `lint_clean`; the record does not say
  which); analyze fails on untraced criteria.
- Rule (ruling R2 with the skeptic's L2 conditions):
  - a check may be recorded as not evaluated only if the diagnosis shows
    it needs something a benchmark run cannot have (a remote, a human at
    an unattended gate, network the sandbox forbids);
  - a check that inspects the produced code (tests, lint, traceability,
    reviewer findings) is never switched off. If it rejects for a wrong
    reason, the defect is repaired; if it rejects for a right reason, it
    stays a rejection;
  - outside benchmark mode nothing changes.
- Always: a rejecting merge or analyze record names what blocked in
  `error` (check names, or the untraced count and first items). The two
  merge returns that leave without a record (`advisory` at
  `merge/step.py:526`, `soft-verdict` at `:591`) write one first; the
  absolute branch already writes one. In a benchmark run each of these is
  one more `record_benchmark` activity; outside a benchmark run the
  recorder schedules nothing, so the command sequence there is unchanged.
- The diagnosis and the per-gate decision are written to
  `gate-diagnosis.md` in the spec directory, and the decision is reported
  to the orchestrator before the repair is coded.

**Why.** "Not evaluated" must not become a way to hide a real failure.

**Stop.** The repair needed is not known until the diagnosis is done. If
it reaches outside the analyze and merge slices and the benchmark
package, or changes non-benchmark behaviour, stop and report.

## R-11 Existing records (FR-027, ruling R3)

**Decision.** New record fields are optional with defaults, so every
stored line still loads. `is_pre012(record)` = `kroker_commit is None`
and the record is not a drift record (`case_id == "_production"`). Drift
records are written outside benchmark runs by a writer this round does
not change; they never carry a commit and are not counted as pre-012.
`compute_summaries` never mixes the two kinds in one row: each summary
carries `pre012`, and the report renders 012 rows first and pre-012 rows
in a second table headed as untrusted. The heatmap, the matrices and the
success-criteria rollup print one line with the number of pre-012 records
they include, and so does `scripts/aggregate_benchmarks.py` (see R-5). A
test loads every stored record file.

**Why.** Ruling R3, plus the skeptic's point that a mean over both kinds
would present itself as one number. Excluding old records by default was
rejected: Phase 2 re-scores them.

## R-12 What the smoke run can and cannot prove

The smoke run (one todo-api cell) proves SC-001, SC-002, SC-003, SC-006
and the positive half of SC-007. Everything else is proved by
deterministic tests (skeptic L8); the contract's proof table says which.

## R-13 What stays out, and what the documents must say

Left to Phase 2: the $0.00 cost on subscription-billed harness records
and first-attempt versus after-repair scoring. `BENCHMARK.md` gains two
sentences (skeptic L9): dollars on harness records are not measured and
tokens are the usable volume figure; the code stage's quality is the
share of attempts that passed, not of tasks.

## Consult log

| Source | Point | Outcome |
|---|---|---|
| advisor D1 | per-grade venv via `_ensure_python_env`, case-owned oracle requirements, allowlisted env, empty-diff guard | adopted (R-6) |
| advisor D2 | new cell-scope record; completion read from the cell's records | adopted, with a typed status object instead of numeric components (R-4) |
| advisor D3 | `PROMPT_SHAS`; commit resolved once and carried on the config | adopted, keyed by role because record stage names differ from registry stage names (R-7) |
| advisor D4 | `arm` field, fallback to `model` for old records | adopted, plus `cell_id` (R-8) |
| advisor D5 | score `None`, no new outcome | overruled on evidence: readers count `outcome is FAIL` (R-5) |
| advisor D6 | leaf `paths.py`, CLI pre-flight plus raising activity | adopted (R-1, R-2); single three-vocabulary table not adopted (R-3) |
| advisor D7 | timestamps at the call sites, review spend; move recorders out of `step.py` | first two adopted; the move not needed (R-9) |
| skeptic L1 | file key and groupings must not use `model` | adopted (R-8) |
| skeptic L2 | evidence standard for "not evaluated" | adopted (R-10) |
| skeptic L3 | tri-state commit; no mixed means | adopted (R-7, R-11) |
| skeptic L4 | honour the override; exempt drift; only active stages | first two hold by construction; third rejected with reason (R-2) |
| skeptic L5 | BREAKS: the branch exists before code runs | adopted; the graded line is redefined (R-4) |
| skeptic L6 | hash must cover prompt builders | not adopted; limit documented, follow-up filed (R-7) |
| skeptic L7 | isolate the runtime and assert the diff | adopted (R-6) |
| skeptic L8 | the smoke run proves four criteria only | adopted (R-12) |
| skeptic L9 | document the cost and quality limits | adopted (R-13) |
