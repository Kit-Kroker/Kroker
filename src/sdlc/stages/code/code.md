# Code Stage

The code stage (Stage 4 / spec A §3.3 / spec A §5) executes coding tasks inside an isolated git worktree, either using a coding harness (`run_coding_task`) or multi-agent crew (`CrewTaskWorkflow`). It evaluates tool escalations, runs clean-context QA and review, drives the bounded fix loop, and returns a schema-validated `TaskResult`.

The orchestrator (`TaskHost` on the workflow) delegates per-task execution to `code.step`.

## Requirements

### CODE-1.1
The code stage slice exports `step`, `prompt_digest`, and `ACTIVITIES = [run_coding_task]`. The step function accepts `ctx: StageContext` as its first argument, receives configuration, task definition, frozen validation contract, worktree path, handoff notes, and agents as keyword arguments, and never receives the workflow instance directly. [FR-801, FR-803]

### CODE-1.2
The code stage step is pure over its inputs and contains no workflow lifecycle decorators (`@workflow.defn`, `@workflow.signal`, `@workflow.query`). All signals and queries remain on the workflow orchestrator. [ADR-6, Rule 1]

### CODE-1.3
The code stage executes the coding task inside an isolated worktree against the frozen contract, coordinates deterministic test suite and clean-context review, drives the bounded fix loop, and returns a schema-validated `TaskResult` indicating `done`, `failed`, or `quarantined`. [FR-802, FR-804]

### CODE-1.4
Each attempt writes three records that partition the attempt's time and
carry only their own role's verdict: `stage="code"` spans the attempt
start to the moment the deterministic test run begins (the
tests/qa/drift combined verdict, judge `contract`); `stage="qa"` spans
the test-run boundary to the qa step's return (quality scored against
the rubric; outcome is qa's own — tests passed and no qa issues,
regardless of containment drift or the reviewer); `stage="review"`
spans from the qa boundary onward and carries the reviewer's own
verdict (no review record when the reviewer is disabled). [Finding 4,
E-36, E-37, round 012 §5]

### CODE-1.5
When the bounded fix loop attempts are exhausted without passing both tests and review, the code stage escalates to the human gate `task:{task.id}`. If the operator grants revision, it resets session context and continues; otherwise it quarantines or completes according to operator decision. [FR-105]

### CODE-1.6
Every `TaskResult` the code stage returns — from both return sites, across all three statuses — carries one `LensOutcome` per name in `GATING_LENSES`, classified once per attempt. The task success condition reads those outcomes through `primary_admits` / `backstop_admits` rather than testing a report for `None`; no presence state blocks the done path. [C8]

### CODE-1.7
When `run_coding_task`'s checkpoint commit exits non-zero, the activity logs one WARNING naming the worktree, the exit code and git's own text, and returns normally with `commit_sha` unset: a failed checkpoint commit is visible but never raises, and the C2 test-freeze anchor does not advance. A zero exit logs nothing. [006-B1]

### CODE-1.8
Before the checkpoint commit, `run_coding_task` runs the toolchain adapter's safe lint fixes over the attempt's changed `*.py` files (on a repair attempt, the containment policy's fenced paths are never touched), so the fixes ride inside the checkpoint commit. What it applied is reported on `HarnessRunResult.lint_autofix`; `None` means not run (no Python changes, no adapter, or the fix command failed), never zero fixes. Autofix is best-effort: any failure logs a WARNING and the checkpoint commits unfixed. [026 FR-011]

### CODE-1.9
Per-task lint is a conjunct of the task success condition: `task_passed` requires tests passed, no qa issues, no drift, **and** no lint finding introduced since the task's `branch_point` (QA-1.7). Findings under repair-fenced paths are reported but never fail the task, and an unmeasured lint (no report, or `NOT_COLLECTED`) never fails it. The per-task check runs the merge gate's own scoped lint, so the two cannot disagree (parity pinned in `tests/test_lint_scope.py`); merge's `lint_clean` is unchanged and remains the fail-closed gate of record (MERGE-1.10). [026 FR-010, FR-012]

### CODE-1.10
Every failed attempt says why on its records, in `BenchmarkRecord.failure` (`AttemptFailure`), never in `error`, which stays the harness's own failure text. `checks` is an ordered subset of `tests`, `qa`, `drift`, `review`, `lint`, `no_feedback`; `summary` is the text the dev was shown, cut to 500 characters. The code record carries the full set (`attempt_failure.py`), the qa record only its tests/qa checks, and the review record `["review"]` with the blocking findings (REVIEW-1.7). A passing attempt, and every pre-026 record, carries `None`. [026 FR-021]

## Failure modes

- **Tool escalation timeout / rejection**: A suspended tool call is rejected by policy or human gate; execution resumes with denied grant.
- **Fix loop exhaustion**: Repeated attempts fail contract verification; escalated to operator gate.
- **Lint introduced by the task**: the per-task scoped lint finds a new finding outside the repair fences; the attempt fails with `failure.checks` containing `lint`, and the capped findings go into the retry prompt (QA-1.4, CODE-1.9).
- **Autofix failure**: logged at WARNING; the checkpoint commits unfixed and the per-task lint judges the result (CODE-1.8).
- **Quarantine on task rejection**: Operator rejects failing task at gate; task marked as quarantined.
