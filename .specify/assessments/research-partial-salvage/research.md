# Idea Research: Salvage partial research work when a sub-question run dies

- **Slug**: research-partial-salvage
- **Created**: 2026-10-05
- **Baseline**: main `bcfbffc`; pydantic-ai 2.51.0, temporalio 1.31.0
  (`kroker-dev`, `/app` at `bcfbffc`)
- **Evidence confidence (overall)**: high for what state exists at death and
  what the code does with it (measured or read); **low for demand** — no
  local run shows a sub-question dying, and real-model behaviour on a
  wrap-up call is unmeasured
- **Evidence tiers**: *measured* (run in `kroker-dev` with a scripted
  `FunctionModel`), *read* (seen in code, not run), *hypothesis* (neither).
  `R/` = `src/sdlc/stages/research/`.
- **Experiments**: `experiments/e6_death_state.py`,
  `experiments/e6b_dangling_call.py` in this directory. Command:
  `docker exec -i kroker-dev python - < <script>`. No network, no repo
  writes; pages and budgets went to a temp `SDLC_RUNS_ROOT` in the container.

## Corrections after advisor consult 1

Source: `.workspace/tmp/research-partial-salvage-advisor-1.md` (question:
`consults/advisor-1-question.md`). Each item was re-checked by me before
being adopted; where it overrides text further down, that text is marked.

- **A1 — M7 was overstated.** A grounding violation does not discard the
  brief or stop the pipeline. `R/step.py:279-298` records a research FAIL
  row and returns the brief with `digest=""` and no rejection; both callers
  continue (`src/sdlc/workflows/feature.py:390-392`,
  `src/sdlc/workflows/graph_nodes/precode.py:98-101`). What is lost on a
  violation: the human gate (the function returns before it), retention of
  every finding, the judge score, a PASS row, and the digest clarify keys
  on. Siblings' findings stay in the returned brief, unretained, in a run
  recorded FAIL. (re-read; adopted)
- **A2 — replay remedy corrected.** "Move the decision into an activity"
  is replay-safe only if it happens *inside an activity the old history
  already ran*. A new activity call on the old failure branch is itself a
  new command. So the stage-level fix has two replay-safe forms: change
  what `synthesize_brief` returns when its model call fails (old histories
  recorded the error and replay the old branch), or keep the findings in
  workflow code behind `workflow.patched`. (adopted)
- **A3 — error string confirmed by a golden.**
  `tests/replay/golden/context_reject.json:2` shows
  `"ActivityError: Activity task failed"`, matching my constructed check.
  Applies to class C gaps (`R/merge.py:48`) and to the stage-level degraded
  brief (`R/step.py:90-102`). Fixing the string in workflow code is itself
  a workflow-side change. (adopted)
- **A4 — death classes refined.** Class A's handler also catches a direct
  `BudgetExceeded` (`R/stage.py:307`): call it A2 — a tool-side cap with no
  request-limit problem. Class B is attributed by "the refusal record is
  non-empty", not by cause (`R/stage.py:329`): a run refused once early
  that later dies of an unrelated dead end is classed B. Class C loses all
  usage as well as all work — the activity raises, so the caller-owned
  usage never reaches the finding — up to 6 attempts × 40 requests of
  spend invisible to the record. The architect's mid-run research call
  (`R/toolset.py:50-70`) has the same death shape; it is out of scope
  (D1). `non_retryable_error_types` at `R/step.py:64` is now dead for this
  activity: both names are caught before they can leave it. (re-read;
  adopted)
- **A5 — a wrap-up is "one request" only if the model concludes on it.**
  My scripted wrap-up model always called the output tool. With function
  tools still offered, a real model may call `run_code` again. E6 W1a
  proves wiring, not model behaviour. (adopted; see E7 below)
- **A6 — verifying twice has a race.** If salvaged content is verified in
  the activity and again by the stage, a sibling re-fetching the same URL
  in between can replace the page bytes and flip the result. Rare.
  (adopted as a noted risk)
- **A7 — a mechanism I had not listed**: findings recorded as the run goes
  (a tool that takes a quote and claim, verifies the quote on the spot and
  keeps it on deps). It is the only shape that creates the structured
  partial state M2 says is missing, and it changes the agent contract and
  prompt for every run. Carried into shape as an option, not researched
  further here.

### E7 — can the last request be reserved for a conclude turn? (measured)

`experiments/e7_reserve_last_request.py`. A `PrepareTools` capability that
returns no tools once `ctx.usage.requests >= limit - 1`, on the E6 agent,
through the real stage handler, limit 4.

- The hook is called before every request and sees the true running
  request count (0, 1, 2, 3, 4). (measured)
- **It does not hide `run_code`.** Under CodeMode the hook is shown the
  nested tool (`get_page`) and the model is still offered `run_code` on
  every request, in either capability order. The run still ends at the
  request limit with a gap-only brief. (measured)
- So reserving the last request is not a one-capability change on this
  agent. The library has a `before_model_request` hook
  (`pydantic_ai/capabilities/abstract.py:869`) that might be able to strip
  tools from the request; that was read, not tried. [hypothesis —
  SUPERSEDED by E7b below: tried, and it works]

### E7b — the same, with the per-request hook (measured, after skeptic 1)

`experiments/e7b_reserve_last_request_hook.py`. A capability whose
`before_model_request` strips every function tool from the request once
`ctx.usage.requests >= limit - 1`. Same agent, real stage handler, limit 4.

| Model | Tools offered per request | Result |
|---|---|---|
| concludes when no function tool is offered | `run_code`, `run_code`, `run_code`, *(none — output tool only)* | **normal completion on request 4 of 4**: 3 grounded findings, 0 gaps, `verify_brief` clean |
| calls `run_code` regardless | same | request-limit stop, gap-only — identical to today |

- **M8 — the last request the limit allows can be turned into a
  conclude-only turn, inside the limit.** A model that complies ends the
  run normally with an ordinary brief; a model that does not ends exactly
  as today. No request beyond the limit, no second run, no change to the
  activity's result shape. (measured, scripted model)
- **This costs clean runs nothing.** A tool call issued on request N of N
  can never be read back today — the next request is refused — so a run
  that survives today is one that concluded on or before request N, and
  it still does. [reasoned from `pydantic_ai/usage.py:532-534`; the
  advisor's "lowers depth by one request" does not hold]
- Not measured: whether the production model concludes with a valid brief
  when offered only the output tool; whether it needs to be told it is on
  its last turn; how the hook learns the limit (a constant in the
  experiment).
- It covers the request limit only — the one cap class with a recorded
  incident (`bench-todo-api-greenfield-1785485669`). Tool-budget stops
  already reach the model as an error it can conclude on (parent E1 S2).

## Skeptic kill-case 1 — what was upheld

Source: `.workspace/tmp/research-partial-salvage-skeptic-1.md` (brief:
`consults/skeptic-1-question.md`). The skeptic's position was kill on both
halves of draft 1. Each point re-checked by me.

- **S1 — upheld. Keeping findings without a filter is worse than today on
  one path.** Today a synthesis-failed run has nothing to verify, passes,
  and reaches the human gate (`R/step.py:270-303`). A merged brief with
  one bad quote would return at `:298` before the gate. "Same exposure as
  a clean run" is true and beside the point: it is a path that reaches the
  gate today and would not.
- **S2 — upheld. A fallback inside the synthesis activity cannot see
  timeouts or a lost worker.** Those surface only in workflow code
  (`R/step.py:269`). An in-activity fallback covers a model error and
  nothing else.
- **S3 — not upheld as stated.** "The activity cannot know its maximum
  attempts": `temporalio.activity.Info` has a `retry_policy` field in
  1.31.0 (checked in `kroker-dev`). Whether it is populated at run time
  was not checked. [hypothesis]
- **S4 — upheld. The reopening condition in draft 1 was a catch-22.**
  Production does not capture message history (`R/stage.py:270-306`), so
  "a real run with its history kept" could never occur. M1 holds only with
  capture wrapped around the call, which my experiments added from
  outside.
- **S5 — upheld. I set aside "reserve the last request" on the wrong
  hook.** E7b above is the result of trying the right one.
- **S6 — upheld. Two unrelated changes were bundled** (the stage-level
  keep and the cause string).
- **S7 — partly upheld.** The cause string flows into the brief handed to
  the verify activity, the gate and the judge. It does not change which
  commands the workflow issues, and the golden the skeptic cites
  (`tests/replay/golden/context_reject.json`) is the context stage's, not
  research's. Whether any research golden compares payloads was not
  checked. [open]
- **S8 — not upheld.** "Cheap offline checks were skipped" (reading the
  provider's serializer; a mock endpoint): neither says what the real
  endpoint accepts or what the real model does.
- **S9 — noted.** "Downstream stages never read the brief" is what this
  document already says under "Who reads the brief". It bounds the value
  of every option here: the human at the gate, the judge, and memory.
- **S10 — speculative, not adopted.** "If synthesis failed on four
  findings it will fail again on eight."

## Skeptic kill-case 2 — what was upheld

Source: `.workspace/tmp/research-partial-salvage-skeptic-2.md` (brief:
`consults/skeptic-2-question.md`). Position: kill on all three parts of
draft 2.

- **T1 — upheld. The "conclude on the last request" residual was left
  open.** A forced-turn brief with a bad quote would fail the stage where
  today's gap reaches the gate. The skeptic's own condition for moving —
  a forced turn that falls back cleanly to gap-only — is adopted as part
  of the option (concept.md, Option D, self-check).
- **T2 — upheld. "Verifies in most repetitions" was too soft.** At a 75%
  per-sub-question pass rate, four sub-questions all pass about a third
  of the time. With the self-check the live check no longer measures
  safety; its threshold is now stated as a value threshold.
- **T3 — upheld. A limit held as a constant would cut the architect's
  research short** (`R/toolset.py:50-70` passes no limit; the library
  default is 50). The capability must be inert unless the sub-question
  run gives it a limit. Already listed as a rabbit hole; now a stated
  requirement.
- **T4 — upheld. `activity.Info.retry_policy` may be `None`.** My S3
  rebuttal was too quick. Moot for the options as they now stand (neither
  needs the attempt budget).
- **T5 — open.** The skeptic says the replay fixtures compare activity
  inputs, so a changed cause string would break them. I did not check
  `tests/replay/projection.py`. It bears only on the inbox task for the
  cause string, which must say so.
- **T6 — not adopted as a defect, kept as the standing argument for
  kill.** The stage-level keep helps only when synthesis fails *and*
  every kept quote verifies; with 2 of 5 local rows failing grounding,
  that is a narrow window on an unobserved failure. This is a value
  judgment for the gate, set out in decision.md.
- **T7 — not upheld.** "The fallback leaves a contradictory audit trail"
  (a verify result with violations followed by a gate on the gap-only
  brief): the history shows what happened, in order. "`merge_briefs` adds
  substantial load to the workflow thread": it is a loop over a handful
  of findings.

## Skeptic kill-case 3 (part 2 as revised) — what was upheld

Source: `.workspace/tmp/research-partial-salvage-skeptic-3.md` (brief:
`consults/skeptic-3-question.md`). Position: **kill** on the revised
"conclude on the last request" option.

- **U1 — upheld. "Can never cause a stage grounding failure" was an
  overclaim.** The re-fetch race (A6) survives the self-check: a sibling
  can replace a page's bytes (`R/verify.py:53-59`) between the
  sub-question's check and the stage's (`R/step.py:273-278`). I had listed
  it as an accepted residual and still written "never". The same race
  exists today for every clean run, so it is not new in kind — but the
  claim is corrected to "except through the re-fetch race".
- **U2 — upheld. The live check at a limit of 6 does not represent a
  40-request history.** A model quoting from two pages says little about
  one quoting from thirty. E8 must run at realistic depth and record the
  context size it concluded on.
- **U3 — upheld as a ruling for the gate, not a defect.** The self-check
  treats two runs differently: a run that concludes on its own with a bad
  quote fails the stage; a run forced to conclude with the same bad quote
  is turned back into a gap and the stage passes. That is a softening of
  the fail-closed rule for one class of run (BENCHMARK.md OQ-B3). Without
  the self-check the option can end worse than today (T1). The option
  cannot have both; which one the project prefers is the user's call.
- **U4 — upheld. One conclude-only turn leaves no room for an output
  retry.** The agent allows one output retry (measured, E6 D3). A brief
  that fails schema validation on request N needs request N+1, which the
  limit refuses — the run then ends as today's gap. Not worse than today,
  but it lowers the success rate; reserving two requests instead of one
  is the alternative and costs a request of research depth. [read, not
  run]
- **U5 — design point, noted.** The activity must know the run ended on
  the forced turn; the request count alone does not show it. The 008
  refusal record (in-memory on deps, never serialized) is the precedent.
- **U6 — not upheld.** "Request 40 is wasted when the brief is thrown
  away": request 40 is made today as well, and its tool call is charged
  and never read. The option spends the same request.
- **U7 — not upheld.** "Two capped sub-questions at 50% give a 25%
  success rate": with the fallback each sub-question stands alone; a
  failed one is today's gap.

## The brief's four hypotheses, checked on `bcfbffc`

| # | Hypothesis | Result |
|---|---|---|
| 1 | `SubQuestionFinding` carries `brief`, `usage`, `failed`, `error`; schema is salvage-shaped | **Holds** (`R/models.py:87-100`). The docstring states the 3-of-4 intent for *siblings*; it says nothing about a partial brief from the dead run itself. (read) |
| 2 | `_findings_from_results` turns a gathered exception into `failed=True` + error string, brief left empty | **Holds** (`R/step.py:105-113`). Also: `R/merge.py:41-51` skips a failed finding's `brief` entirely, so populating it would change nothing without a merge change. (read) |
| 3 | `RESEARCH_SQ_ACT`: 6 attempts, non-retryable `BudgetExceeded` / `UsageLimitExceeded` | **Holds** (`R/step.py:56-66`). (read) |
| 4 | Stage-level try: all-failed → degraded; any exception → `findings = []` | **Holds** (`R/step.py:254-271`). The refine loop has the mirror image: an exception there `break`s and keeps the last good brief (`:334-335`). (read) |

One refinement the brief does not state: after 008, the two death classes
the register row names **do not reach `failed=True` at all**. Both are
caught inside the activity and returned as a gap-only brief with
`failed=False` (`R/stage.py:307-320`, `:321-342`). So the place where the
partial work is dropped for those classes is the activity's own handler,
not `_findings_from_results`. (read; confirmed by E6 D1, D2)

## Where a sub-question run can die, and what happens today

| Class | Trigger | Today | Reaches |
|---|---|---|---|
| A. Request limit | `UsageLimitExceeded` at `max_requests` (40) | caught, returned gap-only, usage kept, `failed=False`, one attempt | `R/stage.py:307-320` |
| B. N4 after a refusal | `UnexpectedModelBehavior` with a refusal on the run's deps | caught, returned gap-only, usage kept, `failed=False`, one attempt | `R/stage.py:321-342` |
| C. Model-behaviour dead end, no refusal | `UnexpectedModelBehavior`: output validation retries exhausted ("Exceeded maximum output retries (1)", measured E6 D3/D4), or `run_code` retries exhausted on script errors | re-raised; Temporal retries up to 6 attempts, each a fresh run from scratch against already-spent persisted budgets; finally `failed=True`, zero usage | `R/stage.py:329-330`, `R/step.py:109-110` |
| D. Transient | provider/network error | re-raised and retried; a later attempt may succeed | `R/step.py:59-65` |
| E. Killed | start-to-close (20 min) or heartbeat timeout, worker loss | the activity cannot return anything | `R/step.py:57-58` |
| F. Stage-level | planner or synthesis activity fails after its 3 attempts | every finding dropped, stage-level gap-only brief | `R/step.py:269-271` |

The register row names A and B. C is the same shape (a run with real work
in it that ends in an exception) but takes a different route. F is design
question 3. (read, except where marked)

## Q1 — what partial state exists at death-time (measured, E6)

Setup: an agent shaped like production — `CodeMode()`, `ResearchDeps`,
`output_type=ResearchBrief`, one `get_page` tool that calls the real
`charge_scoped` and `write_page`. The scripted model fetches a new page
each turn and never concludes. Deaths D1 and D2 go through the real
`_research_subquestion_impl`; `capture_run_messages()` is wrapped around it
from outside.

| Death | Stage result today | Messages captured | Page bodies in history | Page files on disk |
|---|---|---|---|---|
| D1 request limit (3) | returned, 0 grounded, 0 sources, 1 gap | 7 | 3 of 3 | 3 |
| D2 N4 after refused fetch (cap 2) | returned, 0 grounded, 0 sources, 1 gap | 13 | 2 of 2 | 2 |
| D3 output-validation exhaustion, direct | raised `UnexpectedModelBehavior` | 7 | 1 of 1 | 1 |
| D4 = D3 through the stage handler | raised (would be retried) | 7 | 1 of 1 | 1 |

Findings:

- **M1 — the full message history survives every exception class that
  returns control to the activity.** `capture_run_messages()` holds every
  model response and every tool return up to the abort, including the
  complete text of each fetched page. It works wrapped around the existing
  call; nothing about the agent changes. (measured)
- **M2 — there is no structured partial brief.** `ResearchBrief` is the
  run's final output; before the final call there is only raw history. The
  parent assessment's statement stands. 008's refusal record holds refusal
  strings only; caller-owned `RunUsage` holds token counts only. Neither
  carries findings. (measured + read)
- **M3 — pages survive on disk but are not self-describing.** File names
  are `sha256(url)` (`R/verify.py:28-29`); nothing maps a file back to its
  URL or to the sub-question that fetched it. The verifier can check a
  quote against them; nothing can enumerate "what this sub-question
  fetched" from disk alone. (measured + read)
- **M4 — a history that ends mid-tool-call is repaired by the library.**
  D2 and D3 histories end with a tool call that never got a result. On a
  follow-up run with `message_history=`, pydantic-ai inserts a synthetic
  return ("The tool call was interrupted before a result was produced.")
  before the new user prompt. (measured, E6b)

## Q4 — can the partial state become a brief, and at what cost (measured, E6)

A follow-up run was made from each captured history with one instruction
("Stop researching. Conclude now with what you have already fetched.") and
a scripted model that quotes page text it can see in the history.

| Wrap-up | Result | Requests | `verify_brief` |
|---|---|---|---|
| W1a same agent, D1 history | brief with 3 grounded findings | 1 | clean |
| W1b agent with no tools, D1 history | same | 1 | clean |
| W1c same agent, fabricated quotes | brief with 3 grounded findings | 1 | 3 × `quote_not_found` |
| W1d same agent, carried request count 3, limit 3+1 | same as W1a | 4 total | clean |
| W2a / W2b, D2 history | 2 grounded findings | 1 | clean |
| W3a, D3 history | 1 grounded finding | 1 | clean |

Findings:

- **M5 — one extra model request can turn a dead run's history into a
  schema-valid brief whose grounded findings verify against the pages
  fetched before death.** Verified by the real `verify_brief`. (measured,
  scripted model)
- **M6 — the wrap-up call's spend is countable on the same usage object**
  (W1d), so it can be reported and priced like any other request. (measured)
- **M7 — a wrap-up brief is exactly as able to fail verification as any
  other brief** (W1c). And a verification failure is stage-wide: any
  violation in the merged brief records the research stage FAIL
  (`R/step.py:279-298`). [CORRECTED by A1: the brief is not discarded —
  it is returned unretained, unjudged and without a digest, and the human
  gate is skipped.] (measured + read)
- **No mechanical fold produces findings.** A `GroundedFinding` needs a
  `claim` and a chosen `quote`; an `InferredFinding` needs `reasoning`.
  Both are judgment. What code alone could recover is a list of URLs
  fetched — `sources_consulted` rows with empty `assessment` — and only if
  the fetch wrapper recorded them, because neither the disk (M3) nor
  `run_code` results (free-form script return values) give a reliable list.
  (read)
- **Not measured**: whether a real model (production is `zai:glm-5.3`,
  `agents/research/agent.yaml:2`) concludes with a valid brief when asked
  to on a long history; whether a provider accepts a history containing
  tool calls when the follow-up request offers no tools (W1b only shows the
  library allows it); the token cost of re-sending a 40-request history
  once more. [ASSUMPTION for all three until a live run]

## Q2 — raise vs return (read)

- Classes A and B already return rather than raise. Adding salvage there
  changes the *content* of an activity result, not the retry semantics.
- Class C re-raises today so that a non-budget model failure is retried
  (008 FR-005, `R/stage.py:327-330`). To salvage C the activity would have
  to catch it. Catching on every attempt removes the retry that might have
  produced a clean answer; catching only on the last attempt requires the
  activity to know its attempt number against a maximum that is set in
  workflow code (`R/step.py:63`).
- Each retry of a class-C failure re-runs the research from scratch while
  the persisted budget counters keep the spend of earlier attempts
  (`R/AGENTS.md:109-111`). The history of earlier attempts is gone; only
  the last attempt's could be salvaged.
- Class D must keep raising — a transient error says nothing about the
  work, and a retry is the right response.
- Class E cannot be salvaged from inside the activity at all.
- `tests/research/test_research_subquestion_activity.py:63-79` pins
  `failed is False` on exhaustion; `tests/research/test_research_fanout_wiring.py:68`
  pins the non-retryable names (parent assessment, `decide.md:170-171`).

## Q3 — the stage-level drop (read)

- `R/step.py:269-271` discards all findings when the planner or synthesis
  raises, including the case where every sub-question succeeded and only
  synthesis failed. `R/AGENTS.md:49-54` already lists this as a known trap,
  with its consequence: the next refine round restarts ids at `sq-0`
  against already-spent per-scope counters.
- The data needed to keep them is already in workflow memory: `findings`
  is assigned before synthesis runs. `merge_briefs` is pure
  (`R/merge.py:1-7`) and already produces every field except `summary`,
  `confidence` and cross-cutting contradictions.
- But `findings` is assigned inside `_fan_out_research`'s return; if the
  *planner* fails there are no findings to keep. Only the synthesis-failed
  case has anything to salvage.
- This is a different change from sub-question salvage: it is workflow
  code, needs no model call, and carries complete (not partial) work.

## Q5 — replay determinism (read)

- Sub-question salvage done inside the activity changes an activity
  *result*. Replay takes results from history, so existing histories replay
  unchanged — the same argument the parent assessment made for 008
  (`research-budget-enforcement/research.md:118-123`).
- New runs change shape downstream of a salvaged result: a brief with
  grounded findings schedules retain activities and a different digest
  where a gap-only brief scheduled none. That is ordinary data-dependent
  behaviour, already true of clean runs.
- The Q3 change is workflow code. An old history in which synthesis failed
  recorded "no retain activities"; replayed under new code that keeps the
  findings, it would schedule retains — a non-determinism error. It would
  need a patch marker (precedent: 007's marker on the failing branch only)
  or a decision moved into an activity [NARROWED by A2: into the existing
  `synthesize_brief` activity, not a new one]. [hypothesis — not
  reproduced; no such history is known to exist locally]
- 009 left a replay fixture for the research stage; any change here has a
  place to pin itself.

## Users & Demand

- **No local run shows a sub-question dying.** `runs/` has 115 entries;
  none has a `research/` directory. The five research rows in local
  benchmark records (`runs/benchmarks/bench-todo-api-greenfield-*`) are 3
  pass, 2 fail — both failures are `rejected:research.grounding`, not a cap
  or a model dead end. A grep of `runs/`, `benchmarks/`, `docs/reports` for
  "stopped early" / "did not complete" finds only documentation.
  (confidence: high, cited — but five rows is a small sample)
- **One recorded cap incident, before fan-out existed**:
  `bench-todo-api-greenfield-1785485669` exceeded the request limit
  (`tests/research/test_research_degradation.py:6`,
  `tests/research/test_research_e2e.py:270-274`). (cited)
- Research is off by default and on for two benchmark cases
  (parent `decide.md:105-109`). The people affected are the human at the
  research gate and the downstream stages of those runs. (cited)
- The stated want comes from the parent assessment's own residual and the
  user's ruling to do the design work — not from an incident. (cited:
  intake)
- The parent assessment's skeptic judged concluding-after-refusal to be
  harder for a real model than the fake showed, which would make class B
  more frequent, not less (parent `decide.md:125-129`). [ASSUMPTION — no
  live measurement]

## Prior Art

- **In this repo, same slice**: 008 established the pattern of keeping
  run-scoped state on a caller-owned object that survives the abort
  (`RunUsage`, the refusal record) and degrading once instead of retrying.
  Message capture is the same pattern applied to history. (read)
- **In this repo, opposite ruling**: BENCHMARK.md OQ-B3 — "the
  demote-to-inferred + still-judge variant was considered and deliberately
  not built" (`BENCHMARK.md:518-520`). The project has already once chosen
  a hard fail over a softer partial result in this stage. (cited)
- **In this repo, comparability precedent**: the 008 RESEARCH-SPEND BREAK
  MARKER (`BENCHMARK.md:34-43`) — a behaviour change for capped runs
  recorded as a marker, no benchmark re-run. (cited)
- **In the library**: pydantic-ai documents `capture_run_messages` for
  reading history after a failed run, and its usage-limit error text points
  at "budget-aware patterns" (seen in E6 output). The harness package ships
  `step_persistence` and `compaction` capabilities; whether either offers a
  conclude-at-limit behaviour was not investigated. [gap]
- **Elsewhere**: a final "answer now with what you have" turn when a step
  budget runs out is a common agent-loop pattern. [ASSUMPTION — general
  knowledge, no source fetched]

## Market & Context

- **What users cope with today**: a gap that names the sub-question and the
  cause, and a refine round at the research gate that re-plans from gaps
  (`R/step.py:311-323`). The shortfall is explained; the work is redone if
  the human asks. (read)
- **Cost of doing nothing**: for each dead sub-question, up to 40 model
  requests and its searches/fetches are paid for (and since 008, reported)
  and yield one gap line. A refine round then pays again, against a
  per-scope budget that is already spent if ids collide. (read)

## Data & Constraints

- Defaults: 4 sub-questions, 1 refine round, 40 requests per sub-question
  (parent `research.md:167, 241`). One wrap-up request per dead
  sub-question is at most 4 extra requests per wave, each re-sending that
  sub-question's whole history. [arithmetic, not measured]
- The request limit is the configured bound on model spend per
  sub-question. A wrap-up call after `UsageLimitExceeded` is by definition
  request 41 of 40. (read)
- Grounding is fail-closed and stage-wide, and it is the stage's known weak
  point: 2 of 5 local research rows failed it; BENCHMARK.md records
  "research grounding is unreachable for a mid-tier author model"
  (`BENCHMARK.md:189-193`). (cited)
- Brief content on salvaged paths changes what the research judge scores
  and what downstream stages read; nothing in `ResearchBrief` marks a
  finding's origin today (`R/models.py:58-72`). (read)
- Constraints carried in: D1 untouched; register file not edited; cap
  values and attempt budgets out of scope.

## Evidence Against the Idea

- **Nobody has seen the failure it addresses.** Zero dead sub-questions in
  local records; the one known incident predates the current design.
- **It adds load to the stage's weakest point.** A wrap-up brief is written
  by a model that has just failed to finish, on a long history, under an
  instruction to stop. If one of its quotes is not verbatim, the stage is
  recorded FAIL: no gate, no retention, no judge score, no digest — for
  the siblings' verified findings too (M7, A1). Today's gap-only brief can
  never cause that. Salvage can turn "one gap" into "a failed research
  row". Grounding failure is also the one failure the local records do
  show (2 of 5 rows).
- **Mechanical salvage yields almost nothing** — a URL list at best. The
  only salvage with content costs a model call past the configured limit.
- **The project already declined a softer-partial variant once** (OQ-B3).
- **The human can already recover**: the gap is explained and a refine
  round targets it.
- **Class C is the awkward one**: salvaging it trades away a retry that
  might have succeeded, or needs the activity to know it is on its last
  attempt.
- **Benchmark comparability**: capped runs would produce different briefs
  and different research scores than before, for a path no benchmark row
  has exercised.

## Gaps & Open Questions

- [NEEDS CLARIFICATION: real-model behaviour on a wrap-up call — does
  `zai:glm-5.3` produce a schema-valid brief with verbatim quotes from a
  long history? Needs a live run; not allowed in this pass.]
- [NEEDS CLARIFICATION: does the z.ai coding endpoint accept a request with
  tool calls in history and no tools offered (W1b shape)?]
- [NEEDS CLARIFICATION: how often does class C occur with the production
  model? Output retries are 1, so one malformed brief ends an attempt.]
- [NEEDS CLARIFICATION: does any stored Temporal history exist in which
  synthesis failed? It decides whether the Q3 change needs a patch marker.]

Closed after the first draft (both checked 2026-10-05):

- **Who reads the brief.** Downstream stages do not read its prose. The
  feature workflow passes on only the digest — a hash of grounded
  `(source_url, claim)` pairs (`src/sdlc/workflows/feature.py:376-392, 404`;
  `R/verify.py:87-93`); the graph path publishes the brief as a node
  payload and hands clarify the digest
  (`src/sdlc/workflows/graph_nodes/precode.py:100-108`). The brief's
  content reaches three places: the human at the research gate, the
  research judge, and episodic memory (verified grounded findings only,
  `R/step.py:349-353`). So only salvaged **grounded** findings travel
  beyond the gate; salvaged inferred findings, sources and summary are
  seen by the human and the judge and nowhere else. (read)
- **Error text for a failed finding.** `str()` of a Temporal
  `ActivityError` is the generic `'Activity task failed'`; the real cause
  sits on `__cause__` (constructed in `kroker-dev` with temporalio 1.31.0,
  not taken from a live failure). So a class-C gap today reads "this
  sub-question did not complete: Activity task failed" — the gap names the
  question but not the cause. (measured on a constructed error)

## Sources

No URL was fetched. All sources are repository paths (cited inline), the
two experiment scripts in `experiments/`, and the parent assessment under
`.specify/assessments/research-budget-enforcement/`.
