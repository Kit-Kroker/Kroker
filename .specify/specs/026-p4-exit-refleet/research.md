# Research: round 026

`S/` = `src/sdlc/`, `T/` = `tests/`. Everything below was read or run on 2026-11-18. The planner drafted R1–R9. The advisor's consult (`consults/advisor.md`, D1–D7) landed after the first plan pass, and it is merged here; each item says which source decided it. Anything not confirmed is marked **unverified**, and a task settles it.

## R1. Run-path resolution (FR-001; advisor D1 adopted)

**Facts.**

- `SDLC_RUNS_ROOT` drives neither evidence store. Records come from `SDLC_BENCHMARKS_ROOT` or `runs/benchmarks` (`S/benchmarks/recorder.py:17,23-24`). Summaries come from `SDLC_EXPORT_ROOT` or `./runs/pipeline` (`S/benchmarks/evidence.py:30,48-53`).
- The documented scoring command `SDLC_RUNS_ROOT=<dir> sdlc benchmark score --all` (`docs/operations/fleet-runs.md:150`) therefore works only from a CWD whose `runs/` happens to be the fleet root. 025's smoke-stamp misread came from the same gap (025 `verification.md:111`).
- The export-root rule is copied inline in about 8 places:
  - `S/observability/activities.py:28`
  - `S/artifacts/store.py:48`
  - `S/observability/decisions.py:83`
  - `S/calibration/store.py:110`
  - `S/demo/run.py:100`
  - `S/benchmarks/evidence.py:53`
  - `S/benchmarks/recorder.py:24`
  - `S/graph/store.py:109-110`

**Decision.** One stage-neutral resolver module, `S/runs_paths.py`, with `benchmarks_root()`, `export_root()` and `roots_report()`. Every site above calls it.

- Precedence: an explicit `SDLC_BENCHMARKS_ROOT` or `SDLC_EXPORT_ROOT` wins. Otherwise `$SDLC_RUNS_ROOT/benchmarks` or `$SDLC_RUNS_ROOT/pipeline`. Otherwise today's CWD defaults.
- `graph/store.py` routes only its `SDLC_EXPORT_ROOT` read through the resolver and keeps its sibling rule (advisor, unverified item, left as is).
- The `root=` and `export_root_=` arguments on `load_evidence` stay as test seams. An argument beats any environment variable.

**Worker behavior is unchanged.** The containers set no `SDLC_*_ROOT` and run at `/app` with `/app/runs` bind-mounted (`Dockerfile:47`, `docker-compose.yml:75`).

**Named behavior change, surfaced at GATE 2.** A host that exports `SDLC_RUNS_ROOT` but not `SDLC_EXPORT_ROOT` sees its exports and its calibration reads move together to `$SDLC_RUNS_ROOT/pipeline`.

**Drift guards.**

1. A parity test: for each environment combination, the writer roots equal the reader roots.
2. A source-guard test: no module except `runs_paths.py` reads `SDLC_EXPORT_ROOT` or `SDLC_BENCHMARKS_ROOT` from `os.environ`. The repo already has this kind of pin, for example `T/test_judge_literal.py`.

**Rejected alternatives:** a resolver inside the scorer only (planner draft; it would be a ninth copy); a new benchmark export (the files already exist, spec H1).

**Backlog observation (advisor), not this round.** The calibration ledger globs `*/summary.json` one level deep (`S/calibration/store.py:112`), while benchmark `run_id`s contain a `/`. So fleet runs never warm the ledger, one more reason H2's ledger stays cold. FR-040 freezes the calibration rule, so T052 files this as a card.

## R2. Runs with no summary (FR-002/003/004; advisor D2 adopted)

The **cell record is the authority**, keyed on `cell.pipeline_finished`.

| Records for the run | Class | SC-1 | SC-2 |
|---|---|---|---|
| Cell record, `pipeline_finished == False` | `crashed` | miss | not measured |
| No cell record, other records present | `terminated` (operator stop, parent timeout, or still running) | miss | not measured |
| Cell record, `pipeline_finished == True`, no summary | `summary_missing` (fail-closed, flagged) | miss | not measured |

Evidence on the 025 root:

- Run 1 has a cell record with `pipeline_finished: false` and `child_result` "ChildWorkflowError: Child Workflow execution failed".
- Run 6 has 44 stage and task records and **no cell or axis record**.
- The cell record is written only after the child returns or raises (`S/benchmarks/workflow.py:372-385`).

**Timeout cause (advisor, adopted).** The child failure string today is `f"{type(e).__name__}: {e}"` (`S/benchmarks/workflow.py:383`). For a `ChildWorkflowError` that drops `e.cause`, so a timed-out child is indistinguishable from a crash. The string gains the cause type, for example `ChildWorkflowError(cause=TimeoutError): …`. It is only the string passed into the record activity, and Temporal does not compare activity inputs on replay (`S/workflows/AGENTS.md:126-131`, the 021 precedent). A `timed_out` class follows. This touches `BenchmarkWorkflow`, not `GraphWorkflow`, so it is surfaced at GATE 2 as a diagnostic-only workflow-file edit.

**Denominator.** The distinct `run_id`s of non-smoke records. A summary with no records stays under the existing commit flag and is not added to n.

**Smoke exclusion.** By the catalog role if it is readable without the private cases root, else by `case_id == smoke_case(cases_dir()).case_id` (**unverified**; T004 settles it).

## R3. The PRD-aligned SC-1 (FR-006, Q1-A; planner, skeptic 2, advisor D3)

`PRD.md` §8: reach the merge gate "without human intervention beyond configured gates (no unplanned escalations)".

**Rule.**

- `STAGE_GATES = {research, clarify, architecture, plan, merge, deploy}` is a static allowlist. It cannot be config membership: `research` is not in the default `gates` dict and resolves through `default_gate_policy`, exactly like `task:<id>` (advisor D3, `S/core/models.py:381-391`, `S/workflows/gates.py:225-227`). The summary does not carry the config either.
- A gate *g* is **unplanned** iff `g.decided_by != "policy"` and (`g.gate ∉ STAGE_GATES` **or** `g.policy == "soft"`).
  - `!= "policy"` comes from the advisor: a merge override can carry a reviewer name, and a `timeout` on a task gate still means an escalation was raised.
  - The `soft` clause comes from the planner and skeptic: a SOFT gate that fell through to a person is an escalation.
  - Unknown gate names are unplanned (fail-closed). `deploy_failed` is outside the set, and it comes after merge anyway.
- **Steering guard (skeptic 2).** A planned gate decided by a non-policy decider with an outcome other than `approve` disqualifies the run.
- **SC-1 hit:** the run reached merge (`REACHED_PREFIXES`, unchanged; `rejected:merge` counts as reached, and the note says so) with no unplanned gate and no steering before the first `merge` entry.
- Clarification questions are `ClarificationOutcome`, not gates. They never enter SC-1; SC-2 counts them.
- **Companions:** `SC-1-strict` (the 025 rule), the 95% Clopper-Pearson interval, the note listing the set and today's unplanned kinds (`task:<id>`, `tool_approval`, `budget`), and the existing `policy_mix`.

**025 under this rule:** 0.00. Every gate was SOFT and human-decided.

## R4. Per-task lint (FR-010/011/012, Q2-A; planner and advisor D4 merged)

**Facts.**

- The per-task check is `run_test_suite(QAInput(worktree, test_cmd))`, at `S/stages/code/step.py:714-721`, after the harness checkpoint and before QA and review.
- `run_test_suite` and merge's `run_integration_checks` both call `_ensure_python_env` (`S/stages/qa/activities.py:401-403`, `S/stages/merge/activities.py:134-138`), so the ruff binary is merge's by construction.
- The task diff is commit-range only (`S/vcs/git.py:101`), and task branches reach integration by `git merge` (`S/vcs/integration.py:97-124`). So **an uncommitted fix is lost.**
- Only *introduced* findings fail `lint_clean` (`S/stages/merge/step.py:256-265`).
- `qa_step` dumps the whole `qa_raw` into the QA prompt (`S/stages/qa/step.py:177-182`), and review and adversary do the same (`S/stages/review/step.py:75-80,133,207`).

**Decision, in five parts.**

1. **Stage-neutral module (move only).** `_lint_nc`, `_lint_point`, `_policy_and_suppressions`, `_lint_key` and `scoped_lint` (`S/stages/merge/scoping.py:26-129`), plus `LintFinding` and `ScopedLintReport` (`S/stages/merge/models.py`), move to `S/toolchain/lint_scope.py`. `merge/scoping.py` and `merge/models.py` re-export them, so merge is byte-identical. This is needed because qa may not import another stage, and `merge/scoping.py` already imports from `qa/activities` (`:19`), so the reverse import would cycle. Class moves do not change the JSON wire format.

2. **Autofix (FR-011), inside `run_coding_task`, before its checkpoint commit** (`S/stages/code/activities.py:~180-199`). This placement is the planner's, kept over the advisor's "autofix inside `run_test_suite`, then commit plus a workflow-side `_next_anchor` advance".
   - The checkpoint commit then carries the fix to the task branch.
   - The C2 anchor (`commit_sha`) includes it with **no workflow-side anchor logic**.
   - Old histories are untouched by construction.

   From the advisor, adopted:
   - The file list is the task's own Python files changed in this attempt, from `git status --porcelain` filtered to `*.py`. The autofix never adds files, so the `compute_plan_drift` file set is unchanged.
   - The command `ToolchainAdapter.lint_fix_cmd(files)` is `ruff check --fix --force-exclude --exit-zero --no-cache -- <files>`: safe fixes only, config excludes honored. The base adapter returns `None`.
   - On `repair=True`, fenced paths (`repair_patterns(policy)`, loaded activity-side) are excluded.
   - A failure is logged at WARNING and the checkpoint proceeds un-fixed (code AGENTS: a checkpoint failure never raises).
   - `CodingTaskResult` gains `lint_autofix: LintAutofix | None`, recording files and rule counts.

3. **Scoped check (FR-010), inside `run_test_suite`.** `QAInput` gains `lint_base: str | None = None` (the task's `branch_point`), `lint_key: str = ""` and `lint_report_only: list[str] = []`. When `lint_base` is set:
   - **The tests run first, exactly as today.**
   - Then the base is materialized as a **sibling of the task worktree** under `_worktrees_root()` at `<run>/base-<task_id>`, never in `/tmp`, because ruff walks parent directories for config. This reuses `prepare_base_worktree`'s body, lifted into a helper that takes a destination (`S/vcs/integration.py:232`). The base is removed in a `finally`.
   - Then `scoped_lint(...)` is called verbatim, with renames from `git diff -M --name-status` as `get_task_diff` computes them (`S/vcs/git.py:111`).
   - `QAReport.lint: ScopedLintReport | None = None`.
   - Findings in `lint_report_only` paths (fenced, on repair attempts) are reported but excluded from the failing set (advisor D4).

4. **Verdict and feedback (workflow-side, pure).**
   - `task_passed = … and _lint_ok(qa_raw)`, where `_lint_ok` is `lint is None or lint.state is not MEASURED or not failing_introduced(lint)`. `None` means "not run, so pass", which keeps old histories replay-identical. **NOT_COLLECTED never fails a task**; merge stays the fail-closed gate of record.
   - `_fix_loop_issues` (`S/stages/qa/step.py:87-108`) adds "lint findings introduced by this task (the merge gate's own check): `RULE path: line`", capped at 25 entries, the `failing_tests` pattern. Its signature and both call sites are unchanged.

5. **Lint is kept out of the LLM validators' view** (advisor D4). `qa_step`'s prompt dump and review and adversary's `_get_qa_raw_json` exclude `lint`. Otherwise QA and review restate lint as issues or findings, double-counting one deterministic signal and blurring the qa slice's "subprocess is ground truth" invariant.

**Replay.** No new activity, timer, signal or child. Defaulted fields only. The `lint is None` branch is identical to today. The demo fake `run_test_suite` (`S/demo/fakes.py:178`) returns no lint, so capture goldens should not move. Proof: `T/replay`, `-m temporal -k "replay or golden"`, and `scripts/check_golden_rebaseline.py`. **Unverified:** whether a golden serializes activity inputs; T016 settles it, and STOPs if more than defaulted keys move.

**Containment.** `containment_enabled` defaults off (`S/core/models.py:456`), and no case sets it (**unverified** against a fleet config dump, so it is a T040 pre-flight item). The fence logic is correct either way.

**Crew path.** Out of scope; benchmark cells are single-agent opencode.

**Lines.** `S/stages/code/step.py` is at 977. The edits are the `QAInput(...)` fields, the `_lint_ok` conjunct and the failure kwarg. The `_lint_ok` helper and `failing_introduced` live in `S/stages/code/attempt_failure.py` (new) to save lines. The net budget is ≤ +10. Overflow means the record block moves to `S/stages/code/attempt_record.py` (move only).

## R5. Task-attempt failure reason (FR-021; advisor D5 adopted)

- A pure helper `attempt_failure(qa_raw, qa, drift, review_ok, review) -> AttemptFailure | None` in `S/stages/code/attempt_failure.py`.
- `checks` is an ordered subset of `["tests", "qa", "drift", "review", "lint", "no_feedback"]`.
- `summary` is `_fix_loop_issues(qa, qa_raw, review)` plus the drift note, truncated to 500 chars: what the dev was told.
- It is called unconditionally, before the `code` record (`S/stages/code/step.py:759`). The loop's own `issues` is `""` on the last attempt, so it cannot be reused.
- The **code record** gets the full set. The **QA record** gets `tests` and `qa` only. The **review record** (`S/stages/review/step.py:151-167`) gets `["review"]` with a findings summary.
- The value goes in a new defaulted `BenchmarkRecord.failure`, **not** in `error`, which means a measurement or child failure (`S/benchmarks/models.py:88-93`).
- **SC-3 rows:** a loop is **lint-only** when every failed code attempt's `checks == ["lint"]`. `SC-3-non-lint` (comparable to 025) and `SC-3-lint` are reported beside SC-3.

## R6. Run 1's architecture crash (FR-022; advisor D6 adopted, narrower than the planner's draft)

The mechanism, verified by the advisor in the installed libraries:

1. Model code raising inside the Monty sandbox becomes `ModelRetry` (`pydantic_ai_harness/code_mode/_toolset.py:1395-1404`, v0.61.0).
2. `run_code` allows 3 retries (`code_mode/_capability.py:108`). After that, pydantic-ai raises `UnexpectedModelBehavior` (`pydantic_ai/tool_manager.py:520-526`).
3. CodeMode is on the **research** agent, which the architect reaches through its `research` tool, `research_subquery_reported`.
4. That function catches only `BudgetExceeded` and `UsageLimitExceeded`; everything else "propagates (residual R1)" (`S/stages/research/toolset.py:61-76,110-130`). The architect activity retries 3 times (`S/agents/roles.py:41-44`), then the stage and child fail.

The documented contract for exceeding a bound is "degrade to a gap brief, never crash" (`toolset.py:71-76`), and running out of tool retries is a bound being exceeded.

**Decision.** Add `except UnexpectedModelBehavior` beside `UsageLimitExceeded`, returning `_gap_brief` with OUR text ("research tool exhausted its code-execution retries"), never `str(exc)` (AM2/R9), with usage still reported. **Only that type.** Provider and other infra exceptions keep propagating (residual R1 stays for them). This replaces the planner's draft of catching bare `Exception`. It is still surfaced at GATE 2, because it narrows a documented residual.

**Test.** A `FunctionModel` emits `run_code` calls whose code raises `TypeError` 4 times. If Monty is unavailable in the fast tier (**unverified**), use a stub raising `UnexpectedModelBehavior`. Also check that the research stage's own sub-question loop already degrades on a failed sub-run before claiming both callers are covered. The triage row is classified on the evidence that exists.

## R7. The `.env` rider (FR-030; advisor D7 adopted)

- `load_dotenv()` uses `override=False`, and with no path it walks up from the **calling file**, not the CWD (`dotenv/main.py:356-372,383-387`). So a child CLI finds the repo-root `.env` regardless of its CWD, and unsetting variables lets `.env` refill them.
- python-dotenv 1.2.2 honors `PYTHON_DOTENV_DISABLED` in `load_dotenv` (`dotenv/main.py:22-29,412`).

**Decision.** At **import** in `T/conftest.py`, set `os.environ["PYTHON_DOTENV_DISABLED"] = "1"`. This also covers the import-time `load_dotenv()` in `S/worker.py:21`.

**Follow-ups.**

1. `T/test_prompt_gate_mutations.py:54-56` uses `load_dotenv(override=True)` for an opt-in paid test. Switch it to `os.environ.update(dotenv_values())`, because `dotenv_values` ignores the flag.
2. A `child_env(**overrides)` helper in conftest, starting from `os.environ`, used at the from-scratch `env=` sites that spawn the `sdlc` CLI (**unverified** which of about 12 do; convert only those).

## R8. HARD in benchmark mode (B.4; planner and skeptic 3)

- `--gate-policy hard` sets every configured gate and the dynamic default to HARD (`S/benchmarks/workflow.py:157-164`), which also overwrites merge's `on_timeout=HOLD` with REJECT.
- A HARD gate waits `gate_timeout_hours` = 48 (`S/core/models.py:92,431`), then decides `timeout` with `on_timeout` (REJECT by default).
- Under HARD, a clean merge consults no MergeVerdict and opens no merge gate (`S/stages/merge/step.py:582-583`). HARD merge is the production default (`S/core/models.py:383-390`).
- Clarification waits are `ask_and_wait`, not gates (`S/stages/clarify/step.py:293-318`).

**Pre-registered:** a planned gate decided by `timeout` means the attendant was absent, which is **infra**. The attendant services gates and clarification waits. The smoke runs `--gate-policy hard` too.

## R9. Budget (B.5)

Measured judged $ per full 025 run: readtime $1.1531, lice $0.9326, geotext $1.2700, cat-cafe $2.0025, smoke $1.9381. Per-attempt QA and review cost $0.0005–$0.0118 (skeptic 5), so longer loops add little. HARD and per-task lint add no model calls. The judge line is 1.5 × $9.30 = **$13.95**, plus research $1.00. The cost is polled every 60 seconds; run 6 is affordable only if headroom is at least $1.73.
