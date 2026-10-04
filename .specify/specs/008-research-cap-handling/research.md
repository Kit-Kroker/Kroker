# Research: Research Cap Handling (008)

Baseline main `c2d9b12`; `pydantic-ai-slim` 2.51.0, `temporalio` 1.31.0 (same in `kroker-dev`). `R/` = `src/sdlc/stages/research/`; `SP/` = `.venv/Lib/site-packages/`.

Evidence tiers: **measured** (probe run in `kroker-dev`), **read** (seen in code, not run), **inferred**.

Probes: E1/E2 `.workspace/tmp/research-budget-enforcement-experiments.md`; E3 `.workspace/tmp/research-cap-handling-e3.md`; E4 `.workspace/tmp/research-cap-handling-e4.md`. Scripts sit beside the result files and are not committed.

## R1 — Usage that survives an abort (FR-001, FR-002)

- **Decision**: build one `RunUsage` before the run, pass it as `usage=` at all three `agent.run` call sites in `_research_subquestion_impl`, and convert it in the exhaustion branches. On exhaustion the returned `RoleUsage` has `calls=1` when any input or output token was reported; otherwise it is today's zero object.
- **Rationale**:
  - The object passed in is the one the run uses and returns: `usage or RunUsage()` (`SP/pydantic_ai/agent/__init__.py:1521`), and `RunUsage` defines no truthiness, so an empty one is kept (read). On a clean run `result.usage` is the caller's object with equal numbers (measured, E4 D1).
  - It holds every completed request at the abort: 3 requests at a request-limit abort, 4 at a retry-exhaustion abort (measured, E2, E4 B3/C2).
  - Keeping the zero object when no token was reported leaves EC1 and every existing fake-agent test byte-identical.
- **Alternatives considered**: reading usage off the exception or the message history (no such field; the history is dropped with the exception); a custom capability that accumulates usage (more code for what a keyword already does).

## R2 — Telling a budget-caused retry exhaustion apart (FR-003, Q3 = A)

- **Decision**: a refusal record held in a pydantic private attribute on `ResearchDeps`. `charge_scoped` appends to it when a charge is refused. `_research_subquestion_impl` gives its deps copy a fresh record before the run and reads it in the handler.
- **Rationale**:
  - The exception type does not survive the sandbox, and only the last failed call's text does (measured, E3). Type inspection is ruled out.
  - A private attribute never reaches the wire, empty or populated, so `SubQuestionInput` and the architect's deps payload are byte-identical (measured, E4 A1-A3, A7, A8). The `architect_research_tool` replay fixture carries `ResearchDeps` across the wire, so this matters.
  - The tool writes to the caller's own deps object under CodeMode, including under a three-way gather (measured, E3, E4 B2).
  - It is explicit: a direct `charge_scoped` call in a test records too, and losing object identity would fail a test loudly.
  - Recording once in `charge_scoped` covers all three Exa tools. It records only on `BudgetExceeded`, so a lock `TimeoutError` is never recorded (EC4).
- **Trap, measured (E4 A4)**: `model_copy` shares the list. The impl must assign a fresh record after the copy at `R/stage.py:236`, or a refusal from one call leaks into the next call made from the same input object. In production each attempt deserializes a fresh input, so this bites tests and direct callers; it is pinned by a test anyway.
- **Alternatives considered**:
  - A context variable set by the impl. Works (measured, E3), and Temporal runs each async activity in its own task, so siblings cannot see each other's value (`SP/temporalio/worker/_activity.py:160`, read). Rejected as first choice because it is ambient: a direct call records nothing and the reader has to know a hidden global exists. It also rests on the sandbox executor never hopping threads, which was measured for the default configuration only.
  - Matching "budget exhausted" in the cause chain: ruled out at GATE 1 (Q3 option B).
  - A serialized field on `ResearchDeps`: changes the wire; breaks FR-010.
- **Leak checks** (skeptic 1): the record is on the per-activity deps copy, not on the agent or toolset singletons, so concurrent sub-questions cannot share it. It is in memory only, so a new activity attempt starts empty (E4 A7).

## R3 — The handler (FR-003, FR-004, FR-005)

- **Decision**: add one `except UnexpectedModelBehavior` clause after the existing exhaustion clause. If the record is non-empty, return a degraded finding with the caller-owned usage; otherwise re-raise unchanged. The cancellation clause stays as it is.
- **Rationale**: a returned finding completes the activity, so the retry policy is never consulted and the non-retryable list does not change (Q4 = A; skeptic 2 upheld). The error arrives bare, not inside an exception group (measured, E4 B1). Nothing else raised in the function can be budget-caused: the code before the `try` only copies models, and the code after only casts.
- **Text of the degraded finding**: one helper builds the reason and both `why_it_matters` and `summary` use it. For this case the reason is the first recorded refusal, then the terminal error cut at its first sentence and at 200 characters, which drops the library's advice and docs URL. `summary` is what the synthesis prompt embeds (`R/stage.py:355`) and `why_it_matters` is what a refine replan embeds (`R/stage.py:86`); no test or other consumer keys on the text (read; advisor D4). The two existing exhaustion cases keep their exact text.
- **Alternatives considered**: catching the error class without the record (hides unrelated model failures; Q4 option B's flaw); a new sentinel exception raised from the tool (it would not survive the sandbox either, E3).

## R4 — Keeping the two counters in step (FR-006, FR-007, EC6)

- **Decision**: for `scope != "run"`, `charge_scoped` takes the scope lock, then the run lock, reads both counters, checks the run ceiling and then the scope caps on scratch copies, and only if both pass publishes the scope counter and then the run counter with the existing atomic temp-file write. The `scope == "run"` single-counter path and `charge_persisted` are unchanged.
- **Rationale**:
  - Check-then-publish under both locks means a refused charge writes nothing, in either direction, and three concurrent charges against room for one serialize on the scope lock.
  - Checking the run ceiling first keeps today's precedence and message when both would refuse (`tests/research/test_research_budget_scope.py:63` stays as written).
  - Lock order scope then run: the shared run lock is taken last and held only for one read and one write, never while waiting for another lock. Every caller that takes both takes them in this order, and the single-counter path takes only the run lock, so no cycle is possible. (The advisor proposed run then scope. Both orders are deadlock-free; this one keeps a stale scope lock from ageing the shared lock toward the 10 s steal.)
  - Crash between the two publishes: the scope counter is one ahead of the run counter. The charge precedes the work, so no tool ran; the leftover is one phantom charge against that sub-question's own allowance, and the shared ceiling is untouched. Real work is always covered by both counters, so nothing is handed back. (The skeptic called this direction unsafe. Not upheld: nothing was done for that charge, so the run counter does not under-count real work.)
- **Alternatives considered**: charge the run and refund it when the scope refuses, or charge the scope first and refund it when the run refuses. Both add a third write with its own crash window, both hand budget back by design, and a refund races with concurrent charges unless it takes the same locks (skeptic 5).
- **Unchanged and out of scope**: the 10 s lock steal and its known flaw (a slow holder's `finally` unlinks the stealer's lock, `R/budget_store.py:105`).

## R5 — What new runs record (FR-009, Q1 = A, Q2 = A)

- **Decision**: no workflow code changes. `R/step.py` is not edited. A capped sub-question that reports tokens flows through the existing fold: one `price_usage` activity, `calls` plus one, tokens and cost added. The break is named by a second marker in `BENCHMARK.md` beside the 005 cost-history marker (`BENCHMARK.md:20-32`), and by the rewritten Gotchas in `R/AGENTS.md`.
- **Rationale**: `BENCHMARK.md`'s marker block is the established place a benchmark reader scans, and the 005 marker already speaks about research budgets. The marker carries the date and the feature number, as the 005 one does; a commit cannot contain its own hash.
- **The run budget gate**: a higher research total can make the existing budget gate fire on a capped run. `rejected:budget` is an existing outcome (`src/sdlc/workflows/feature.py:293-294`), now reachable where the spend used to be hidden. Not a new outcome (skeptic 3 upheld).

## R6 — What "clean-run replays unchanged" rests on (FR-010, SC-006)

- **Finding**: no replay or golden suite runs a sub-question activity. `research_greenfield` fakes the planner into an empty decomposition, so `research_subquestion` is never scheduled in it (`tests/replay/scenarios.py:135-146`); `architect_research_tool` records only the architect's tool activity. Both seats flagged this.
- **Decision**: FR-010 is carried by three things, stated as such: (1) no workflow code and no activity configuration changes, so the command sequence cannot change; (2) the activity's input type is byte-identical, pinned by a new wire test; (3) on a clean run the returned usage is the same object with the same numbers (measured), pinned by a new test. The unmodified replay suites are a regression check on the wire and the workflow, not evidence about the sub-question activity.

## R7 — Tests that fail on the baseline (SC-002)

- **H1**: a real `Agent` with a scripted `FunctionModel` and a trivial tool, run through `_research_subquestion_impl` with a request limit it exceeds. A raising fake agent cannot test this: it never touches the usage object. Token counts from `FunctionModel` are estimates, so tests assert against the `RunUsage` figures or `> 0`. About 0.03 s (measured).
- **N4**: CodeMode with a scripted `FunctionModel`, in-process, through the real handler. About 0.6 s per scenario (measured), no network, no service. `tests/research/test_research_spike.py` skips its CodeMode test only because `TestModel` cannot drive `run_code`; `FunctionModel` can. One end-to-end scenario per behaviour; branch logic in cheap fake-agent tests.
- **H4**: pure `charge_scoped` tests against a temp runs root.
- **Fake agents**: the three that stand in for the research agent accept extra keywords (`tests/research/test_research_subquestion_activity.py:45`, `tests/research/test_research_budget_scope.py:119`, `tests/test_model_forwarding.py:317`), so the new `usage=` keyword breaks none (read).

## Consult disposition

Advisor `.workspace/tmp/advisor-008-1.md`, skeptic `.workspace/tmp/skeptic-008-1.md`. Each adopted point was re-checked in code or by probe.

| Point | Disposition |
|---|---|
| Advisor D1: private attribute over context variable; record once in `charge_scoped`; `model_copy` shares the list | Adopted; all three measured in E4. |
| Advisor D1 extra: the record says which counter refused | Adopted for the record only. The exception message the model sees is NOT changed (FR-012). |
| Advisor D2: check both under both locks, publish scope then run | Adopted, with lock order scope then run (R4). |
| Advisor D3: zero usage stays today's object; refactor `_usage_of` | Adopted. |
| Advisor D4: `summary` reaches the synthesis model; bound it | Adopted (spec amendment A1). |
| Advisor D5: `BENCHMARK.md` marker | Adopted (A4). |
| Advisor D6: real agent for H1; wire pin; architect-scope test; crash-between-writes test | Adopted. |
| Advisor 5: `charge_scoped` docstring goes stale | Adopted; inside the FR-011 pre-approval (a docstring stating old behaviour). |
| Skeptic 1: a transient failure after a refusal degrades instead of retrying | Upheld as a case of EC3, which GATE 1 accepted. Made explicit (A2) and reported at GATE 2. |
| Skeptic 1: an error of another class after a refusal is still retried | Upheld; it is today's behaviour (FR-005). Residual. |
| Skeptic 1: record leaks between siblings or attempts | Not reachable with R2's design; pinned by tests. |
| Skeptic 2, 3, 4, 7 | Upheld; no change. |
| Skeptic 5: refund designs race | Upheld; refund designs rejected (R4). |
| Skeptic 5: scope-ahead crash residue is unsafe | Not upheld (R4). |
| Skeptic 6: replay suites do not cover the sub-question activity | Upheld (R6, A3). |
| Skeptic 8: SC-003 targets are right; S2 is optimistic about real models | Upheld; already in decide.md. |

## Residuals (reported at GATE 2)

1. After a refusal, any `UnexpectedModelBehavior` degrades, including one whose real cause was a transient failure in a later tool call. The gap names both the refusal and the terminal error. Accepted at GATE 1 as EC3.
2. After a refusal, an error of any other class is retried as today, against a cap that stays exhausted.
3. An attempt that raises still loses its spend (decide.md's known residual).
4. A crash between the two counter writes leaves one phantom charge on that sub-question's own counter.
5. No replay fixture runs a sub-question activity; FR-010 rests on R6.
6. The architect's research tool still lets a retry exhaustion escape (spec N2; D1 in force).
7. How often a real model retries a refusal rather than concluding is unknown.
8. The lock-steal flaw in `budget_store.py` is unchanged.
