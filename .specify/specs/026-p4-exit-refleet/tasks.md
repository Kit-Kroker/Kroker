# Tasks: round 026, P4 exit fixes plus a smaller re-fleet

**Input**: `.specify/specs/026-p4-exit-refleet/`: spec.md (US A1–A4; FR-001..006, FR-010..012, FR-020..023, FR-030, FR-040, FR-050..054; SC-A1..A4, SC-B1..B4; GATE 1 record; amendments A-1..A-8), plan.md revision 2 (steps A1–A6, B), research.md R1–R9, data-model.md, quickstart.md, consults/.

There are two halves in this one file:

- **Part A = T001–T027.** Code. One L crew round, test-first.
- **Part B = T040–T052.** Operations, **paid**. Part B starts only when T027 is merged and verified, **T008's $0 re-score reproduced the 025 baseline**, and GATE 2 is cleared. `[OPS]` tasks are done by the operator or orchestrator, and each run is **announced before it starts**.

**Tests**: REQUIRED. Every Part A implementation task is preceded by a RED task that must fail first, and the GREEN commit body shows the red→green. T011 is move-only; its proof is unchanged-green merge tests plus an identity test.

**Sizes**: **S** is about 30 minutes or less; **M** is one focused sitting. No task is L.

**Executor rules (Part A)**:

- One commit per task, with the task id in the subject.
- Never `git add -A`. Never stash. Never revert files you did not create. The tree is shared.
- **Read the nearest AGENTS.md before editing** a slice: `src/sdlc/stages/code/AGENTS.md`, `src/sdlc/stages/qa/AGENTS.md`, `src/sdlc/stages/merge/AGENTS.md`, `src/sdlc/stages/review/AGENTS.md`, `src/sdlc/workflows/AGENTS.md` (for `src/sdlc/benchmarks/workflow.py`).
- Commands run from the repo root with `uv run`.
- Run `uv run python scripts/check_file_size.py` in every task that touches `src/sdlc/stages/code/step.py` (977/1000; net budget ≤ +10) or `src/sdlc/benchmarks/sc_rollup.py` (418; budget ≤ 470, overflow per plan "Technical context").
- **Never write to `/home/maksim/work/kroker-fleet-runs-025` or `/home/maksim/work/scratch-repos`.** Work on a copy made with `D=$(mktemp -d)`. Never `rm -rf` a variable-derived path.

**Standing constraints (FR-040)**:

- No change to `lint_clean`, `MERGE_REQUIRED_CHECKS`, gate-policy semantics, `auto_decision_for`, containment or ADR-6.
- No change to `GraphWorkflow`, and no new activity, timer, signal or child workflow. `BenchmarkWorkflow` gets only T004's string edit.
- Defaulted, additive fields only.
- Part B changes no code.

---

## Part A, slice A1: the scorer reads what the fleet wrote (FR-001 to FR-005) [US A1, P1]

**Story goal:** `benchmark score` over a fleet root renders SC-1, SC-2 and the commit set with every scored run accounted for. **Independent test:** T008's $0 re-score of a 025 copy.

- [ ] **T001 [S] RED: run paths.** Create `tests/test_runs_paths.py` (module `sdlc.runs_paths` does not exist yet, so the import fails: RED). Cases:
  - **Parity:** for each environment combination (none; `SDLC_RUNS_ROOT=X` only; `X` plus explicit `SDLC_EXPORT_ROOT=Y`; `X` plus explicit `SDLC_BENCHMARKS_ROOT=Z`; explicit only), the writer roots (`recorder._root()` and the path `export_run_artifacts` computes) equal the reader roots (`evidence`), and `roots_report()` names the `how` (`explicit` / `runs_root` / `default`) for each half.
  - **Defaults** unchanged: `runs/benchmarks` and `./runs/pipeline`.
  - **Source guard:** an AST scan of `src/sdlc/` finds no module except `runs_paths.py` *reading* `SDLC_EXPORT_ROOT` or `SDLC_BENCHMARKS_ROOT` from `os.environ` (`.get`, a subscript load, `getenv`). Writes are allowed: `src/sdlc/demo/__main__.py:56` *sets* `SDLC_EXPORT_ROOT` for its child, and that stays. Pattern: `tests/test_judge_literal.py`.
  - `explicit_export_root()` returns the explicit `SDLC_EXPORT_ROOT` or `None`, for `graph/store.py`'s sibling rule.

  Run `uv run pytest -q tests/test_runs_paths.py`. It must FAIL. *(FR-001, research R1)*
- [ ] **T002 [M] GREEN: `S/runs_paths.py`.** Create `src/sdlc/runs_paths.py` with `benchmarks_root()`, `export_root()`, `explicit_export_root()` and `roots_report()`. Route these 8 sites through it, changing no other logic:
  - `src/sdlc/observability/activities.py:28`
  - `src/sdlc/artifacts/store.py:48`
  - `src/sdlc/observability/decisions.py:83`
  - `src/sdlc/calibration/store.py:110`
  - `src/sdlc/demo/run.py:100`
  - `src/sdlc/benchmarks/evidence.py:53`
  - `src/sdlc/benchmarks/recorder.py:24`
  - `src/sdlc/graph/store.py:109-110` (via `explicit_export_root()`; the sibling rule and its precedence are kept exactly)

  `load_evidence`'s `root`/`export_root_` arguments still win. Run `uv run pytest -q tests/test_runs_paths.py tests/test_benchmark_score.py tests/test_benchmark_sc_rollup.py` and `uv run pytest -q -k "calibration or export or artifact_store or graph_store"`.
- [ ] **T003 [S] RED: no-summary runs and smoke exclusion.** In `tests/test_benchmark_evidence_roots.py`, build fixtures under `tmp_path`:
  - one summarized run;
  - a crashed run: a cell record with `pipeline_finished=False` and `child_result` `"ChildWorkflowError: …"`, no summary;
  - a timed-out run: a cell record with `pipeline_finished=False` and `child_result` `"ChildWorkflowError(cause=TimeoutError): …"`;
  - a terminated run: stage and task records only, no cell record, no summary;
  - a summary-missing run: a cell record with `pipeline_finished=True` but no summary;
  - a smoke-case run (the `case_id` of `smoke_case(...)`).

  Assert:
  - `Evidence.no_summary` lists those four runs with classes `crashed`, `timed_out`, `terminated` and `summary_missing`;
  - `excluded_smoke == [smoke id]`;
  - `selection_runs` counts non-smoke runs only.

  Run `uv run pytest -q tests/test_benchmark_evidence_roots.py -k "no_summary or smoke"`. It must FAIL. *(FR-002, FR-004, research R2)*
- [ ] **T004 [M] GREEN: evidence classification and the cause type.** In `src/sdlc/benchmarks/evidence.py`, add `NoSummaryRun`, `Evidence.roots`, `no_summary` (keyed on the cell record's `pipeline_finished`, research R2) and `excluded_smoke`.
  - **Read `src/sdlc/workflows/AGENTS.md` first.** In `src/sdlc/benchmarks/workflow.py:383`, the child-failure string gains the cause type: `f"{type(e).__name__}(cause={type(e.cause).__name__}): {e}"` when `e.cause` is set. It is string-only and replay-safe (the 021 precedent). Add a test in `tests/test_benchmark_workflow*.py` (or the nearest existing cell-record test) asserting the format.
  - Settle research R2's **unverified** item: can the smoke case's catalog role be read without the private cases root? If yes, exclude by role. If not, exclude by `case_id == smoke_case(cases_dir()).case_id`. Record which in the commit body.
  - Run `uv run pytest -q tests/test_benchmark_evidence_roots.py`.
- [ ] **T005 [S] RED: rollup accounting and roots line.** In `tests/test_benchmark_sc_rollup.py`, assert:
  - SC-1's `n` = summaries + no-summary runs, and every no-summary run is a miss;
  - SC-2 and SC-2-all name no-summary runs as not measured, with their class;
  - SC-1's n is the distinct non-smoke run_ids, and a summary with no records stays under the existing commit flag (not added to n);
  - markdown, HTML and JSON each carry the roots line: "records: … (how); summaries: … (how); k of n scored runs summarized; no-summary: id: class; smoke excluded: ids".

  Run `uv run pytest -q tests/test_benchmark_sc_rollup.py -k "roots or no_summary"`. It must FAIL. *(FR-002, FR-003)*
- [ ] **T006 [M] GREEN: rollup and score rendering.** In `src/sdlc/benchmarks/sc_rollup.py` (`build_sc_rollup` gains `no_summary` and `roots` inputs) and `src/sdlc/benchmarks/score.py` (pass them through), render all three formats. Existing rollup tests must stay green unchanged. Run `uv run pytest -q tests/test_benchmark_sc_rollup.py tests/test_benchmark_score.py` and `uv run python scripts/check_file_size.py`.
- [ ] **T007 [S] Docs.** In `docs/operations/fleet-runs.md`, update the scoring section: `SDLC_RUNS_ROOT` now drives both halves through `runs_paths`, and the named behavior change for hosts exporting it; explain the roots line, the four no-summary classes and the smoke exclusion. Then run `uv run --no-sync mkdocs build --strict`.
- [ ] **T008 [S] The $0 re-score of 025 (FR-005, Part B entry condition).** Make a copy with `D=$(mktemp -d) && cp -a /home/maksim/work/kroker-fleet-runs-025/. "$D"/`, then run `SDLC_RUNS_ROOT="$D" uv run python -m sdlc.cli benchmark score --all`.
  - Assert the quickstart's expected list: 4 of 6 summarized; `…readtime-1794957781-bccb20` crashed; `…lice-1794980735-e87339` terminated; smoke excluded; commit set `{ce3a36f8…}`; SC-1 0.00 (n=6); SC-1-strict 0.00; SC-2-all n/a (4 measured); SC-3 0.385 (n=13), with `SC-3-non-lint` 0.385 and `SC-3-lint` n/a (legacy loops count as non-lint).
  - **This task depends on T010 and T023** (it is ordered after them) so that SC-1-strict and the SC-3 rows also print.
  - Paste the output into `.specify/specs/026-p4-exit-refleet/verification.md` §026-A "025 baseline".
  - Any mismatch STOPs and is reported.

## Part A, slice A2: the PRD-aligned SC-1 (FR-006, A-2) [US A1, P1]

- [ ] **T009 [S] RED: SC-1 rule.** In `tests/test_benchmark_sc_rollup.py`, the rule is that a gate is unplanned when `decided_by != "policy"` and (`gate ∉ STAGE_GATES` or `policy == "soft"`); a planned gate with a non-policy decider and an outcome other than `approve` is steering. Cases:
  - HARD stage gates human-approved, no `task:*` → hit;
  - a `task:T-1` gate human-decided → miss;
  - a `task:T-1` gate decided by `timeout` → miss (an escalation was raised);
  - an unknown gate name `foo` human-decided → miss (fail-closed);
  - clarification outcomes never affect SC-1;
  - `tool_approval` human-decided → miss;
  - a SOFT `architecture` gate human-decided → miss;
  - a HARD `plan` gate human-decided with outcome `revise` → miss (steering guard);
  - a policy-decided gate → ignored;
  - a merge override with `decided_by="reviewer-name"` → human;
  - `SC-1-strict` row present with the 025 rule;
  - the 95% exact (Clopper-Pearson) CI string for 4/5 is `[0.28, 0.99]`;
  - the note names `STAGE_GATES`, the steering guard and the planned-gate count.

  Run `uv run pytest -q tests/test_benchmark_sc_rollup.py -k sc1`. It must FAIL. *(FR-006, research R3)*
- [ ] **T010 [M] GREEN: SC-1.** In `src/sdlc/benchmarks/sc_rollup.py`, add `STAGE_GATES`, `_unplanned`, the reworked `_sc1`, `_sc1_strict` (the existing `_unattended_to_merge`), and a pure `_clopper_pearson(k, n)` with no new dependency (use the `math`/`statistics` stdlib or the closed-form beta quantile by bisection). Render all three formats. Run `uv run pytest -q tests/test_benchmark_sc_rollup.py tests/test_benchmark_score.py` and `uv run python scripts/check_file_size.py`.

## Part A, slice A3: per-task lint (FR-010 to FR-012, Q2-A) [US A2, P1]

**Story goal:** a task that leaves lint dirty learns it inside its own fix loop, never first at merge. **Independent test:** T012, T014, T016 and T017.

- [ ] **T011 [S] Move-only: `lint_scope`.** Read `src/sdlc/stages/merge/AGENTS.md` first. Move `_lint_nc`, `_lint_point`, `_policy_and_suppressions`, `_lint_key` and `scoped_lint` from `src/sdlc/stages/merge/scoping.py`, and `LintFinding` and `ScopedLintReport` from `src/sdlc/stages/merge/models.py`, to a new `src/sdlc/toolchain/lint_scope.py`, unchanged. `scoping.py` and `merge/models.py` re-import and re-export the same names (the JSON wire format is unchanged).
  - Add `tests/test_lint_scope.py`, asserting `sdlc.stages.merge.scoping.scoped_lint is sdlc.toolchain.lint_scope.scoped_lint` and `sdlc.stages.merge.models.ScopedLintReport is sdlc.toolchain.lint_scope.ScopedLintReport`.
  - Run `uv run pytest -q tests/merge/ tests/test_lint_scope.py`: green, with no merge test edited.
  - Check that no qa or code module imports `stages.merge` (`grep -rn "stages.merge\|from \.\.merge" src/sdlc/stages/qa src/sdlc/stages/code` prints nothing new).
- [ ] **T012 [M] RED: autofix before checkpoint.** In `tests/code/test_autofix_checkpoint.py`, use a git repo fixture with a Python file that has an unsorted import (I001) and a test file under a fenced glob. Assert:
  - (a) `PythonAdapter.lint_fix_cmd(files)` is `ruff check --fix --force-exclude --exit-zero --no-cache -- <files>` (no `--unsafe-fixes`), and the base adapter returns `None`;
  - (b) `run_coding_task` (harness faked) leaves the I001 fixed **inside the checkpoint commit** (`git show HEAD` contains the fix, the worktree is clean), and `result.lint_autofix` lists the file and `{"I001": 1}`;
  - (c) with `repair=True`, a fenced test file the attempt changed is **not** autofixed, and the drift check (`check_test_drift` against the new anchor) reports `found=False`;
  - (d) the autofix command failing logs WARNING and the checkpoint still commits;
  - (e) only `*.py` files the attempt changed are passed to the command, and no file is added to the diff's file set.

  Run `uv run pytest -q tests/code/test_autofix_checkpoint.py`. It must FAIL. *(FR-011, research R4, skeptic 4)*
- [ ] **T013 [M] GREEN: autofix.**
  - `src/sdlc/toolchain/adapters.py`: `lint_fix_cmd`.
  - Read `src/sdlc/stages/code/AGENTS.md` first.
  - `src/sdlc/toolchain/lint_scope.py`: `LintAutofix(files, rules)`.
  - `src/sdlc/stages/code/activities.py`: before `git add` and the checkpoint, list the changed `*.py` files (`git status --porcelain`), drop fenced paths (`repair_patterns(policy)`) when `inp.repair`, run the adapter command with a bounded shell, and record the applied fixes on the result's new `lint_autofix` field.
  - Run `uv run pytest -q tests/code/ tests/test_lint_scope.py`.
- [ ] **T014 [M] RED: scoped lint in `run_test_suite`.** In `tests/qa/test_task_lint.py`, assert:
  - `QAInput(lint_base=None)` leaves `QAReport.lint is None` and runs the tests unchanged;
  - with `lint_base` set to the base commit and a head introducing one PERF102, `lint.state` is MEASURED and `lint.introduced` holds exactly that finding, and a pre-existing finding is not reported;
  - the base worktree is created as a sibling of the task worktree (under the worktrees root, key `lint_key`), never in `/tmp`, and is removed afterwards;
  - an unmaterializable base gives NOT_COLLECTED with a reason, and `tests_passed` is unaffected;
  - a finding in a `lint_report_only` path is present in the report;
  - the tests run **before** lint, and their outcome is identical with and without lint.

  Run `uv run pytest -q tests/qa/test_task_lint.py`. It must FAIL. *(FR-010)*
- [ ] **T015 [M] GREEN: task lint.**
  - Read `src/sdlc/stages/qa/AGENTS.md` first.
  - `src/sdlc/vcs/integration.py`: lift `prepare_base_worktree`'s body into `materialize_base(repo_wt, sha, dest)`, which the activity keeps calling. Merge's behavior is unchanged, and `tests/merge/` stays green.
  - `src/sdlc/stages/qa/activities.py`: `QAInput.lint_base`, `lint_key` and `lint_report_only`. After the test run, materialize the sibling base, call `toolchain.lint_scope.scoped_lint` verbatim with renames from `git diff -M --name-status`, and remove the base in a `finally`.
  - `src/sdlc/stages/qa/models.py`: `QAReport.lint: ScopedLintReport | None = None`.
  - Run `uv run pytest -q tests/qa/`.
- [ ] **T016 [M] RED→GREEN: wiring into the fix loop, plus the replay proof.** RED first, in `tests/code/test_task_lint_loop.py`:
  - (a) a task whose tests pass but whose `lint.introduced` (outside `lint_report_only`) is non-empty fails the attempt, and the next attempt's prompt contains the block "lint findings introduced by this task (the merge gate's own check):", capped at 25 lines plus "(+N more)";
  - (b) a NOT_COLLECTED report, `lint is None`, and findings only in report-only paths do not fail the attempt;
  - (c) the QA record's outcome ignores lint, while the code record's follows `task_passed`;
  - (d) the QA prompt (`qa_step`) and the review and adversary prompts (`_get_qa_raw_json`) do **not** contain the lint field.

  Run `uv run pytest -q tests/code/test_task_lint_loop.py`. It must FAIL before GREEN.

  GREEN:
  - `src/sdlc/stages/code/attempt_failure.py` (new): `_lint_ok(qa_raw, report_only)`.
  - `src/sdlc/stages/code/step.py`: pass `lint_base=branch_point`, `lint_key=f"{_workflow_id()}/base-{task.id}"` and `lint_report_only=` the fence globs on repair attempts into `QAInput`; add `and _lint_ok(...)` to `task_passed`.
  - `src/sdlc/stages/qa/step.py`: the `_fix_loop_issues` lint block, and lint excluded from the `qa_step` prompt dump.
  - `src/sdlc/stages/review/step.py`: exclude lint in `_get_qa_raw_json`. Read `src/sdlc/stages/review/AGENTS.md` first.

  Then run `uv run pytest -q tests/code/ tests/qa/ tests/merge/ tests/review/`, `uv run pytest -q tests/replay`, `uv run pytest -q -m temporal -k "replay or golden"` and `uv run python scripts/check_golden_rebaseline.py`, plus `uv run python scripts/check_file_size.py` (`step.py` must stay ≤ 1000; overflow → move the record block to `src/sdlc/stages/code/attempt_record.py`, move-only).

  **Settle research R4's unverified item**: if a golden pins a serialized `QAInput` or `QAReport`, regenerate it only if the diff is defaulted keys only, and otherwise STOP and report. *(FR-010, FR-040)*
- [ ] **T017 [S] Lint parity proof.** In `tests/test_lint_scope.py`, prove that for one fixture tree, the per-task path (`run_test_suite` lint) and the merge path (`run_integration_checks`' scoped lint) produce the same `introduced` list for the same base and head: same binary, same command (`adapter.lint_json_cmd()`), same configuration resolution. Run `uv run pytest -q tests/test_lint_scope.py`. *(US A2 AS3)*
- [ ] **T018 [S] Offline conversion read (no model calls).** Using `git archive` of the surviving 025 integration branches into `$(mktemp -d)` (read-only on `/home/maksim/work/scratch-repos`), run the T013 autofix command over each tree, then `ruff check --statistics`. Record cat-cafe, geotext and lice before→after counts (expected 22→4, 24→15, 74→42 per spec H3) in verification.md §026-A as the "autofix alone" read. This task is evidence only; no assertion.

## Part A, slice A4: failure reasons and the triage (FR-020 to FR-023, A-4) [US A3, P2]

**Story goal:** every 025 failure and loop has a classified cause, and every new failed attempt records why. **Independent test:** T019, T021 and T024's 18-row table.

- [ ] **T019 [S] RED: `AttemptFailure`.** In `tests/test_attempt_failure.py`, assert:
  - `attempt_failure(qa_raw, qa, review, drift)` returns `None` on a pass;
  - its `checks` are an ordered subset of `tests, qa, drift, review, lint, no_feedback`;
  - `summary` equals `_fix_loop_issues(qa, qa_raw, review)` plus the drift note, truncated to ≤ 500 chars (the text the dev was shown);
  - a legacy `BenchmarkRecord` JSON without `failure` loads with `None`.

  Run `uv run pytest -q tests/test_attempt_failure.py`. It must FAIL (ImportError). *(FR-021)*
- [ ] **T020 [M] GREEN: field and wiring.**
  - `src/sdlc/benchmarks/models.py`: `AttemptFailure` and `BenchmarkRecord.failure`.
  - `src/sdlc/stages/code/attempt_failure.py`: the pure `attempt_failure(qa_raw, qa, drift, review_ok, review)`, called unconditionally before the code record.
  - `src/sdlc/stages/code/step.py`: `failure=` on the code record (full set) and the QA record (`tests` and `qa` only). `stage_record` gains a defaulted `failure` kwarg.
  - `src/sdlc/stages/review/step.py:151-167`: `failure=AttemptFailure(checks=["review"], summary=<blocking findings>)` on a failed review record.
  - Never write the reason into `error`.
  - Run `uv run pytest -q tests/test_attempt_failure.py tests/code/ tests/review/` and `uv run python scripts/check_file_size.py`.
- [ ] **T021 [M] RED (conditional): run 1's crash mode.** Read `src/sdlc/stages/research/AGENTS.md` (if present) and research R6.
  - **Settle evidence first.** Read run 1's records and preflight notes, and any transcript under `/home/maksim/work/kroker-fleet-runs-025/pipeline/` (read-only). Is the death consistent with CodeMode's `run_code` exhausting its 3 retries inside the architect's `research` tool (`research_subquery_reported`)? Record the evidence in the commit body.
  - Then in `tests/test_architect_research_degrade.py`, drive `research_subquery_reported` outside durable execution with a `FunctionModel` that emits `run_code` calls whose code raises `TypeError("unsupported operand for +: 'Result' and 'Result'")` 4 times. If Monty is unavailable in the fast tier, use a stub inner agent raising `pydantic_ai.exceptions.UnexpectedModelBehavior`, and say so in the test docstring. Assert:
    - a gap brief whose `gaps` contains OUR fixed text, not `str(exc)` (no library URL);
    - usage is still reported;
    - a provider-style `RuntimeError` still propagates (residual R1 kept for infra).
  - Check whether the research stage's own sub-question loop already degrades on a failed sub-run. Record the answer in the commit body.
  - Run `uv run pytest -q tests/test_architect_research_degrade.py`. It must FAIL today.
  - If the evidence contradicts this mechanism: classify the triage row on that evidence, **skip T022**, and file a backlog card.
- [ ] **T022 [S] GREEN (conditional): the narrow degrade.** In `src/sdlc/stages/research/toolset.py`, add `except UnexpectedModelBehavior` beside `UsageLimitExceeded`. It returns `_gap_brief` with OUR text ("research tool exhausted its code-execution retries") and keeps reporting usage. **Do not catch bare `Exception`.** Update the docstring's residual-R1 sentence to name what still propagates. Run `uv run pytest -q tests/test_architect_research_degrade.py tests/research/`. This is surfaced at GATE 2 (plan item 1).
- [ ] **T023 [S] RED→GREEN: SC-3 rows.** RED, in `tests/test_benchmark_sc_rollup.py`:
  - `SC-3-non-lint` and `SC-3-lint` partition the loops;
  - a loop is lint-only when every failed code record has `failure.checks == ["lint"]`;
  - legacy loops with `failure is None` count as non-lint;
  - SC-3 is unchanged.

  Run `uv run pytest -q tests/test_benchmark_sc_rollup.py -k sc3`. It must FAIL before GREEN.

  GREEN in `src/sdlc/benchmarks/sc_rollup.py`. Run `uv run pytest -q tests/test_benchmark_sc_rollup.py` and `uv run python scripts/check_file_size.py`. *(A-4)*
- [ ] **T024 [M] Triage table (FR-020/023).** Write `.specify/specs/026-p4-exit-refleet/triage.md` with 18 rows: 5 scored failures plus 13 fix loops (per-case loop list from `fleet-report.md`).
  - Each row: run, task, attempt count, failing check(s), class (harness defect / agent-tool defect / check-or-reviewer behavior / case difficulty / cause not recoverable), and an evidence pointer (`pipeline/<uuid>/sessions/T*-a*.jsonl` line, or a record).
  - Read-only on the 025 root.
  - For each row classed harness or agent-tool, state "fixed by T0xx" or "backlog card <path>" (FR-023: only fixes that fit one M task are done in this round).

## Part A, slice A5: the `.env` rider (FR-030) [US A4, P3]

**Story goal:** local verification is immune to the operator's `.env`. **Independent test:** the fast tier with the fleet `.env` present equals the baseline ids.

- [ ] **T025 [S] RED: dotenv isolation.** In `tests/test_dotenv_isolation.py`, write a `.env` with `KROKER_HARNESS_QUEUE=polluted` into `tmp_path`. Spawn a child Python process from `os.environ` (cwd=`tmp_path`) that calls `dotenv.load_dotenv(dotenv.find_dotenv(usecwd=True))` and prints `os.environ.get("KROKER_HARNESS_QUEUE")`. Assert it prints `None`. Run `uv run pytest -q tests/test_dotenv_isolation.py`. It must FAIL. *(research R7)*
- [ ] **T026 [M] GREEN: the import-time flag and follow-ups.**
  - In `tests/conftest.py`, **at import** (module top, before any `sdlc` import that triggers `load_dotenv`), set `os.environ["PYTHON_DOTENV_DISABLED"] = "1"`.
  - `tests/test_prompt_gate_mutations.py:54-56`: switch to `os.environ.update(dotenv_values())`.
  - Add a `child_env(**overrides)` helper in `tests/conftest.py` that starts from `os.environ`. Use it at every from-scratch `env=` site that spawns the `sdlc` CLI (`grep -rn "env=" tests/ | grep -v os.environ`; convert only the sites that spawn the CLI, and list them in the commit body).
  - Run `uv run pytest -q tests/test_dotenv_isolation.py`, then the six files named in `.workspace/tasks/2026-11-18-env-pollutes-cli-tests.md` **with the fleet `.env` present at the repo root**.

## Part A, slice A6: close-out

- [ ] **T027 [M] Battery and A close-out.**
  - With the fleet `.env` **present**, run `uv run pytest -q` and compare against `.specify/specs/024-two-worker-pools/baseline-failures.txt` (novel ids: none).
  - Run `uv run ruff check . && uv run ruff format --check . && uv run mypy`, `uv run python scripts/check_file_size.py`, `uv run pytest -q tests/replay`, `uv run pytest -q -m temporal -k "replay or golden"`, and `uv run --no-sync mkdocs build --strict`.
  - `git diff --stat <round-start>..HEAD -- src/sdlc/workflows src/sdlc/gate.py src/sdlc/calibration/decision.py src/sdlc/stages/merge/step.py src/sdlc/harness` must be empty (FR-040). `src/sdlc/calibration/store.py` may show only T002's resolver routing, and `src/sdlc/benchmarks/workflow.py` only T004's string.
  - Write `.specify/specs/026-p4-exit-refleet/verification.md` §026-A: each command and result, the T008 baseline, the T018 read, the T024 summary, and the red→green ledger.
  - Name the fleet commit candidate. *(SC-A1..A4)*

**Checkpoint, Part A done.** The reviewer has passed every task; Part A is merged; T008 reproduced the baseline. Do not start T040 without GATE 2.

---

## Part B: the re-fleet `[OPS]` (FR-050 to FR-054)

Part B uses the **fleet commit** in a dedicated clean checkout. **No commit lands between T042 and the last scored run.** `--gate-policy hard` applies everywhere. The 025 B.4–B.6 rules bind unless amended here.

- [ ] **T040 [OPS][M] Pre-flight evidence.** Write `.specify/specs/026-p4-exit-refleet/preflight.md`, evidencing with command output:
  - The verbs and `--arm` name from `src/sdlc/benchmarks/cli.py`.
  - Doctor green.
  - Pools overlay up, harness cap ≥ 2.
  - The 025 host fixes present: `KROKER_HARNESS_QUEUE=default` in the fleet checkout `.env`; `safe.directory` entries for all five scratch repos; the read-only opencode `auth.json` bind; the image built with `--build-arg KROKER_COMMIT=<fleet commit>`.
  - z.ai, judge and EXA keys.
  - `adversarial_review_enabled` False, and `containment_enabled` False in a dumped cell config (research R4).
  - A fresh, dedicated `SDLC_RUNS_ROOT`, and the scorer's roots line printing it (T006).
  - Scratch repos: a fresh seeding per case (025 T021 path). The 025 branches stay untouched as evidence; use a new repo dir or confirm the case seeding creates a clean `main`.
  - **Attendant (A-3/A-5):** services pending gates **and** clarification waits; approve-only on planned gates (any REVISE disclosed as steering); 30-minute idle watchdog; cost polled every 60 s against the per-run stop; ledger on.

  If any item fails: STOP. *(FR-050)*
- [ ] **T041 [OPS][S] Freeze.** Create the dedicated checkout at the fleet commit and assert `git status --short` is empty. Record the commit and announce the freeze.
- [ ] **T042 [OPS][M] Smoke (paid, unscored, announced).** Announce an expected judge spend of $1.94 (025 measured). Run `SDLC_RUNS_ROOT=<dir> uv run python -m sdlc.cli benchmark smoke --gate-policy hard`.
  - PASS writes the stamp.
  - A case-difficulty failure STOPs for the owner.
  - An infra failure counts toward the two-stop limit.
  - Record the measured judge cost.
- [ ] **T043 [OPS][S] Ceiling re-announce.** The judge ceiling is $13.95 + research $1.00 (spec B.5). If the smoke's measured cost exceeds $1.94 × 1.5, re-derive the ceiling as 1.5 × (smoke measured + scored expected) and **STOP for the owner** if it exceeds $13.95. Per-run stops: cat-cafe $3.00, readtime $1.73, geotext $1.91, lice $1.40. Record in `preflight.md`.
- [ ] **T044 [OPS][M] Run 1: cat-cafe-monitoring.** Announce (run number, case, arm, commit, expected cost, spend so far, ceiling left). Run `SDLC_RUNS_ROOT=<dir> uv run python -m sdlc.cli benchmark run --case benchmarks/cases/cat-cafe-monitoring/case.yaml --arm zai-coding-plan-glm-5.3 --gate-policy hard`, with the attendant servicing planned gates and clarifications. Post-run report: outcome; class by the pre-registered rule (a `timeout` on a planned gate is infra); cost; unplanned-escalation count; planned interactions; `lint_clean` blocked or not. Infra → STOP. *(FR-051)*
- [ ] **T045 [OPS][M] Run 2: deveval-readtime** (same procedure; sequential until runs 1 and 2 have both completed).
- [ ] **T046 [OPS][M] Run 3: deveval-geotext** (same procedure; at most 2 concurrent from here).
- [ ] **T047 [OPS][M] Run 4: deveval-lice** (same procedure; may overlap run 3).
- [ ] **T048 [OPS][M] Run 5: cat-cafe-monitoring, repeat** (same procedure).
- [ ] **T049 [OPS][S] Run 6 decision (conditional).** Run deveval-readtime once more **only if** fewer than 5 scored runs are SC-2-measured (summarized) **and** the remaining judge headroom is ≥ $1.73 (A-5, A-7). Otherwise record "run 6 not needed" or "run 6 not affordable". Never exceed 6, and do not extend the delegation.
- [ ] **T050 [OPS][M] Score and fleet report.** Run `SDLC_RUNS_ROOT=<dir> uv run python -m sdlc.cli benchmark score --all`, and save the outputs beside `fleet-report.md` in the runs root. The report contains:
  - the roots line;
  - the commit set (must be one, read by the rollup);
  - SC-1 (PRD rule) with n, the CI and `SC-1-strict`;
  - SC-2 shipped and all-scored with the evidence tier;
  - SC-3 overall, `SC-3-non-lint` and `SC-3-lint`;
  - **the delta of each against the 025 baseline** (T008);
  - the lint conversion read (merge-reaching runs blocked by `lint_clean`: 025 3/3);
  - the MergeVerdict-not-exercised disclosure (A-3);
  - failures and infra tables;
  - a per-class triage of this fleet's loops from `failure.checks`;
  - spend against the ceiling;
  - an honest-miss section naming each remaining gap's cause. *(FR-052/053/054, SC-B1..B4)*
- [ ] **T051 [OPS][S] P4 read.** Update the `ROADMAP.md` SC-1/2/3 rows and the P4 line with the measured read and its deltas, citing the fleet report. Append §026-B to `.specify/specs/026-p4-exit-refleet/verification.md`. Remove the dedicated checkout (by its literal path).
- [ ] **T052 [OPS][S] Card closes.**
  - Mark 025's `tasks.md` T034 `[x]`, with the note "closed by 026 FR-001..004 (the summaries existed; root resolution fixed)".
  - Set `.workspace/tasks/2026-11-18-env-pollutes-cli-tests.md` Status to done, citing T026.
  - File `.workspace/tasks/<date>-calibration-ledger-misses-benchmark-summaries.md`: `calibration/store.py`'s one-level `*/summary.json` glob never sees `bench-…/<cell>/summary.json` (advisor D1; FR-040 kept it out of this round).
  - Write `.workspace/tasks/<date>-round-026-close-out.md` in the 025 close-out format.

---

## Dependencies

**Part A, internal order:**

- A1: T001→T002→T003→T004→T005→T006→T007 (T002 touches 8 files; run it alone).
- A2: T009→T010.
- A3: T011→T012→T013→T014→T015→T016→T017; T018 any time after T013.
- A4: T019→T020→T023. T021→T022 (conditional). T024 after T020 (it uses the field's classes).
- A5: T025→T026.
- **T008 after T006, T010 and T023.**
- T027 last.

**Parallel**: the slices A1/A2, A3, A4 and A5 touch disjoint files, except `sc_rollup.py` (A1 T006, A2 T010, A4 T023 run in that order) and `stages/code/step.py` (T016 then T020, in that order).

**Part B**: T027 + T008 → GATE 2 → T040→T041→T042→T043→T044→T045→(T046 ∥ T047)→T048→T049→T050→T051→T052.

## Parallel execution examples

- **Crew of two after T002:** one executor takes A3 (T011→T017), and the other takes A1's T003–T007 then A2's T009–T010. They meet at `sc_rollup.py` order (T006 → T010 → T023) and at `stages/code/step.py` order (T016 → T020).
- **Independent any time:** A5 (T025→T026); T018 after T013.
- **Part B:** runs 3 and 4 (T046 ∥ T047) only, per the 025 overlap rule.

## Implementation strategy

1. **MVP is US A1 (A1 + A2) plus T008.** That alone makes SC-1 and SC-2 measurable, and it is proven for $0 on the 025 data. If the round had to stop early, this is the slice that carries evidence.
2. **Then US A2 (A3):** the lint conversion, the one measured blocker with a targeted fix.
3. **Then US A4 (A5)**, which is small and unblocks honest local batteries, and **US A3 (A4)**, which carries the triage and the field. The run-1 fix is the first thing cut on an L overrun (spec Assumptions; plan cut line).
4. **T027 closes Part A.** Part B starts only after GATE 2.
