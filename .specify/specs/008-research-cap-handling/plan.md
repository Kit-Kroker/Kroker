# Implementation Plan: Research Cap Handling

**Branch**: `008-research-cap-handling` (cut in the `D:\own\Kroker-007` worktree at exec) | **Date**: 2026-10-04 | **Spec**: [spec.md](spec.md)

**Status**: Plan reviewer-validated 2026-10-04 (`.workspace/tmp/reviewer-008-plan-1.md`: approve, three nits F1-F3 applied). Tasks reviewer-validated 2026-10-04 (`.workspace/tmp/reviewer-008-tasks-1.md`: approve, one nit applied). Waiting for GATE 2.

**Input**: approved spec (GATE 1, 2026-10-04: Q1 written note only; Q2 `calls` keeps its meaning; Q3 caller-owned refusal record; Q4 the non-retryable list does not change; FR-011 pre-approved, bounded) plus consult amendments A1-A8. Design inputs: advisor `.workspace/tmp/advisor-008-1.md`, skeptic `.workspace/tmp/skeptic-008-1.md`, and probes E1-E4 run in the dev container. Every adopted claim was re-checked in code or by probe (see [research.md](research.md), "Consult disposition").

## Summary

When a research sub-question hits a bound today, its model spend is recorded as zero, each refused tool charge still charges the run ceiling its siblings share, and a model that keeps retrying a refused call ends the run in an error the stage retries six times. This feature fixes the three together, activity-side only. The sub-question run accounts usage in an object the caller owns and returns it on exhaustion. `charge_scoped` checks both counters before writing either, so a refused charge writes nothing. A refused charge is noted in a record on the run's own deps object, and the handler degrades a retry exhaustion when that record is non-empty. No workflow code, no activity configuration and no wire type changes. Three source files edited, no new source module.

## Technical Context

**Language/Version**: Python 3.13 (dev container; the host venv is not a verification environment).

**Primary Dependencies**: none added or changed. Uses installed `pydantic-ai-slim` 2.51.0 (`Agent.run(usage=...)`, `RunUsage`, `UnexpectedModelBehavior`), `pydantic` (`PrivateAttr`), and `pydantic_ai_harness.CodeMode` in tests only.

**Storage**: the existing per-run budget counter files under `$SDLC_RUNS_ROOT/<run_id>/research/`. No format change.

**Testing**: pytest fast tier only (`pyproject.toml` `addopts`). One pytest invocation per command; do not add `-q`. Ruff, mypy (`src/` only), `scripts/check_file_size.py`. No `temporal`-marked test is added.

**Target Platform**: Linux container (`kroker-dev`, bound to `D:\own\Kroker-007`, venv `kroker-007-venv`).

**Project Type**: single repo, Temporal worker + workflows.

**Performance Goals**: no measurable change. An accepted charge takes two short locks instead of two in sequence; a refused charge does less I/O than today. New tests add about 3 s to the fast tier (measured: 0.6 s per CodeMode scenario, 0.03 s per request-limit scenario).

**Constraints**:
- `src/sdlc/stages/research/step.py` is NOT edited (stop-guard 1). No change to any retry policy, timeout, cap value, prompt, or to the text of any `BudgetExceeded` message (FR-012: what the model is told at a cap does not change).
- No edit to `src/sdlc/stages/research/toolset.py`, `retain.py`, `verify.py`, `models.py`, `src/sdlc/stages/architecture/`, `pyproject.toml`, `uv.lock`, or the register file.
- The user's uncommitted files are not touched: `agents/dev/agent.yaml`, `agents/devops/agent.yaml`, `src/sdlc/core/models.py`, `docs/reports/2026-09-22-neon-welcome-session-retro.md`, the two `Pipeline Canvas` HTML files. (`CLAUDE.md` and `.specify/feature.json` are also modified in the primary checkout: those are spec-kit pointer updates, not user work, and no task edits them.)
- `AGENTS.md` edits are pre-approved for exactly two Gotchas bullets in `src/sdlc/stages/research/AGENTS.md` and for docstrings that state the old behaviour. Nothing else in any `AGENTS.md`.
- File ceilings: 1000 lines. `R/stage.py` 414, `R/budget_store.py` 138, `R/deps.py` 95 today.
- Read `src/sdlc/stages/research/AGENTS.md` and the root `AGENTS.md` before editing.
- All runs in `kroker-dev`; never the host venv; never alongside a live pipeline run. Commits: `git commit -F <msgfile>`, one path per `git add`, subject and body, no attribution trailers. RC capture `> log 2>&1; echo RC=$?`. Host shell is PowerShell 5.1 (no heredocs).
- TDD: RED tests are written by the qa seat and seen failing on `c2d9b12` before the fix task starts. Reviewer gate is per task and blocking.
- Read `.workspace/tasks/` for known host hazards before any tier run.
- Base: main `c2d9b12`.

**Scale/Scope**: 3 source files edited (`deps.py`, `budget_store.py`, `stage.py`), 2 new test modules, 1 existing test module extended, 2 docs.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template (no ratified principles): no gates apply. Repo rules from `AGENTS.md` are carried as constraints above. Post-design re-check: no violation; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/008-research-cap-handling/
├── spec.md
├── plan.md          # this file
├── research.md      # R1-R7 decisions, consult disposition, residuals
├── quickstart.md    # dev-container validation runbook
├── checklists/
└── tasks.md         # /speckit-tasks
```

No `data-model.md` and no `contracts/`: the feature adds no persisted entity, no wire field and no external interface. The one new piece of state (the refusal record) is in-memory and is specified in D2.

### Source Code (repository root)

```text
src/sdlc/stages/research/deps.py          # the refusal record on ResearchDeps
src/sdlc/stages/research/budget_store.py  # charge_scoped: check both, then write both; note refusals
src/sdlc/stages/research/stage.py         # caller-owned usage; the handler's new clause; degraded text

tests/research/test_research_cap_usage.py             # NEW: H1, clean-run parity, wire pin
tests/research/test_research_cap_retry_exhaustion.py  # NEW: N4 and its boundaries
tests/research/test_research_budget_scope.py          # extended: H4

src/sdlc/stages/research/AGENTS.md        # two Gotchas bullets (pre-approved)
BENCHMARK.md                              # history-break marker
```

**Structure Decision**: no new module. Each change sits where the behaviour already lives. Tests go in `tests/research/`, two new modules so the baseline-failing tests are easy to run alone; the H4 tests extend the module that already pins `charge_scoped`.

## Design

### D1 — Usage that survives the run (FR-001, FR-002; research R1)

In `R/stage.py`:

- Split `_usage_of(result, model)` so the conversion takes a `RunUsage`: a helper `_role_usage(run_usage, model, calls)` builds the `RoleUsage`; `_usage_of` becomes a one-line caller with `calls=1`. The planner and synthesis keep calling `_usage_of` unchanged.
- In `_research_subquestion_impl`, create `run_usage = RunUsage()` before the `try` and pass `usage=run_usage` at all three `agent.run` call sites (the `_model` seam, the override branch, the default branch). The zero `RoleUsage` built before the `try` today is removed.
- On exhaustion, the returned usage is `_role_usage(run_usage, inp.model, calls=1)` when `run_usage` has any input or output token, and otherwise exactly today's `RoleUsage(role="research", model=inp.model)`.
- The success path is unchanged: it still returns `_usage_of(result, inp.model)`.

Rules that are part of the contract:

- **All three call sites.** Missing one leaves that path on the old behaviour with no test failing unless that path is exercised; the tests cover the `_model` seam and the `_agent` seam (default branch).
- **Zero stays zero.** A run refused before any request completed returns the same object shape as today (EC1), so the workflow's fold still skips it.

### D2 — The refusal record (FR-003; research R2)

In `R/deps.py`, on `ResearchDeps`:

- A private attribute holding a list of strings, default empty. Private attributes are not fields: they are absent from `model_dump`, from `model_dump_json` and from the custom serializer's output (measured, E4).
- Three small members: `note_refusal(text)` appends; `refusals` returns the list's contents; `reset_refusals()` assigns a fresh empty list.

In `R/stage.py`, `_research_subquestion_impl` calls `deps.reset_refusals()` immediately after building its deps copy. This is required, not defensive: `model_copy` shares the list with the input's deps (measured, E4 A4).

Rules:

- **In memory only.** Never written to disk, never keyed by run or sub-question in a module-level structure. A new activity attempt starts empty.
- **On the deps object only.** Not on the agent, the toolset or any module global: those are process-wide singletons shared by concurrent sub-questions.

### D3 — A refused charge writes nothing (FR-006, FR-007, EC6; research R4)

In `R/budget_store.py`:

- Factor the two bodies `charge_persisted` already has into private helpers: read a counter (missing file = empty counter) and publish a counter (the existing temp-file + `os.replace`, with the same temp-name scheme and the same cleanup on failure). `charge_persisted` is rebuilt from them with identical behaviour; its tests are the check.
- `charge_scoped`, `scope == "run"`: unchanged (one charge through `charge_persisted`).
- `charge_scoped`, any other scope:
  1. Acquire the scope lock, then the run lock.
  2. Read both counters.
  3. Check the run ceiling on a scratch copy (cost cap = `run_max_cost_usd`, count caps unbounded, as today), then the scope caps on a scratch copy. Either check raises `BudgetExceeded` with today's message.
  4. Only if both pass: publish the scope counter, then the run counter.
  5. Release both locks in a `finally`, run lock first.
- On `BudgetExceeded` from either path, call `deps.note_refusal(...)` and re-raise the same exception. The note is the exception text prefixed with which counter refused (`run ceiling` or `<scope> allowance`). The exception itself is not altered.
- Rewrite the `charge_scoped` docstring: the sentence "the run counter is charged FIRST" is no longer true.

Rules:

- **Check order run, then scope; lock order scope, then run; publish order scope, then run.** Check order keeps today's precedence and message. Lock order keeps the shared lock shortest-held and never held while waiting. Publish order makes the only possible crash leftover "scope one ahead of run": one phantom charge on that sub-question's own allowance, never on the shared ceiling.
- **No refund path.** Nothing ever subtracts from a counter.
- **A lock `TimeoutError` is not a refusal** and is not noted (EC4).
- **Unreadable counters are still never reset.**

### D4 — The handler (FR-003, FR-004, FR-005; research R3)

In `R/stage.py`, `_research_subquestion_impl`:

- The existing `except (BudgetExceeded, UsageLimitExceeded)` clause stays first, with D1's usage. Its text and log level are unchanged.
- New clause `except UnexpectedModelBehavior as exc`: if `deps.refusals` is empty, re-raise with a bare `raise`. Otherwise log at WARNING (sub-question id, first refusal, the terminal error) and return a degraded finding with D1's usage and `failed` left false.
- The cancellation clause is unchanged.
- `_degraded` takes the reason text instead of the exception. For the two existing cases the reason is `str(exc)`, so their output is byte-identical. For the new case the reason is `<first refusal>; then <terminal error>`, where the terminal error is cut at its first sentence and at 200 characters. Both `why_it_matters` and `summary` are built from the one reason.
- Update the handler comment and the function docstring where they state the old behaviour.

No change to `R/step.py`: the list at `:64` and the fold at `:138-163` already do the right thing with a finding that carries usage.

### D5 — Tests

**`tests/research/test_research_cap_usage.py`** (new, fast tier). A real `Agent` with a scripted `FunctionModel` and one trivial tool, run through `_research_subquestion_impl`.

1. Request limit exceeded after N completed requests: `failed` false, one gap, usage tokens equal the caller-visible totals and are non-zero, `calls == 1`. **Fails on `c2d9b12`** (usage is zero).
2. A tool that raises `BudgetExceeded` directly (no CodeMode) after a completed request: same assertions. **Fails on `c2d9b12`.**
3. Exhaustion before any request completes (fake agent raising immediately): usage equals today's zero object (EC1).
4. Clean run: finding and usage equal to what `_usage_of(result)` gives; `calls == 1` (FR-010).
5. Wire pin: `SubQuestionInput(...).model_dump_json()` is byte-identical with an empty and with a populated refusal record, and the deps key set is exactly today's twelve keys.
6. Record hygiene: `model_copy` of a deps with a noted refusal, then `reset_refusals()` on the copy, leaves the source untouched; two impl calls from one `SubQuestionInput` do not share a record.

**`tests/research/test_research_cap_retry_exhaustion.py`** (new, fast tier). CodeMode + scripted `FunctionModel` + a function tool that calls the real `charge_scoped`, temp `SDLC_RUNS_ROOT`, through the real handler (E1 S4's shape).

1. Model keeps retrying a refused search: returns a finding, `failed` false, usage non-zero, the gap and the summary name the refused bound and stay under the length bound, no docs URL in either. **Fails on `c2d9b12`** (the error escapes).
2. Tool fails for an unrelated reason every time, no refusal: `UnexpectedModelBehavior` propagates (FR-005).
3. Lock timeout: the tool's lock acquisition raises `TimeoutError` every time; the error propagates and the record is empty (EC4).
4. Refusal swallowed by the script, which then fails for another reason (a script that passes the sandbox's type check, unlike E3's P4): degrades, and the gap carries both the refusal and the terminal error (EC3, pinned as accepted behaviour).
5. Branch logic with a fake agent (no CodeMode): record non-empty + `UnexpectedModelBehavior` degrades; record empty re-raises; `BudgetExceeded` still takes the first clause.

**`tests/research/test_research_budget_scope.py`** (extended).

1. Scope at its cap, further charge refused: the run counter file is unchanged. **Fails on `c2d9b12`.**
2. Three concurrent charges against a scope with room for one: exactly one accepted, two `BudgetExceeded`, both counters show one. **Fails on `c2d9b12`** (run shows three).
3. The same with `scope="architect"` (spec N1).
4. A refusal is noted on the deps passed in, with the counter named; an accepted charge notes nothing; the exception message is exactly today's.
5. Crash between the two publishes (`os.replace` made to fail on its second call): the scope counter is one ahead, the run counter unchanged, no temp or lock file left behind.
6. The existing tests in the module stay as written, including `:63` (run ceiling refuses, scope unchanged) and the two `scope == "run"` tests.

**Unmodified suites that are the regression check**: all of `tests/research/` (in particular `test_research_subquestion_activity.py`, `test_research_fanout_wiring.py`, `test_research_budget_store.py`, `test_research_budget_atomic_write.py`, `test_research_durability_nested.py`), `tests/test_model_forwarding.py`, `tests/test_exa_wrapper.py`, `tests/replay/`, and `tests/durability/test_single_retry_layer.py` (temporal tier; the only other suite that runs the real `research_subquestion` activity, with a stubbed provider and no budget charging, so the new clause re-raises there). Per research R6, the replay suites check the wire and the workflow; they do not run a sub-question activity.

### D6 — Living docs (FR-009, FR-011)

- `src/sdlc/stages/research/AGENTS.md`, exactly two bullets:
  - "Budget/usage exhaustion in `stage.py`'s handler ..." (`:58-62`): rewrite to what is now true — `failed` stays false and partial work is still dropped for a gap-only brief, but the usage up to the cap is returned and priced; a retry exhaustion after a refused charge degrades the same way; any other error is retried.
  - "The run counter is charged FIRST ..." (`:99-103`): rewrite — both counters are checked before either is written, a refused charge writes nothing, a crash between the two writes can leave the scope one ahead; retries still inherit the persisted allowance.
- `BENCHMARK.md`: a second marker after the 005 one, same form: date, feature 008, what changed for research rows (a capped sub-question is now priced: more `calls`, tokens and cost; the run budget gate reads the higher total), that earlier rows under-report capped runs and are not rewritten, and that no benchmark was re-run.
- Docs describe main: both land in the feature branch, last.

## Requirement coverage

| Requirement | Where |
|---|---|
| FR-001 caller-owned usage | D1; usage tests 1, 2 |
| FR-002 usage on every exhaustion; baseline-failing test | D1, D4; usage tests 1, 2; retry test 1 |
| FR-003 degrade on retry exhaustion after a refusal | D2, D3 (note), D4; retry tests 1, 5 |
| FR-004 `failed` false, names the bound, logged; baseline-failing test | D4; retry test 1 |
| FR-005 everything else as today | D4 bare re-raise; retry tests 2, 3, 5; unmodified `test_research_subquestion_activity.py` |
| FR-006 refused charge leaves both counters unchanged, also concurrently; baseline-failing test | D3; scope tests 1, 2, 3 |
| FR-007 existing guarantees | D3 rules; scope test 6; unmodified store tests |
| FR-008 H4 before or with N4 | task order: D3 lands before D4 |
| FR-009 the break is named | D6 `BENCHMARK.md` marker; research R5 |
| FR-010 clean runs unchanged | no `step.py` edit; usage tests 4, 5; unmodified suites; research R6 |
| FR-011 notes match the code | D6; docstrings in D3, D4 |
| FR-012, FR-013 boundaries | Constraints |
| SC-001 | usage tests 1, 2; retry test 1 |
| SC-002 | the five tests marked "Fails on `c2d9b12`" |
| SC-003 | scope tests 1, 2; quickstart step 4 (E1 re-run) |
| SC-004 | retry test 1 (the handler returns, so one attempt) |
| SC-005 | retry tests 2, 3 |
| SC-006 | unmodified suites; `git status` on fixtures |
| SC-007 | D6 marker |
| EC1 | usage test 3 |
| EC2 model concludes after a refusal | no fast-tier end-to-end test by design: the counter half is scope tests 1, 2; the conclude half is quickstart step 4 (E1 S2 re-run) |
| EC3 | retry test 4 |
| EC4 | retry test 3; scope test 4 (a timeout is not noted) |
| EC5, EC7 | unchanged behaviour, named residuals; no test |
| EC6 | scope test 5 |
| EC8 | unchanged (`failed` stays false: usage test 1, retry test 1) |
| EC9 | no model change (constraint: `models.py` not edited); usage test 5 |
| EC10 | scope test 3; `toolset.py` not edited |

## Stop-guards (binding; clearance from the orchestrator only)

1. Any change seems to need an edit to `R/step.py`, to a retry policy, or to the text of a `BudgetExceeded` message: stop. The design holds that none is needed.
2. Any existing test in `tests/research/`, `tests/test_model_forwarding.py`, `tests/test_exa_wrapper.py`, `tests/replay/` or `tests/durability/test_single_retry_layer.py` fails after a change and the plan does not name it as an intended edit: stop. Do not edit the test to pass and do not re-record a fixture.
3. The tool does not see the caller's refusal record under CodeMode (retry test 1 shows an empty record): stop and report; do not fall back to message matching.
4. A CodeMode test is flaky or takes more than 5 s: stop and report the timing.
5. A baseline-failing test passes on `c2d9b12` before the fix: stop; the test does not test the defect.

## Residuals (accepted, reported at GATE 2)

From research "Residuals": a transient failure after a refusal degrades instead of retrying (EC3, accepted at GATE 1); other error classes after a refusal are still retried; an attempt that raises still loses its spend; a crash between the two counter writes leaves one phantom charge on the sub-question's own counter; no replay fixture runs a sub-question activity; the architect tool's own uncaught retry exhaustion; real-model behaviour at a refusal is unknown; the lock-steal flaw is unchanged.

## Complexity Tracking

Empty: no constitution violations.
