# Idea Research: Research budget-enforcement defect cluster

- **Slug**: research-budget-enforcement
- **Created**: 2026-10-03
- **Baseline**: main `269fa29`; pydantic-ai-slim 2.51.0, temporalio 1.31.0
  (same versions in `kroker-dev`)
- **Evidence confidence (overall)**: high for the five mechanisms (read in
  code); medium for runtime consequences (nothing was executed)
- **Method**: code reading only. No test was run, no file outside this
  directory was written. Paths are relative to the repo root; `R/` abbreviates
  `src/sdlc/stages/research/`.

## Corrections after advisor consult 1

Source: `.workspace/tmp/research-budget-enforcement-advisor-1.md`. Each item
below was re-checked by me in code before being adopted; where it overrides
text further down, the text further down is marked.

- **C1 — production runs the research agent under CodeMode.**
  `agents/research/agent.yaml:3` is `provider: exa`, and
  `agents/research/agent.py:49-54` then adds `CodeMode()` plus the wrapped Exa
  toolset. Tool calls happen inside a `run_code` script. An exception from a
  nested tool is captured (`.venv/.../pydantic_ai_harness/code_mode/_toolset.py:621-622`)
  and, if the script does not catch it, becomes
  `ModelRetry("Runtime error: ...")` on `run_code` (`:1173-1217`), whose retry
  budget is 3 (`:734`, `_capability.py:99`). So on the production path a
  budget refusal is shown to the model and does NOT abort the run at the
  first refusal. The direct-raise path I described under H2 is what the unit
  tests exercise (`tests/test_exa_wrapper.py:122,148`), not production.
  [Not executed — the exact sequence under CodeMode is a hypothesis until
  experiment E1 in concept.md.]
- **C2 — new uncaught path, N4.** When `run_code` exceeds its retries,
  pydantic-ai raises `UnexpectedModelBehavior`
  (`.venv/.../pydantic_ai/tool_manager.py:299-308`). `R/stage.py:277` catches
  only `BudgetExceeded` and `UsageLimitExceeded`, and `R/step.py:64` lists only
  those two as non-retryable. That attempt fails, Temporal retries up to 6
  times against counters that are already spent, and the finding ends
  `failed=True` with default zero usage (`R/step.py:109-110`,
  `R/models.py:98`). This is a larger spend loss than H1 as written.
- **C3 — H1 has an incident in its trigger class.**
  `tests/research/test_research_degradation.py:6` and
  `tests/research/test_research_e2e.py:270-274` record benchmark run
  `bench-todo-api-greenfield-1785485669`, where research exceeded the request
  limit. That shows caps are hit in real runs; it does not show a wrong spend
  row. "No observed incident" below is corrected accordingly.
- **C4 — H1 is wider than the handler.** Spend is also lost for every
  attempt that raises (Temporal discards the result) and for the final
  `failed=True` finding. Recovering usage in the handler repairs only the
  branch where the activity returns.
- **C5 — `failed is False` on exhaustion is pinned intent.**
  `tests/research/test_research_subquestion_activity.py:63-79` asserts it
  ("budget exhaustion is a degradation, not a failure"). The defect in H1 is
  the usage, not the flag.
- **C6 — N3 corrected.** The architect's sub-run is not unlimited:
  pydantic-ai applies `UsageLimits()` with `request_limit = 50`
  (`.venv/.../pydantic_ai/usage.py:467`). It is a different limit from the
  configured `max_requests` (40), and `UsageLimitExceeded` is still uncaught
  at `R/toolset.py:57`.
- **C7 — "uncapped retry" is stale.** Agent activities are bounded at 3
  attempts (`src/sdlc/agents/roles.py:40-44`); the stage's sub-question
  activity at 6. A lock `TimeoutError` is transient, so retrying it is
  correct. Only the wording in `R/toolset.py:33-38` and `R/AGENTS.md:105-106`
  is wrong.
- **C8 — third stale docstring.** `R/stage.py:216-218` distinguishes "the
  PLAIN research_agent" from "its durable handle"; `roles.py:275` makes them
  one object.
- **C9 — reachability precondition.** `charge_scoped` is called only from the
  Exa wrapper, attached only when `provider == "exa"`. With `fake` or
  `tavily` no budget is enforced at all, so H1's budget branch, H2, H3, H4 and
  N1-N3 are reachable only on the exa configuration (which is production).
- **C10 — H3's lock is redundant in-process.** The critical section
  (`R/budget_store.py:80-89`) has no `await`, so coroutines in one worker
  cannot interleave in it; the lost-update path via lock stealing needs a
  process frozen for more than 10 s. A truncated file also costs each
  sub-question 6 attempts (~62 s of backoff) before it fails.
- **C11 — H5 is likely untested, not proven harmless.** The only end-to-end
  brief with a grounded finding (`tests/research/test_research_e2e.py:71-77`)
  has no page file, so it fails verification and returns before the retain
  loop. No test was found that runs the retain path with grounded findings in
  the sandbox. [Inferred from grep; not executed.]
- **C12 — frequency check (zero-cost).** Grep of `runs/` (89 entries) and of
  `docs/reports`, `.workspace`, `benchmarks` for cap-hit markers found none.
  Local records show no cap hit; the one known instance is C3.

## Measured results (E1, E2) and skeptic corrections

Experiments authorized by orchestrator ruling and run in `kroker-dev` with a
scripted fake model; full output in
`.workspace/tmp/research-budget-enforcement-experiments.md`. These supersede
the "not executed" hypotheses in C1, C2 and under H1.

- **M1 (E2) — spend is recoverable at the cap.** A caller-owned usage object
  held all three completed requests both when a tool raised and when the
  request limit was exceeded. (confidence: high, measured)
- **M2 (E1) — a budget refusal under CodeMode does not abort the run.** It
  reaches the model as a retry prompt ending "Fix the errors and try again."
  If the model concludes, the run completes with usage intact: the documented
  contract holds and no spend is lost. (measured)
- **M3 (E1) — N4 is real.** If the model retries instead, the run ends in
  `UnexpectedModelBehavior` after four `run_code` calls, and the real stage
  handler does not catch it. (measured through `_research_subquestion_impl`)
- **M4 (E1) — the H4 leak is not cents.** Every refused call charges the run
  counter: 4 phantom charges for 1 real search with sequential calls, 11 with
  a three-way gather, in one attempt. By arithmetic over the 6 activity
  attempts (not run): $0.25 to $0.72 drained from the shared $4.00 ceiling by
  one sub-question that did one real search.
- **Not measured**: how often a real model retries rather than concludes; the
  experiment used a plain function tool, not the Exa toolset.

Skeptic kill-case 1 (`.workspace/tmp/research-budget-enforcement-skeptic-1.md`),
each point re-checked in code:

- **S-a — upheld.** `verified_findings_to_retain` has a unit contract to drop
  unverified findings (`tests/research/test_research_grounding.py:24-50`).
  Simply removing the verifier call breaks it. The H5 fix must keep that
  contract without workflow-side I/O, which makes it more than a one-line
  change.
- **S-b — upheld in part.** Returning real usage on exhaustion makes a capped
  run schedule a `price_usage` activity it did not schedule before and raises
  `calls` and `cost_usd` (`R/step.py:140-163`), which the run budget gate
  reads. It does NOT break replay of existing histories: the change is
  activity-side, and replay takes activity results from history. It is a
  visible behaviour change for new capped runs.
- **S-c — upheld.** H1 and N4 share one handler (`R/stage.py:277`) and one
  retry list (`R/step.py:64`). On the production path the budget-exhaustion
  loss goes through N4 (M3), so fixing H1 alone repairs only request-limit
  exhaustion.
- **S-d — upheld.** Under CodeMode a lock `TimeoutError` raised in a tool is
  also turned into a retry prompt before Temporal sees it. [Inferred from the
  mechanism E1 showed for `BudgetExceeded`; not run for `TimeoutError`.]
- **S-e — noted.** With the architect on `scope="architect"`, the collapsed
  branch at `R/budget_store.py:110-113` has no production caller; it is
  exercised by tests and by the default scope only.
- **S-f — not upheld.** "89 runs, zero cap hits" over-reads C12: those are
  89 entries under `runs/`, not 89 research-enabled runs.

## Slice freshness

- The slice's last code change is `a2d54bb` (004 T033). The only later commit
  touching it is `f7bf90c`, which added the Gotchas section (docs only). 007
  did not touch it — [source: `git log -- src/sdlc/stages/research`]
  (confidence: high, cited). The Gotchas therefore describe main as it is.

## Users & Demand

- The affected "user" is the benchmark/pricing record and whoever reads it,
  plus anyone resuming a run after a crash. No ticket or run log shows any of
  the five firing in a real run — [ASSUMPTION: none was searched for beyond
  the inbox card] (confidence: low).
- The card was filed from a documentation task, not from an incident —
  [source: `.workspace/tasks/2026-10-03-research-budget-exhaustion-defects.md`]
  (confidence: high, cited).

## Findings per hypothesis

### H1 — exhaustion zeroes usage: CONFIRMED

- `R/stage.py:243` builds a zero `RoleUsage` before the run; the
  `except (BudgetExceeded, UsageLimitExceeded)` branch at `R/stage.py:277-282`
  returns that same zero object. `failed` is not set, so it stays `False`
  (`R/models.py:99`).
- `R/step.py:140-141` (`_fold_research_usage`) returns early when both token
  counts are zero, so nothing is priced or added — not even a call count.
- Consequence: every model request the sub-question made before the cap is
  absent from `research_spend`, hence from the `stage_record` rows at
  `R/step.py:354-368` and `:370-385`. With `max_requests` defaulting to 40
  (`src/sdlc/core/models.py:301`), a request-limit exhaustion drops up to 40
  requests' worth of tokens. (confidence: high, cited)
- Recoverability: `Agent.run` accepts a caller-owned `usage: RunUsage`
  (`.venv/Lib/site-packages/pydantic_ai/agent/abstract.py:425`) and threads
  that object into the run state
  (`.venv/Lib/site-packages/pydantic_ai/agent/__init__.py:1521,1627`). Whether
  it holds the full spend at the moment `UsageLimitExceeded` is raised is
  [ASSUMPTION — not executed] (confidence: medium).

### H2 — exhaustion discards partial work: CONFIRMED, and wider than stated

- The degraded brief is gap-only (`R/stage.py:195-208`); the agent's message
  history and any tool results are dropped with the exception.
- Because `failed` is `False`, `R/merge.py:41-51` (failed → gap) does not run
  and `R/step.py:256` (`all(f.failed ...)`) cannot fire. The gap still reaches
  the brief through the ordinary path (`R/merge.py:72`), so the shortfall is
  reported; what is lost is the work, not the explanation.
- [SUPERSEDED IN PART by C1: the abort-at-first-refusal below holds for
  direct tool calls only; under CodeMode the model sees the refusal and the
  abort comes later, as N4.]
- Wider than stated: the documented contract is that a hit bound "surfaces to
  the model as an ordinary error; the agent concludes with what it has"
  (`R/deps.py:31-33`; `src/sdlc/core/models.py:267-269`). The tool wrappers
  call `charge_scoped` with no `try` (`agents/research/exa_wrapper.py:29-34,
  38-43, 60-65`), so `BudgetExceeded` propagates out of `agent.run` and aborts
  the run. The model never sees the refusal and never gets to conclude. The
  first refused tool call therefore discards the entire sub-question, not just
  the tail. (confidence: high for the code path; that pydantic-ai re-raises a
  non-`ModelRetry` tool exception is from library knowledge, consistent with
  `tests/test_exa_wrapper.py:122,148` expecting the raise)
- There is no partial *structured* finding to carry: `ResearchBrief` is the
  agent's final output and does not exist until the run ends. Pages already
  fetched do survive on disk (`R/verify.py:39-63`).

### H3 — non-atomic budget write: CONFIRMED as the brief states it

- `R/budget_store.py:87` is a plain `path.write_text(...)`. `write_page`
  (`R/verify.py:56-59`) uses tmp + `os.replace` and its docstring explains why.
- A truncated file fails `Budget.model_validate_json` at `R/budget_store.py:82`
  with a pydantic `ValidationError`, which is not `BudgetExceeded`. Nothing
  rewrites the file, so every later charge on that scope fails the same way.
  For `budget-run.json` that is every tool call of every sub-question in the
  run. (confidence: high, cited)
- The inbox card's wording ("replay/retry can double-count or lose a
  decrement") is a different claim and is NOT what line 87 does: the
  read-modify-write is inside the lock (`R/budget_store.py:79-89`), and
  `tests/research/test_research_budget_store.py:76` covers concurrent
  increments. Double-counting across retries is real but comes from
  charge-before-work plus persistence (see "retries inherit" below), not from
  the write.
- One genuine lost-update path exists: a holder slower than 10 s has its lock
  stolen (`R/budget_store.py:59-61`), and its `finally` then unlinks the
  stealer's lock (`:89`), admitting a third caller. Requires a >10 s stall
  between two local file operations — (confidence: high for the code,
  likelihood low, ASSUMPTION).
- No test covers a truncated or unparsable budget file — [source: grep of
  `tests/research` for truncat/corrupt/ValidationError] (confidence: high).

### H4 — run counter not rolled back: CONFIRMED

- `R/budget_store.py:121-122`: the run charge commits to disk, then the scope
  charge may raise; there is no compensation. The docstring's promise runs one
  way only ("a sub-question is never billed for work the run ceiling refused",
  `:97-98`), and `tests/research/test_research_budget_scope.py:63` tests only
  that direction.
- [SUPERSEDED by C1/C2: under CodeMode a refused call can be re-issued (up to
  3 `run_code` failures, each script possibly making several calls) and
  activity attempts (up to 6) re-charge the run counter first. The leak is
  bounded by the $4.00 run ceiling, not by "cents". Its real size is unknown
  until E1.] The same charge-before-work gap exists for any later failure
  (provider HTTP error, cancelled sibling call, activity retry), not only a
  scope refusal.
- Size of the leak under direct tool calls: one phantom charge of $0.01 (search) or $0.02 (fetch)
  (`R/deps.py:27-28`) per exhausted scope, because the refusal aborts the run
  (H2). With defaults (4 sub-questions, 1 refine round) that is cents against a
  $4.00 ceiling. (confidence: high, cited)
- Interaction: if H2 is fixed by letting the model see the refusal, the model
  can retry refused calls, and each retry leaks again. H4 becomes material
  only after an H2 fix of that shape.

### H5 — retain re-runs the verifier in workflow context: CONFIRMED

- `R/step.py:346` calls `verified_findings_to_retain` directly in workflow
  code; `R/retain.py:19` calls `verify_brief`, which does `Path.is_file` and
  `Path.read_text` (`R/verify.py:74,80`). `pages_dir`'s own docstring says
  "Resolved activity-side only — the workflow never computes this"
  (`R/verify.py:33-34`).
- The result decides how many `ctx.retain` calls follow, and each schedules an
  activity when memory is enabled (`src/sdlc/workflows/memory_host.py:62-73`).
  A replay on a host without the page files (or with a different CWD /
  `$SDLC_RUNS_ROOT`) would schedule a different number of activities — a
  non-determinism error. (confidence: high for the code path; the failure was
  not reproduced)
- The call is redundant: `brief_digest_val` is truthy only when
  `verify_brief_activity` returned no violations for this same brief
  (`R/step.py:273-297, 333-342`), so `bad` at `R/retain.py:19` is expected to
  be empty.
- Why the sandbox does not stop it: temporalio restricts `Path.is_file` /
  `read_text` (`.venv/.../workflow_sandbox/_restrictions.py:655-690`), but
  `R/step.py:21-50` imports the module under `imports_passed_through()`.
  [ASSUMPTION: passthrough is why no restriction error fires; not executed]
  (confidence: medium).
- Only bites when the brief has grounded findings; a brief without them does
  no I/O in the loop (`R/verify.py:72`).

## Adjacent traps

- **Lock `TimeoutError` not caught** — confirmed: raised at
  `R/budget_store.py:63`, not in the handler at `R/stage.py:277`, and
  `R/toolset.py:57` catches `BudgetExceeded` only. On the stage path this is
  NOT uncapped: `RESEARCH_SQ_ACT` bounds it at 6 attempts
  (`R/step.py:59-65`). Whether the architect tool activity's retries are
  capped was not checked — [NEEDS CLARIFICATION].
- **Retries inherit the spent allowance** — confirmed by construction:
  counters are keyed by run+scope on disk (`R/budget_store.py:29-39`) and
  charged before the work (`agents/research/exa_wrapper.py:29,38,60`), so
  attempt N starts from attempt N-1's total and a re-run re-charges.
- **Stale docstrings** — confirmed: `R/deps.py:8-12` ("a Task 8 concern") and
  `R/toolset.py:21-26` ("advisory-only ... (deferred)") both describe the
  persisted counter as future work; `R/budget_store.py` implements it.

## New findings (not in the brief or the Gotchas)

- **N1 — the Gotchas' `scope == "run"` bullet misdescribes the architect
  path.** `src/sdlc/stages/architecture/step.py:159` sets
  `scope="architect"`, so the architect takes the two-charge path
  (`R/budget_store.py:114-122`) and is exposed to H4, not the collapsed
  branch. No production caller was found that uses `scope="run"`.
- **N2 — the architect ignores the configured run ceiling.**
  `architecture/step.py:149-161` does not set `max_run_cost_usd`, so the
  default 4.0 (`R/deps.py:57`) applies regardless of
  `cfg.research.max_run_cost_usd`. The stage passes the configured value
  (`R/step.py:202`, `R/stage.py:239`).
- **N3 — the architect's research sub-run has no request limit of its own and
  catches only `BudgetExceeded`.** `R/toolset.py:52-56` passes no
  `usage_limits`; a `UsageLimitExceeded` or lock `TimeoutError` there escapes
  the tool activity.

## Defect 6.2 — evidence

- Definition: `docs/reports/2026-09-27-pydantic-ai-harness-comparison.md:168-184`
  — the architect's research tool returns only the brief, so the research
  agent's model tokens on that path reach neither per-role cost nor the run
  budget gate.
- Still true on main: `R/toolset.py:52-56` returns `result.output` and drops
  `result.usage`; `agents/architect/agent.py:29-35` returns the brief only.
  (confidence: high, cited)
- Relation to the cluster: same failure class as H1 (model spend lost at an
  activity-side `agent.run` boundary) and same agent, but a different hand-back
  channel — the stage returns usage on its own activity result types
  (`R/models.py:75-100`), while the architect's tool return value is a
  `ResearchBrief` that goes back to the architect model.
- D1 kept it out of 003, the 004 follow-up and 007
  (`.specify/specs/007-bounded-proposer-prompts/spec.md:116`). No re-ruling
  was found.

## Prior Art

- 006-B4 documented all of this instead of fixing it — [source:
  `R/AGENTS.md:41-115`].
- `write_page` is the in-repo precedent for the H3 fix — [source:
  `R/verify.py:39-63`, `tests/research/test_research_page_write.py`].
- `verify_brief_activity` is the in-repo precedent for keeping verifier I/O
  out of workflow code — [source: `R/verify.py:123-136`].
- The research stage's "hand usage back from the activity" rule (E-33
  amendment) is the precedent H1 violates on one branch — [source:
  `R/stage.py:1-7`].

## Market & Context

- Cost of doing nothing: benchmark rows under-report research spend exactly in
  the runs that hit a cap, which are the expensive ones; a crash mid-write can
  disable research tools for the rest of a run until a file is deleted by hand
  — [source: findings H1, H3] (ASSUMPTION for frequency).

## Data & Constraints

- Defaults: 4 sub-questions, 5 searches / 10 fetches / $1.00 per sub-question,
  $4.00 per run, 40 requests, 1 refine round —
  [source: `src/sdlc/core/models.py:278-301`].
- Budget caps price tool calls from constants only; LLM tokens are never
  enforced against them — [source: `R/deps.py:25-28, 81-94`].
- Any change to activity inputs/outputs or to the number of scheduled
  activities is replay-visible. H5's fix removes workflow-side I/O but must
  keep the retain sequence identical for briefs that verified clean —
  [ASSUMPTION: replay fixtures cover the research stage; not checked].
- Tests for this slice: `pytest tests/research/ -q`, container only.

## Evidence Against the Idea

- No observed wrong record. Every finding comes from reading code; the one
  recorded incident (C3) shows a cap being hit, not a bad spend row, and
  local run records show no cap hit (C12).
- H4's leak size is unknown (C1); fixed alone it may change nothing visible.
- H3 needs a crash or kill inside one small `write_text`; the window is tiny.
- H5 is not known to have broken a run (but see C11: it is likely untested
  rather than proven safe); it needs a replay on a host
  missing the page files, with grounded findings and memory enabled.
- H2 has no cheap fix that actually carries work: the honest fix changes what
  the model is told at the cap, which is a behaviour change that can alter
  briefs and benchmark comparability.
- H1 is the only one that silently corrupts a record on an ordinary (if
  unlucky) run.

## Gaps & Open Questions

- Answered by the advisor from library code (read, not run): a caller-owned
  `RunUsage` is the live state object and holds every completed response's
  tokens when the run aborts; `ToolFailed` exists and costs no tool-retry
  budget, but under CodeMode any raise still spends `run_code`'s budget, so
  only a *returned* refusal avoids it; the architect tool activity is bounded
  at 3 attempts. I verified the cited lines for the retry bound, `ToolFailed`
  and the `usage` threading; the rest stands on the advisor's reading.
- [NEEDS CLARIFICATION: what actually happens to a budget refusal under
  CodeMode — does the run conclude, or end in `UnexpectedModelBehavior`, and
  how many run-counter charges result? Experiment E1.]
- [NEEDS CLARIFICATION: do replay fixtures / golden traces include a research
  stage with grounded findings?]
- [NEEDS CLARIFICATION: how often do real runs hit a research cap? No run
  data was examined.]
- [NEEDS CLARIFICATION: is dropping partial work on exhaustion a recorded
  design decision? None found beyond the contract text that says the
  opposite.]

## Sources

- Repo files as cited above, read at `269fa29`. No URL was fetched.
