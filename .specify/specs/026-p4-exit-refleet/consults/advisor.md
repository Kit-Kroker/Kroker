# Round 026 design-advisor consult

One pick per decision. Evidence is `file:line` as read this session (2026-11-18). Anything I did not confirm is marked **unverified**.

## Two findings the spec does not state yet

Both bear on D1. Plan around them.

- **`SDLC_RUNS_ROOT` drives neither evidence store.** No module under `src/sdlc/benchmarks/` reads it (repo grep).
  - Records come from `SDLC_BENCHMARKS_ROOT`, else the CWD-relative `runs/benchmarks` (`benchmarks/recorder.py:17,23-24`).
  - Summaries come from `SDLC_EXPORT_ROOT`, else `./runs/pipeline` (`benchmarks/evidence.py:30,48-53`).
  - So the documented command `SDLC_RUNS_ROOT=<dir> sdlc benchmark score --all` (`docs/operations/fleet-runs.md:150`) only works when run from a CWD whose `runs/` happens to be the fleet root, or with `SDLC_BENCHMARKS_ROOT` also exported. 025's own smoke stamp misread for exactly this reason (025 `verification.md:111`, "records-root misread — `SDLC_BENCHMARKS_ROOT` was unset").
  - SC-A1's "scored with only the runs root configured" therefore needs **both** roots derived. FR-001 as written covers only summaries.
- **Benchmark summaries are invisible to the calibration ledger.** A benchmark `run_id` contains a slash (`bench-…/<cell>`; for example, the geotext `summary.json`'s `run_id`). The exporter writes `root / run_id` (`observability/activities.py:28-35`), so the summary sits two levels deep. `calibration/store.py:112` and `evidence.load_run_summaries` (`evidence.py:65`) glob `*/summary.json`, one level deep.
  - So fleet runs never warm the ledger. That is one more reason H2's ledger stays cold.
  - This is an observation only. FR-040 freezes the calibration rule, so it goes to the backlog, not this round.
  - The scorer's own path, `_summaries_by_run_id` (`evidence.py:88`), joins on `base / run_id` and handles the nesting correctly.

## D1. FR-001: export-root resolution

**Pick: one stage-neutral resolver module, used by every writer and every reader.**

- The module (proposed name `src/sdlc/runs_paths.py`) exposes `runs_root()`, `benchmarks_root()` and `export_root()`.
- Precedence: an explicit specific variable (`SDLC_BENCHMARKS_ROOT` or `SDLC_EXPORT_ROOT`) wins. Otherwise `$SDLC_RUNS_ROOT/benchmarks` or `$SDLC_RUNS_ROOT/pipeline`. Otherwise today's CWD defaults `runs/benchmarks` and `./runs/pipeline`.
- `Evidence` gains `records_root` and `export_root` strings, plus the source that won (`explicit`, `runs_root` or `default`). The report renders them in every format (FR-001).

**Why derive in the resolver, not in the scorer or the CLI.** The drift happened because the same rule is copied inline in about eight places:

- `observability/activities.py:28`
- `artifacts/store.py:48`
- `observability/decisions.py:83`
- `calibration/store.py:110`
- `demo/run.py:100`
- `benchmarks/evidence.py:53`
- `benchmarks/recorder.py:24`
- `graph/store.py:109-110`, which derives a sibling of the export root

Another copy, in `cli.py` or in `evidence.py`, would be a ninth. The CLI already passes `root=None` straight through (`benchmarks/cli.py:151`), so it has nothing to add.

**Worker behaviour is unchanged.** The container sets neither variable (no `SDLC_*_ROOT` in the compose files; repo grep). It runs at `WORKDIR /app` (`Dockerfile:47`) with `/app/runs` bind-mounted (`docker-compose.yml:75`, `docker-compose.override.yml:8-10`). The default branch still yields `/app/runs/{benchmarks,pipeline}`, byte-for-byte as today.

**Named behaviour change.** On a host that *does* export `SDLC_RUNS_ROOT` but not `SDLC_EXPORT_ROOT`, worker exports and the calibration read both move to `$SDLC_RUNS_ROOT/pipeline`. Together they are consistent, and research's per-run files already live under `SDLC_RUNS_ROOT` (`stages/research/budget_store.py:42`). Still, state it in the plan, because an existing host could see its ledger "move".

**Keeping writer and reader from drifting again:**

1. **Parity test.** For each env combination (none, `RUNS` only, `RUNS` plus an explicit variable, explicit only), assert that the writer roots (`recorder._root`, the export path the exporter computes) equal the reader roots (`evidence`).
2. **Source guard test.** An AST or grep scan asserts that no module except the resolver reads `SDLC_EXPORT_ROOT` or `SDLC_BENCHMARKS_ROOT` from `os.environ`. The repo already pins things this way (for example `tests/test_judge_literal.py`, cited at `benchmarks/models.py:94-96`).
3. **Unverified:** whether `graph/store.py`'s sibling-of-export rule should follow `SDLC_RUNS_ROOT` too. Leave its precedence as is and route only its `SDLC_EXPORT_ROOT` read through the resolver.

**Out of scope:** the `--root` and `export_root_` parameters on `load_evidence` (`evidence.py:104-111`). They stay as test seams, and an argument still beats any environment variable.

## D2. FR-002/003: classifying a summary-less run from records alone

**Pick: the cell record is the authority. Axis records add nothing. Three classes, plus one diagnostic.**

| Records for the run | Class | SC-1 | SC-2 |
|---|---|---|---|
| Cell record, `cell.pipeline_finished == False` | **crashed** (the child workflow failed) | miss | not measured, with the class |
| No cell record, other records present | **terminated** (the parent stopped before writing its cell record) | miss | not measured, with the class |
| Cell record, `pipeline_finished == True`, no summary | **summary missing** (retro or export failed) | miss (fail-closed), flagged | not measured, flagged |
| Summary present | as today | rule D3 | as today |

**Evidence on the 025 root, read this session:**

- **Run 1** (`readtime-1794957781`) has a cell record with `pipeline_finished: false`, `last_stage: clarify` and `child_result: "ChildWorkflowError: Child Workflow execution failed"`.
- **Run 6** (`lice-1794980735`) has 44 records (stage and task_attempt only) and **no cell or axis record**.
- The cell record is written only after the child returns or raises (`benchmarks/workflow.py:372-385`, then the `012-cell-record` block), so an operator terminate on the parent leaves none.
- `CellStatus` documents itself as the stored outcome status (`benchmarks/models.py:184-200`).

**Why not the axis record.** Its "code stage did not finish" reason is written in the same block as the cell record. It is absent exactly when the cell record is, so it carries no extra signal.

**Why "summary missing" is a miss.** Under D3, SC-1 needs the gates, and gates exist only in the summary. Without them a run cannot be shown to have had zero unplanned escalations, and counting it as a hit would fail open.

**"Timed out" cannot be told apart today.** The child failure is stored as `f"{type(e).__name__}: {e}"` (`benchmarks/workflow.py:383`). For a `ChildWorkflowError` that is always "Child Workflow execution failed", because the cause (timeout or application error) is in `e.cause` and is dropped.

- **Recommended small fix:** append the cause type, for example `ChildWorkflowError(cause=TimeoutError): …`.
- It changes only the string passed into the record activity. Temporal does not compare activity inputs on replay, and the round-021 precedent states exactly that (`workflows/AGENTS.md:126-131`).
- 025's run 1 stays "crashed". The re-fleet gains a real "timed out" class.
- A **parent** timeout or cancel still lands in "terminated". Label that class "terminated (no cell record: operator stop, parent timeout, or still running)". The scorer is offline (`evidence.py:12-15`) and must not ask Temporal.

**Denominator:** the distinct `run_id`s of the non-smoke records (FR-004). A summary with no records stays under the existing commit flag (`sc_rollup.py:128-153`) and is not added to n.

## D3. FR-006: the "unplanned escalation" rule

**Pick: use a static set of planned kinds in `sc_rollup`, not config membership.**

- `PLANNED_GATES = {"research", "clarify", "architecture", "plan", "merge", "deploy", "deploy_failed"}`.
- A gate *g* is an **unplanned escalation** iff `g.gate not in PLANNED_GATES` and `g.decided_by != "policy"`.
- **SC-1 hit** means the run reached merge (`REACHED_PREFIXES`, unchanged) **and** has no unplanned escalation before the first `merge` gate entry. This keeps the shape of today's `_unattended_to_merge` loop (`sc_rollup.py:160-169`) and swaps its predicate from "any human-decided gate" to "unplanned kind, not decided by policy".

**Why not "names in `cfg.gates`".**

- The summary does not carry the config.
- More decisively, **`research` is not in the default `gates` dict** (`core/models.py:381-391`). The research gate (`stages/research/step.py:382`) resolves through `default_gate_policy` (`workflows/gates.py:225-227`), exactly like `task:<id>`.
- The benchmark override rewrites only names already present (`benchmarks/workflow.py:157-164`). So a membership rule would count every research gate as unplanned.

**Gate by gate:**

- **`task:<id>`** (`stages/code/step.py:904-908`): unplanned. This is the PRD's case.
- **`tool_approval`** (`code/step.py:635-643`, `default_policy=HARD`): unplanned. It is a containment escalation, not a stage checkpoint. It cannot fire with containment off (`core/models.py:456`), which is the fleet's setting (D4).
- **`budget`** (`workflows/role_host.py:323-334`, `default_policy=HARD`): unplanned.
  - A configured budget is a ceiling, not a checkpoint, and crossing it is an exception path.
  - The 025 fleet doc says no budget switch is used (`fleet-runs.md`, "no budget switch exists"), so this cannot fire in the re-fleet. Classify it anyway so the rule is total.
- **The merge override** (the `merge` gate opened when absolute checks fail, `merge/step.py:536-538`): this *is* the merge gate. The loop stops there, and `rejected:merge…` already counts as reached. No special case.
- **`clarify` questions** are not gates. They are `ClarificationOutcome`, not in `s.gates`, so they never enter SC-1, under today's rule or the new one. SC-2 still counts them.
- **`deploy` and `deploy_failed`** come after merge and cannot affect SC-1. They are listed only so the set is total.
- **`decided_by != "policy"`, not `== "human"`.**
  - Under HARD every gate opens for a human (`gates.py:231-244`).
  - The merge override can carry a reviewer name in `decided_by` (025 D1, hazard 1).
  - A `timeout` on a task gate still means an escalation was raised.
  - Under OFF, a task gate is approved by policy and correctly does not count.
- **Unknown gate names** (a future graph gate) default to **unplanned**, which is fail-closed. Render the set beside the rate (FR-006), so a new planned kind is a visible one-line change.
- **The note text:** "unplanned = any gate outside {research, clarify, architecture, plan, merge, deploy} not decided by policy (today: `task:<id>`, `tool_approval`, `budget`), counted before the merge gate". Keep the existing `policy_mix` line beside it (`sc_rollup.py:120`), because the rule assumes a HARD or attended fleet.

## D4. FR-010/011: per-task lint (the big one)

**Pick: put it inside the existing `run_test_suite` activity, as autofix, then scoped lint, then tests. Gate it on a new defaulted `QAInput` field that only the code-stage call site sets.**

This adds no new activity, no new command and no `workflow.patched` marker. Lift merge's lint scoping to a stage-neutral module and call it unchanged.

**Why this activity.**

- It is the one activity every attempt already runs at the right moment: after the harness checkpoint, before QA and review (`stages/code/step.py:717-722`).
- It already provisions the **same** env as merge. Both `run_test_suite` (`qa/activities.py:401-403`) and `run_integration_checks` (`merge/activities.py:134-138`) call `_ensure_python_env` on a Python adapter. So the ruff binary and its resolution are merge's by construction (FR-010, AS-3).
- `task_host.py` only delegates to `code_step` (`workflows/task_host.py:287`). `qa/step.py` has its own `run_test_suite` call (`qa/step.py:141-148`), but that is a fallback path the code stage never takes, because it always passes `qa_raw`. So the home is `code/step.py` (call site and verdict) plus `qa/activities.py` (mechanism).
- **Replay.** The command sequence is unchanged. A new defaulted input field is not compared on replay, and a new defaulted result field deserializes from old histories as its default (`workflows/AGENTS.md:126-131`, the 021 precedent; `QAReport` is pydantic, `qa/models.py:15-39`).
  - The workflow-side verdict must treat `lint is None` as "not run, so pass". That is what keeps old histories replay-identical.
  - The demo fake `run_test_suite` (`demo/fakes.py:178`) returns no lint, so capture goldens should not move.
  - **Unverified:** whether any golden projection serializes activity inputs. Run `scripts/check_golden_rebaseline.py` and the replay suite as the proof (`tests/replay/AGENTS.md` rule 3).

**Mechanism inside `run_test_suite`.** It runs only when `inp.lint_base` is set and the adapter is Python; otherwise behaviour is exactly as today.

1. **Materialize the task's base.** Use a detached checkout of `branch_point` placed as a **sibling of the task worktree** (under the same `_worktrees_root()`), never in `/tmp`. Ruff walks parent directories for config, so base and head must share ancestry for "same resolution" to hold.
   - Reuse `vcs/integration.py:232`'s materialization by lifting its body into a helper that takes a destination. Its fixed path `<run>/base` would collide with merge's base and with parallel tasks, so use `<run>/base-<task_id>`.
   - Remove it in a `finally`.
2. **Safe autofix, scoped to the task's own Python files.** The file list is `git diff --name-only --diff-filter=AMR <branch_point>...HEAD -- '*.py'`, minus the exclude globs. The command is `ruff check --fix --force-exclude --exit-zero --no-cache -- <files>`.
   - Restricting to the task's files keeps the diff's file set unchanged. Otherwise `compute_plan_drift` (`code/step.py:757`) would see new files, and parallel tasks would collide on shared files.
   - `--force-exclude` keeps config `exclude` honoured when paths are passed explicitly.
   - Safe fixes only; no `--unsafe-fixes`.
   - Add `lint_fix_cmd(files)` to the adapter beside `lint_json_cmd` (`toolchain/adapters.py:252`), so the command lives in one place.
3. **Commit the autofix** as `sdlc lint autofix` when the tree changed. This is **required**, not optional:
   - the task diff is commit-range only (`vcs/git.py:101`, `branch_point...HEAD`), so QA, review and the integration merge never see uncommitted edits;
   - the passing attempt's autofix would otherwise be lost, and merge's `lint_clean` would see the findings again.
   - A commit failure reverts the autofix, records the reason and never raises, mirroring the checkpoint rule (`code/activities.py:198-211`, code `AGENTS.md`).
4. **Scoped lint**: call `scoped_lint(adapter, head_wt=worktree, base_wt=<base>, base_reason, base_sha=branch_point, renames, env, timeout)` **verbatim**.
   - The renames come from `git diff -M --name-status`, as `get_task_diff` already computes them (`vcs/git.py:111`).
   - Its `base_sha...HEAD` suppression and policy scan (`merge/scoping.py:51-73`) works because `branch_point` is an ancestor.
5. **Run the tests**, exactly as today. Autofix, then lint, then test holds by construction, so an autofix that changes behaviour shows up as a test failure in the same attempt (spec, Edge cases).

**Reusing merge's scoping instead of duplicating it.**

- Move `_lint_nc`, `_lint_point`, `_policy_and_suppressions`, `_lint_key` and `scoped_lint` (`merge/scoping.py:26-129`), together with `LintFinding` and `ScopedLintReport` (`merge/models.py`), into a stage-neutral module such as `src/sdlc/toolchain/lint_scope.py`.
- `merge/scoping.py` and `merge/models.py` re-export them, so `merge/activities.py:27` and `merge/step.py:257` are untouched (FR-012).
- The move is needed because the QA slice may not import another stage (`stages/qa/AGENTS.md`, "does not import other stages"), and `merge/scoping.py` already imports *from* `qa/activities` (`merge/scoping.py:19`), so the reverse import would be a cycle.
- The lint half needs nothing from QA. Only `scoped_tests` uses `_diagnostic_slice` and `_stopped_early`.
- Class moves do not change the JSON wire format.

**Workflow-side changes, all pure.**

- **`QAInput`** (`qa/activities.py:45-48`) gains `lint_base: str | None = None` and `autofix_exclude: list[str] = field(default_factory=list)`. Only `code/step.py:720` sets them.
- **`QAReport`** gains `lint: ScopedLintReport | None = None` and `lint_autofix: LintAutofix | None = None`, where `LintAutofix` holds the files, the rule counts and the commit sha.
- **Verdict** (`code/step.py:756`): `task_passed = … and not drift.found and _lint_ok(qa_raw)`, where `_lint_ok` is `lint is None or lint.state is not MEASURED or not lint.introduced`.
  - **NOT_COLLECTED does not fail the task.** It is recorded and visible. Merge stays the fail-closed gate of record (`merge/step.py:257-266`).
  - Failing tasks on a harness-side lint outage would turn infra faults into fix loops and SC-1 misses, and that would be a trust-layer change FR-040 forbids.
- **Feedback.** Extend `_fix_loop_issues`' deterministic block (`qa/step.py:87-108`) with "lint findings introduced by this task (the merge gate's own check): `RULE path: line`", capped at 25 entries, the same pattern as `failing_tests`. It reads `qa_raw`, so its signature and both call sites (`code/step.py:875,897`) are unchanged, and the task-gate analysis inherits the text.
- **Keep lint out of the LLM validators' view.** `qa_step` dumps the whole `qa_raw` into the QA prompt (`qa/step.py:177-182`), and review and adversary do the same through `_get_qa_raw_json` (`review/step.py:75-80,133,207`).
  - Exclude `lint` and `lint_autofix` there. Otherwise QA and the reviewer restate lint as `qa.issues` or blocking findings.
  - That would double-count one deterministic signal and blur the QA slice's "subprocess is ground truth" invariant (`stages/qa/AGENTS.md`).
- **Recording (FR-011).** The `code` attempt record gets the autofix summary and the residual introduced keys. Ride D5's new field (`failure.checks` includes `lint`), plus a small `lint` bag (autofixed count, residual count, collection state). That is additive and defaulted.

**The containment interaction.** It only matters when `containment_enabled`. That defaults to off (`core/models.py:456`), and no benchmark case or config sets it (repo grep). **Unverified** against an actual fleet config dump, so add it to pre-flight beside `adversarial_review_enabled`.

- **Repair attempts:** pass the fence and report globs already loaded at `code/step.py:684-688` as `autofix_exclude`, so an autofix never rewrites a frozen test. Report lint findings in fenced paths but do not fail on them, because a frozen session cannot fix them.
- **Attempt 1 (freely writable):** advance the anchor to the autofix commit with `_next_anchor(anchor, qa_raw.lint_autofix.commit_sha or run.commit_sha, …)` after the activity. That is a pure state update (`code/step.py:678-680`, `stages/code/freeze.py`), so attempt 2's drift check does not read the autofix as tampering. Old histories carry `None` and keep today's anchor.

**Loop pressure.** Lint residue now triggers fix loops. The budget is still `max_fix_attempts + 1` (`code/step.py:529`), and exhaustion still raises `task:<id>`, an unplanned escalation under D3. That is the accepted risk named in the spec's edge cases.

**Measured context:** autofix alone leaves 4, 15 and 42 of 22, 24 and 73 findings (spec H3). Per-task feedback is what converts the residual. Autofix is not.

## D5. FR-021: where the failure reason is available at record time

**Pick: compute it once in `code/step.py`, right before the `code` record, through a pure helper. Write it to a new defaulted `BenchmarkRecord.failure` field, not to `error`.**

**Everything is already in scope at `code/step.py:759`:**

- `qa_raw`: `tests_passed`, `failing_tests`, `issues`, `stopped_early` (`code/step.py:718`)
- `qa`, the LLM verdict (`code/step.py:727-736`)
- `drift` (`code/step.py:682-711`)
- `review`, because the primary review runs **before** the code record (`code/step.py:739-751`)
- `qa_raw.lint`, from D4

The adversary runs only on the pass path (`code/step.py:833`), so it never needs a failure reason.

**The helper.** `attempt_failure(qa_raw, qa, drift, review_ok, review) -> AttemptFailure | None`.

- `checks` is an ordered subset of `["tests", "qa", "drift", "review", "lint", "no_feedback"]`.
- `summary` is `_fix_loop_issues(qa, qa_raw, review)` plus the drift note, truncated to 500 characters. That is the same text the dev was told, so triage reads what the agent saw.
- Call it unconditionally. The loop's own `issues` is `""` on the last attempt (`code/step.py:875`), so it cannot be reused for this.

**Which records get it:**

- **`code` record:** the full set. This is the record SC-3's loops key on (`sc_rollup.py`, `fix_attempts > 0` on `code` records).
- **`qa` record** (`code/step.py:786-806`): `tests` and `qa` only, matching its own verdict.
- **`review` record** (`review/step.py:151-167`): `review.blocking_findings` is in hand there. Use `checks=["review"]` and a summary built from the findings (the `review/step.py:244` format).

**Why not `error`.** `error` already means "the measurement or child failed": judge errors (`benchmarks/models.py:88-93`) and child failure text on cell records (`benchmarks/cell.py:148`). Mixing in task verdicts would make every failed attempt read as an infra error to any `error`-keyed reader.

**Replay.** The new field rides the record-activity input only, and it is defaulted, so legacy records load unchanged. That is FR-021's rule, as well as Temporal's.

## D6. FR-022: run 1's `run_code` TypeError

**Pick: fix it test-first. Exhausting CodeMode's `run_code` retries is a bound being exceeded, and the documented contract for exceeding a bound is "degrade to a gap brief, never crash".**

**What happens, verified in the installed libraries:**

1. Model code that raises inside the Monty sandbox becomes `MontyRuntimeError`, and CodeMode re-raises it as `ModelRetry("Runtime error: …")` (`pydantic_ai_harness/code_mode/_toolset.py:1395-1404`, v0.61.0). So the TypeError **does** go back to the model as a retry prompt. That part is correct.
2. `run_code` allows `max_retries = 3` (`code_mode/_capability.py:108`). On the next failure pydantic-ai raises `UnexpectedModelBehavior("Tool 'run_code' exceeded max retries count of 3…")` (`pydantic_ai/tool_manager.py:520-526`).
3. CodeMode is on the **research** agent (`agents/research/agent.py:51-53`), not the architect (`agents/architect/agent.py:17-25`, loader capabilities only). The architect reaches it through its `research` tool, which calls `research_subquery_reported` (`agents/architect/agent.py:30-35`).
4. `research_subquery_reported` catches only `BudgetExceeded` and `UsageLimitExceeded`. Everything else "propagates (residual R1)" (`stages/research/toolset.py:110-130`, docstring `:61-76`).
   - So `UnexpectedModelBehavior` escapes the architect's tool-call activity.
   - That activity is retried up to `AGENT_ACTIVITY_MAX_ATTEMPTS = 3` (`agents/roles.py:41-44`), each time a fresh inner run that can fail the same way.
   - Then the architect run fails, and the stage and child fail with it. That matches 025 preflight's "retried 3×, failed the child at architecture" (`025 preflight.md:402-408`).

**Is this the documented contract?** No.

- The same docstring states the contract it chose: "exceeding a bound degrades to a brief with the shortfall recorded in `gaps`, never a crash" (`toolset.py:71-76`).
- "Residual R1" names other exceptions as a *known residual*. It does not say they are intended.
- A tool-retry budget running out on model-written code is the same kind of event as the request limit, which already degrades.

**The fix.** Add `except UnexpectedModelBehavior` beside `UsageLimitExceeded`, returning `_gap_brief` with **our own** text, for example "research tool exhausted its code-execution retries (3)". Never `str(exc)`, which carries the library's documentation URL (the `toolset.py:72-74` AM2/R9 rule). Usage reporting continues as for the other degrades.

**Scope it narrowly.** Catch `UnexpectedModelBehavior` only. Do not catch bare `Exception`: provider errors and other genuine infra failures must still surface through Temporal (residual R1 stays for them).

**Test.** Drive `research_subquery_reported` directly, outside durable execution, with a `FunctionModel` that emits `run_code` calls whose code raises `TypeError` four times. Assert a gap brief, no raise, and a usage report.

- **Unverified:** that Monty runs in the fast-tier environment. `deps.py:15-18` records CodeMode as "untestable via TestModel under durable execution", but this path is not durable.
- If Monty cannot run there, fall back to a stub agent that raises `UnexpectedModelBehavior`. That still proves the catch, though not the CodeMode mapping.

**Also unverified:** whether run 1 died through the architect's tool path or through the top-level research stage, which also runs CodeMode. 025's history is gone. Classify the triage row on the evidence that exists ("architect agent's `run_code`", preflight), and check that the research stage's own sub-question loop already degrades on a failed sub-run before claiming both callers are covered.

## D7. FR-030: `.env` scrub

**Pick: one line at suite level in `tests/conftest.py`, at import: `os.environ["PYTHON_DOTENV_DISABLED"] = "1"`. No per-test edits and no scrub list.**

**Why scrubbing alone does not work.**

- `load_dotenv()` defaults to `override=False` (`dotenv/main.py:383-387`, python-dotenv 1.2.2), so it fills only *unset* variables.
- `sdlc.cli.main()` calls it with no path (`src/sdlc/cli.py:493`), and with no path `find_dotenv` walks up from the **calling file's** directory, not the CWD (`dotenv/main.py:356-372`). So a child CLI finds the repo-root `.env` whatever CWD the test gives it.
- Deleting `KROKER_*` from the child's env therefore just lets `.env` refill it. Only *pinning* (setting a value, even empty) or *disabling* works.
- The suite already relies on the pinning half of this (`tests/doctor/test_doctor_cli.py:119-124`, "load_dotenv never overrides a variable that is set").

**Why disabling is the right fix.**

- python-dotenv 1.2.2 honours `PYTHON_DOTENV_DISABLED` inside `load_dotenv` (`dotenv/main.py:22-29,412`).
- Children built from `os.environ` inherit it. That covers every subprocess test that passes `env=None` or `{**os.environ, …}`.
- It also stops the import-time `load_dotenv()` in `src/sdlc/worker.py:21` from polluting the pytest process itself, the race that `tests/conftest.py:34-43` documents.
- It covers `KROKER_*`, `SDLC_*` **and** any future key, with no list to maintain.
- `REAL_PRIVATE_ROOT` is captured from the shell env before any dotenv load (`conftest.py:44`), so the opt-in private-leak tests do not change.

**Two follow-ups for the plan:**

1. **`tests/test_prompt_gate_mutations.py:54-56`** deliberately calls `load_dotenv(override=True)` to pull real keys for an opt-in paid gate. The disable flag would turn that into a silent no-op. Switch it to `os.environ.update(dotenv_values())`; `dotenv_values` does not check the flag (only `load_dotenv` does, at `main.py:412`).
2. **Tests that build a child env from scratch** (about 12 `env=` sites not derived from `os.environ`, for example `tests/test_operator_mcp_parity.py:295`) would not inherit the flag. Their children would still load `.env` for any key they leave unset.
   - Add a tiny `child_env(**overrides)` helper in conftest that starts from `os.environ`, so the flag rides along, and use it at those sites.
   - **Unverified:** which of the 12 actually spawn the `sdlc` CLI. Only the six files named on the card failed, so convert only those that do.

**Ambient shell exports** (as opposed to `.env`) are a separate exposure. The card measured only `.env`. If the plan also wants shell-exported `KROKER_*` neutralised, pin them in the same conftest block with `monkeypatch`-free `os.environ.pop` at import. The flag still prevents refill. Optional; the card does not need it.

**Proof (SC-A4):** the full fast tier with the fleet `.env` present must equal the 2 baseline ids, as the card measured (8038 passed with `.env` moved aside).
