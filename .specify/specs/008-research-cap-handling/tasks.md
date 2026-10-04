# Tasks: Research Cap Handling

**Input**: `.specify/specs/008-research-cap-handling/` (spec.md, plan.md, research.md, quickstart.md)

**Tests**: required (spec FR-002, FR-004, FR-005, FR-006; plan D5). Every behaviour task is preceded by its RED test task. Inside a RED task, tests marked PIN pin behaviour that already exists and are expected to pass on first run; a red PIN test is a stop-guard, not a cue to edit source.

`R/` = `src/sdlc/stages/research/`.

## Standing rules for every task

- All test and lint runs happen in `kroker-dev` (bound to `D:\own\Kroker-007`, venv `kroker-007-venv`; see quickstart.md). Never the host venv. Never alongside a live pipeline run. One pytest per command; do not add `-q` (already in `addopts`). Capture with `> <log> 2>&1; echo RC=$?`.
- Read `.workspace/tasks/` for known host hazards before any tier run. `-m temporal` runs in the container only.
- Read the root `AGENTS.md` and `src/sdlc/stages/research/AGENTS.md` before T003.
- RED tasks are written by the qa seat and must be seen failing on the branch for the stated reason before the paired fix task starts. A RED task's tests are committed in the commit of the task that turns them green, so no commit on the branch is red. The reviewer gate still applies to the RED diff on its own.
- Commit: subject + body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add`. Host shell is PowerShell 5.1: no heredocs.
- Reviewer gate is per task and blocking: task N+1 does not start until the reviewer has replied approve on task N.
- Forbidden paths: `R/step.py`, `R/toolset.py`, `R/models.py`, `R/retain.py`, `R/verify.py`, `src/sdlc/stages/architecture/`, `agents/research/`, `pyproject.toml`, `uv.lock`, `docs/reports/external-ideas-2026-09.md`, `tests/replay/histories/`, `tests/replay/golden/`, earlier `.specify/specs/*`, and every `AGENTS.md` except the two bullets named in T010. No retry policy, timeout or cap value is changed. The text of every `BudgetExceeded` message stays exactly as it is. The user's uncommitted files in the primary checkout are not touched.
- Tests use scripted `FunctionModel`s and fake agents only, with `SDLC_RUNS_ROOT` pointed at a temp directory. No real model call, no network, no credentials. Token counts from `FunctionModel` are estimates: assert against the run's own `RunUsage` figures or `> 0`, never hand-picked numbers.
- Line numbers in spec.md, plan.md and research.md are as of main `c2d9b12`; re-locate by symbol, not by number.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

- **SG-1** An edit to a forbidden path, to a retry policy, or to a `BudgetExceeded` message appears necessary.
- **SG-2** Any existing test in `tests/research/`, `tests/test_model_forwarding.py`, `tests/test_exa_wrapper.py`, `tests/replay/` or `tests/durability/test_single_retry_layer.py` fails after a change. Do not edit the test to pass and do not re-record a fixture.
- **SG-3** Under CodeMode the tool does not see the caller's refusal record (T008 case 1 shows an empty record after T009). Do not fall back to message matching.
- **SG-4** A CodeMode test is flaky or takes more than 5 s.
- **SG-5** A test this file marks RED passes before its fix task, or a test marked PIN is red.

## Phase order

| Phase | Purpose | Story | Plan | Commits |
|---|---|---|---|---|
| 1 Setup + baseline | — | — | — | 1 |
| 2 Foundational: the refusal record | blocks US2 and US3 | — | D2 | 1 |
| 3 A capped sub-question reports what it spent | H1 | US1 | D1 | 1 |
| 4 A refused charge costs the run nothing | H4 | US2 | D3 | 1 |
| 5 A retry exhaustion after a refusal degrades once | N4 | US3 | D4 | 1 |
| 6 Living docs + verification | — | — | D6 | 3 |

FR-008 (H4 lands before or with N4) is met by the phase order: phase 4 precedes phase 5.

---

## Phase 1: Setup and baseline on unmodified main (no source edits)

- [x] T001 Create branch `008-research-cap-handling` from main `c2d9b12` in the `D:\own\Kroker-007` worktree, confirm `kroker-dev` sees it at `/app` and syncs (`uv sync --frozen --extra dev --extra logfire`), run `pytest` and `mypy` once each, and record the base sha, the fast-tier pass count, any pre-existing failures and the mypy error count in `.specify/specs/008-research-cap-handling/baseline.md`. Commit

**Checkpoint**: baseline.md holds base sha, pass count, mypy count.

---

## Phase 2: Foundational — the refusal record (blocks US2 and US3)

**Goal**: `ResearchDeps` can hold a list of refused charges in memory, invisible on the wire (plan D2). Nothing writes to it or reads it yet.

**Independent test**: `pytest tests/research/test_research_cap_usage.py`.

- [x] T002 RED: create `tests/research/test_research_cap_usage.py` (fast tier) with plan-D5 usage cases 5 and 6a. (5) wire pin: for a `SubQuestionInput` built like `_inp()` in `tests/research/test_research_subquestion_activity.py`, `model_dump_json()` is byte-identical before and after `inp.deps.note_refusal("x")`; `ResearchDeps(...).model_dump_json()` likewise; the serialized deps key set is exactly `budget, max_cost_usd, max_fetches, max_run_cost_usd, max_searches, memory_backend, memory_base_url, memory_bank, memory_watermark, provider, run_id, scope`; `ResearchDeps.model_validate_json(d.model_dump_json()).refusals` is empty for a `d` with a noted refusal. (6a) hygiene: a fresh deps has empty `refusals`; `note_refusal` appends in order; after `c = d.model_copy(update={"scope": "sq-9"})` and `c.reset_refusals()`, `d.refusals` still holds its entry and `c.refusals` is empty. Confirm every case fails because `note_refusal` / `refusals` / `reset_refusals` do not exist
- [x] T003 In `src/sdlc/stages/research/deps.py` add the refusal record to `ResearchDeps` per plan D2: one pydantic private attribute holding a list of strings (default empty), `note_refusal(text)`, a read-only `refusals` returning the contents, `reset_refusals()` assigning a fresh empty list; a short docstring saying it is in-memory only, never serialized, and owned by whoever runs the agent. Do not touch the serializer, any field, `charge`, or the `BudgetExceeded` messages. T002 goes green; run `pytest tests/research/test_research_cap_usage.py`, then `pytest tests/research`, then `pytest -m temporal tests/replay` (the `architect_research_tool` history carries `ResearchDeps` on the wire; SG-2). Commit T002 + T003 together

**Checkpoint**: the record exists and the wire is unchanged; fast tier otherwise unchanged.

---

## Phase 3: User Story 1 — a capped sub-question reports what it spent (P1)

**Goal**: a sub-question that ends in exhaustion returns the usage of every completed request (FR-001, FR-002; plan D1).

**Independent test**: `pytest tests/research/test_research_cap_usage.py`.

- [x] T004 [US1] RED: in `tests/research/test_research_cap_usage.py` add plan-D5 usage cases 1–4, each through `sdlc.stages.research.stage._research_subquestion_impl`. Build a real `pydantic_ai.Agent` (`deps_type=ResearchDeps`, `output_type=ResearchBrief`) with one trivial tool and pass it as `_agent=` together with a scripted `FunctionModel` as `_model=`. (1) RED: the model calls the tool on every turn and `max_requests` is 3 → the finding has `failed is False`, exactly one gap whose text contains `request_limit`, `usage.input_tokens > 0`, `usage.output_tokens > 0`, `usage.calls == 1`; fails today because usage is zero. (2) RED: the tool raises `BudgetExceeded("search budget exhausted (1 searches)")` on its second call (no CodeMode) → same assertions with the gap containing `search budget exhausted`; fails today because usage is zero. (3) PIN: a fake agent whose `run` raises `BudgetExceeded` immediately → `usage == RoleUsage(role="research", model=inp.model)` (EC1). (4) PIN: a model that answers at once with a valid brief → `failed is False`, the brief is returned, `usage.calls == 1`, and the token fields equal those of a second identical run made directly with `agent.run(..., usage=RunUsage())` (FR-010). Confirm 1 and 2 fail for the stated reason and 3 and 4 pass
- [x] T005 [US1] In `src/sdlc/stages/research/stage.py` implement plan D1: add `_role_usage(run_usage, model, calls)` and make `_usage_of(result, model)` a one-line caller of it (planner and synthesis untouched); in `_research_subquestion_impl` create one `RunUsage()` before the `try` and pass `usage=` at **all three** `agent.run` call sites (the `_model` seam, the override branch, the default branch); remove the zero `RoleUsage` built before the `try`; in the existing `except (BudgetExceeded, UsageLimitExceeded)` clause return `_role_usage(run_usage, inp.model, calls=1)` when the run reported any input or output token and otherwise `RoleUsage(role="research", model=inp.model)`; leave the success path returning `_usage_of(result, inp.model)`. Update the comment in that clause only where it states the old behaviour. T004 goes green. Then run, as separate commands: `pytest tests/research/test_research_cap_usage.py`; `pytest tests/research`; `pytest tests/test_model_forwarding.py`; `pytest -m temporal tests/durability/test_single_retry_layer.py` (SG-2). Commit T004 + T005 together

**Checkpoint**: US1 acceptance scenarios 1, 2 and 4 hold. Scenario 3 (the stage prices the usage) needs no code: `R/step.py` already folds any finding that carries tokens.

---

## Phase 4: User Story 2 — a refused charge costs the run nothing (P2)

**Goal**: a charge refused by either counter leaves both unchanged, also under concurrency, and is noted on the deps (FR-006, FR-007; plan D3). Lands before phase 5 (FR-008).

**Independent test**: `pytest tests/research/test_research_budget_scope.py`.

- [x] T006 [US2] RED: extend `tests/research/test_research_budget_scope.py` with plan-D5 scope cases 1–5, reusing the module's `_deps` helper and reading counters with `budget_path`. (1) RED: with `max_fetches=1`, one accepted `charge_scoped(fetch=1, scope="sq-0", run_max_cost_usd=4.0)` then a second that raises `BudgetExceeded` → the bytes of `budget-run.json` are unchanged by the refused call and it shows one fetch; fails today (run shows two). (2) RED: `asyncio.gather(..., return_exceptions=True)` of three such charges against room for one → exactly one result is None and two are `BudgetExceeded`; both counters show one fetch; fails today (run shows three). (3) RED: case 1 with `scope="architect"` (spec N1). (4) RED: after a refused charge, `deps.refusals` has one entry that contains the exception's text and names the counter (`sq-0 allowance` when the scope refused; `run ceiling` when the run ceiling refused, using a low `run_max_cost_usd`); an accepted charge leaves `refusals` empty; `str(exc)` equals today's message exactly (`fetch budget exhausted (1 fetches)` and `cost budget exhausted ($0.03)`-style); when lock acquisition is monkeypatched to raise `TimeoutError`, the `TimeoutError` propagates and `refusals` stays empty (EC4). Fails today because nothing notes a refusal. (5) RED: monkeypatch `os.replace` in `sdlc.stages.research.budget_store` to raise `OSError` on its second call within one `charge_scoped` → the scope counter shows the charge, the run counter does not exist or is unchanged, and no `*.tmp` or `*.lock` file is left in the directory; fails today (the run counter is the one written first). Leave every existing test in the module as written. Confirm 1–5 fail for the stated reasons and the existing tests pass
- [x] T007 [US2] In `src/sdlc/stages/research/budget_store.py` implement plan D3: factor `charge_persisted`'s read (missing file = empty `Budget`) and its publish (the existing PID-and-counter temp name, `write_text`, `os.replace`, unlink-on-failure) into two private helpers and rebuild `charge_persisted` from them with identical behaviour; leave the `scope == "run"` branch of `charge_scoped` calling `charge_persisted` once; for any other scope acquire the **scope lock, then the run lock**, read both counters, run `charge` on a scratch copy for the **run ceiling first** (cost cap `run_max_cost_usd`, count caps unbounded as today) and then on a scratch copy for the scope, and only if both pass publish the **scope counter, then the run counter**; release both locks in `finally`, run lock first; on `BudgetExceeded` from either branch call `deps.note_refusal(f"<which counter>: {exc}")` with `run ceiling` or `<scope> allowance` and re-raise the same exception unaltered; never subtract from a counter; never reset an unreadable counter. Rewrite the `charge_scoped` docstring so it describes the new order and the one possible crash leftover (scope one ahead of run). T006 goes green. Then run, as separate commands: `pytest tests/research/test_research_budget_scope.py`; `pytest tests/research`; `pytest tests/test_exa_wrapper.py` (SG-2: `test_research_budget_store.py`, `test_research_budget_atomic_write.py` and `test_research_durability_nested.py` must pass unmodified). Commit T006 + T007 together

**Checkpoint**: US2 acceptance scenarios 1–3 hold; scenario 4 (the E1 scenarios) is checked in T012.

---

## Phase 5: User Story 3 — a retry exhaustion after a refusal degrades once (P3)

**Goal**: a run that ends in `UnexpectedModelBehavior` after a refused charge returns one degraded finding with its usage; the same error with no refusal propagates as today (FR-003, FR-004, FR-005; plan D4).

**Independent test**: `pytest tests/research/test_research_cap_retry_exhaustion.py`.

- [x] T008 [US3] RED: create `tests/research/test_research_cap_retry_exhaustion.py` (fast tier) with plan-D5 retry cases 1–5, and add usage case 6b to `tests/research/test_research_cap_usage.py`. Harness, following `.workspace/tmp/research-budget-enforcement-e1.py` (`via_stage`): an `Agent(FunctionModel(...), deps_type=ResearchDeps, capabilities=[CodeMode()])` with a `web_search` function tool that calls the real `charge_scoped(ctx.deps, search=1, scope=ctx.deps.scope, run_max_cost_usd=ctx.deps.max_run_cost_usd)`; deps with `max_searches=1`; the model always emits a `run_code` call; run through `_research_subquestion_impl(inp, _model=model, _agent=agent)`; autouse temp `SDLC_RUNS_ROOT`. (1) RED: script `r1 = await web_search(query="a")` then `r2 = await web_search(query="b")` → returns a finding (no raise), `failed is False`, `usage.input_tokens > 0`, `usage.calls == 1`, one gap; `why_it_matters` and `summary` both contain `search budget exhausted` and `sq-0 allowance`, neither contains `http`, and the part after `; then ` is at most 200 characters; the `run` counter shows one search. Fails today because `UnexpectedModelBehavior` escapes. (2) PIN: the tool raises `RuntimeError("network down")` on every call, nothing is charged → `UnexpectedModelBehavior` is raised (FR-005). (3) PIN: lock acquisition monkeypatched to raise `TimeoutError` on every call → `UnexpectedModelBehavior` is raised (EC4). (4) RED: a script that catches the refusal and then fails for another reason, written so it passes the sandbox's type check (for example `try:` two searches `except Exception: pass`, then `raise ValueError("after")`; E3's P4 was rejected before any tool ran, so first confirm with one assertion that the tool body ran) → degrades, and the gap contains both `search budget exhausted` and the terminal error's first sentence (EC3, spec A2: accepted behaviour, pinned). (5) with fake agents and no CodeMode: (5a) RED: `run` calls `kw["deps"].note_refusal("sq-0 allowance: search budget exhausted (1 searches)")` then raises `UnexpectedModelBehavior("Tool 'run_code' exceeded max retries count of 3. Consider ... https://example.invalid/docs")` → degraded finding whose gap ends with `Tool 'run_code' exceeded max retries count of 3` and has no URL; (5b) PIN: `run` raises `UnexpectedModelBehavior` with no note → raises; (5c) PIN: `run` notes a refusal and raises `BudgetExceeded("x")` → the gap text is exactly today's `research stopped early: x`. (6b, in the usage module) RED: call the impl twice with the **same** `SubQuestionInput`, first with the 5a fake, then with a 5b fake → the first call returns a degraded finding and the second call raises (the first call's refusal did not leak into it); fails before T009 because the first call raises, and after T009 it passes only if the reset is in place (`model_copy` shares the list, E4 A4). Confirm 1, 4, 5a and 6b fail for the stated reasons and 2, 3, 5b and 5c pass
- [x] T009 [US3] In `src/sdlc/stages/research/stage.py` implement plan D4: call `deps.reset_refusals()` immediately after the `inp.deps.model_copy(...)` that builds the run's deps; change `_degraded` to take the reason text and build both `why_it_matters` (`research stopped early: <reason>`) and `summary` (`Research stopped early: <reason>`) from it, with the existing call site passing `str(exc)` so its output is byte-identical; add `except UnexpectedModelBehavior as exc:` **after** the existing exhaustion clause and before the cancellation clause: if `deps.refusals` is empty, bare `raise`; otherwise log at WARNING (sub-question id, first refusal, terminal error) and return `SubQuestionFinding(sub_question=sub, brief=_degraded(sub, reason), usage=<the D1 exhaustion usage>)` where `reason` is `<first refusal>; then <terminal error cut at its first sentence and at 200 characters>`; leave `failed` at its default. Update the function docstring and the handler comment where they state the old behaviour. Do not edit `R/step.py` (SG-1). T008 goes green. Then run, as separate commands: `pytest tests/research/test_research_cap_retry_exhaustion.py`; `pytest tests/research`; `pytest tests/test_model_forwarding.py`; `pytest -m temporal tests/durability/test_single_retry_layer.py`; `python scripts/check_file_size.py` (SG-2, SG-3, SG-4). Commit T008 + T009 together

**Checkpoint**: US3 acceptance scenarios 1–3 hold; all three defects are fixed.

---

## Phase 6: Living docs and verification

- [x] T010 [P] In `src/sdlc/stages/research/AGENTS.md` rewrite exactly two Gotchas bullets (pre-approved at GATE 1; nothing else in the file): the bullet beginning "Budget/usage exhaustion in `stage.py`'s handler" → the finding keeps `failed` False and the partial work is still dropped for a gap-only brief, but the usage up to the cap is returned and priced; a run that ends in retry exhaustion after a refused charge degrades the same way, in one attempt; any other error is retried as before, and an attempt that raises still loses its spend. The bullet beginning "The run counter is charged FIRST" → both counters are checked before either is written, so a refused charge writes nothing; the run counter still enforces cost only; a crash between the two writes can leave the scope counter one charge ahead; being disk-persisted per run+scope, activity retries still inherit the already-spent allowance. Commit
- [x] T011 [P] In `BENCHMARK.md` add a second blockquote marker directly after the 005 `COST-HISTORY BREAK MARKER` paragraph, in the same form: `RESEARCH-SPEND BREAK MARKER — <landing date> (008 research cap handling)`. State: a research sub-question that hits a bound (request limit or tool budget) now reports and prices the model spend it incurred, so research rows for capped runs show more `calls`, tokens and `cost_usd` than before, and the run budget gate reads the higher total; every record before this marker under-reports research spend for capped runs and is not rewritten; runs that hit no cap are unchanged; no benchmark was re-run. Change nothing else in the file. Commit
- [x] T012 Run quickstart.md §4, §5 and §6 as separate commands and record in `.specify/specs/008-research-cap-handling/verification.md`: each command's result; the E1 counters for S1, S2, S3 (expect `run` = 1 search, equal to `sq-0`) and S4's returned finding (expect `failed` False, non-zero usage); the pass-count delta against baseline.md; the mypy count against baseline.md; the empty forbidden-path diff; the wall time of the CodeMode test module; and the per-task commit shas. Commit

---

## Dependencies

- T001 first; T012 last.
- T002 → T003. T004 → T005. T006 → T007. T008 → T009.
- T005 needs only T001 in principle, but runs after T003 so the fast tier is checked once per step. T007 needs T003 (`note_refusal`). T009 needs T003, T005 (the exhaustion usage) and T007 (the note; FR-008).
- T010 and T011 need T009 (they describe what landed).
- `[P]`: T010 and T011 touch different files and need no gate between them.

## Requirement → task map

| Requirement | Tasks |
|---|---|
| FR-001 | T005; T004 (1, 2) |
| FR-002, SC-001 | T004 (1, 2), T005; T008 (1), T009 |
| FR-003 | T003, T007 (the note), T009; T008 (1, 5a) |
| FR-004 | T009; T008 (1, 5a) |
| FR-005, SC-005 | T009 (bare re-raise); T008 (2, 3, 5b, 5c); unmodified `test_research_subquestion_activity.py` |
| FR-006 | T007; T006 (1, 2, 3) |
| FR-007 | T007; T006 (existing tests unmodified, 5) |
| FR-008 | phase order: T007 before T009 |
| FR-009, SC-007 | T011 |
| FR-010, SC-006 | T002 (5), T004 (4); T003, T005, T009 regression runs; T012 |
| FR-011 | T010; docstrings in T007, T009 |
| FR-012, FR-013 | Standing rules; T012 (forbidden-path diff, file size) |
| SC-002 | RED cases: T004 (1, 2), T006 (1, 2), T008 (1) |
| SC-003 | T006 (1, 2); T012 (E1 re-run) |
| SC-004 | T008 (1): the handler returns, so the activity completes on its first attempt |
| Edge cases | EC1 T004 (3); EC2 T006 (1, 2) + T012 (E1 S2); EC3 T008 (4); EC4 T006 (4), T008 (3); EC5, EC7 unchanged, named residuals; EC6 T006 (5); EC8 unchanged, `failed` false in T004 (1), T008 (1); EC9 `R/models.py` forbidden, T002 (5); EC10 T006 (3), `R/toolset.py` forbidden |

## Implementation strategy

MVP is phases 1–3: after T005 the record defect (H1) is fixed for request-limit exhaustion and for a direct refusal. Phase 4 stops the leak and is shippable on its own. Phase 5 depends on both and must not land without phase 4 (FR-008). If time runs out after phase 4, the branch is shippable with N4 still open; phase 6 would then describe only what landed.

**Totals**: 12 tasks — setup 1, foundational 2, US1 2, US2 2, US3 2, docs and verification 3. Eight commits (baseline; record; H1; H4; N4; two docs; verification).
