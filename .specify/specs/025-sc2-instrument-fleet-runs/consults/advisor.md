# Round 025 design-advisor consult

One pick per decision. Evidence is `file:line` as read this session. Anything I did not confirm is marked **unverified**.

## D1. Where `raised_at` comes from

**Pick: derive it in `build_run_summary` from the existing `GATE_AWAITED` event's `at`. Store it as `GateOutcomeSummary.raised_at`. Emit nothing new.**

- `_on_gate_awaited` emits `GATE_AWAITED` with `gate` and `round` (`workflow/run_host.py:50-51`). `_emit` stamps `at = workflow.now()`. That is the same workflow task as `opened_at=workflow.now()` at `gates.py:239`. Nothing yields between them (`gates.py:239-244`), so the two timestamps are equal.
- A new emitted field changes the workflow's event payload for no gain. The derivation reads only the trace, which the summary already receives.
- **Do policy-decided gates emit AWAITED?** No, and that is correct.
  - `GatePolicy.OFF` takes the first branch (`gates.py:231`).
  - A SOFT gate with an approving `auto_decision` takes the second (`gates.py:235`).
  - Neither opens a pending or calls `_on_gate_awaited`. Both are `decided_by="policy"` and never count as human, so they need no `raised_at`.
- **A SOFT escalation that a human then answers** goes through the `else` branch (`gates.py:237-244`). It does emit AWAITED, with the same `(gate, round)` key as the later `GATE_DECIDED`. This is the case you asked about, and it works.
- The merge override is covered too.
  - `ctx.gate("merge", ...)` opens at `merge/step.py:59`. That emits AWAITED.
  - The bare `GATE_DECIDED` at `merge/step.py:569` is a second emit on the same key, and `_enrich` merges them (`summary.py:74-87`).
  - Set `raised_at` after the dedup loop, from a `{(gate, round): at}` map built over the trace. Don't add it to `_ENRICH_OPTIONALS`.
- Engaged time uses the human's own `decided_at`, which is stamped at signal time (`gates.py:128`). It does not use the enriched emit's time.
- **Hazard 1: the "human" test must not be `== "human"`.**
  - The override emit sets `decided_by=(gate.reviewer or "human")` (`merge/step.py:569-577`).
  - `_enrich` lets the later event's always-present fields win (`summary.py:81-84`). So `decided_by` can be a reviewer name.
  - SC-2 must treat "human" as `decided_by not in {"policy", "timeout"}`.
  - SC-6's `g.decided_by == "human"` (`sc_rollup.py:179`) probably undercounts for the same reason. That is a pre-existing issue to log, not to fix this round. **Unverified:** whether any real run sets `reviewer`.
- **Hazard 2:** a human decision with no matching AWAITED leaves `raised_at = None`. Count it as "not measured" for that run. Never let it read as zero.

## D2. Clarification batching

**Pick: one interaction per `ask_and_wait` batch, not N.**

- ASKED events for a batch are all emitted in one loop with no await between them (`question_host.py:60-69`). The wait is a single `wait_condition` over all ids (`question_host.py:79-82`). The ANSWERED events are all emitted after it, in one loop (`question_host.py:92-106`).
- So every question in a batch shares one raise time and one answer time. Counting N interactions would apply the 10-minute cap N times to one sitting. That inflates SC-2 by up to a factor of N, and the intervals overlap exactly.
- Batch key: `(stage, ASKED.at)`.
- A batch is human iff at least one question has `answered_by == "human"`. Its engaged time is `ANSWERED.at - ASKED.at`, capped once.
- Add `raised_at` and `answered_at` to `ClarificationOutcome`.
- **Limit:** per-question answer times are not recorded. The signal handler at `question_host.py:36-41` stores no timestamp. Don't add one. The batch end is the last answer, which is the right bound.
- The `OFF`-policy path (`clarify/step.py:293-312`) emits ASKED and ANSWERED(suggested) together. It is never human and never counts.

## D3. Interactions in scope

**Pick: all `GATE_DECIDED` human decisions, plus clarification batches. Nothing else.**

- `build_run_summary` already iterates every gate (`summary.py:133-138`). The `task:<id>` escalation, `budget` (`summary.py:169-171`), `merge`, `deploy` and `clarify` gates all go through `_gate`. So they need no special cases.
- The pending kinds are `clarify`, `stage_gate`, `task_escalation` and `merge_gate` (`pending.py:32,48,60,74`). Those four are everything the inbox can hold. No other inbox kind exists.
- **Concurrency caveat.** Wave-mode `task:<id>` gates can be open at the same time (`gates.py:105-110`). Summing capped intervals then double-counts one human sitting. State in the SC-2 note that the figure is an upper bound when interactions overlap. Do not add interval-union logic this round.
- **Out of scope, and stated as such:**
  - the owner's out-of-band work (reading a PR, fixing the host);
  - the fleet protocol's own operator effort (B.5, B.6);
  - maintenance-loop gates (A.4).

## D4. Where the cap is applied, and the field shape

**Pick: store raw times in the summary and apply the cap in `sc_rollup`.**

- FR-004 requires that changing the cap needs no re-run. So the summary stores only raw `raised_at`, `decided_at` and `answered_at`.
- `sc_rollup` owns `ENGAGEMENT_CAP_S = 600` (the Q1 ruling) and computes everything derived: engaged time, wait, count, the median, and the zero-interaction count.
- Fields to add, all additive with defaults:
  - `GateOutcomeSummary.raised_at: datetime | None = None`
  - `ClarificationOutcome.raised_at` and `.answered_at: datetime | None = None`
  - `RunSummary.operator_instrumented: bool = False`
- **The marker is needed.** `build_run_summary` sets it `True` on every new summary. Without it, a pre-025 run with no human gates looks the same as a measured zero (A1-AS3 versus AS4). It also keeps legacy runs out of SC-2's n and lets the rollup name them.
- **Per-run states:**
  - **not measured:** the marker is false, or any human interaction has `raised_at` or `answered_at` of `None`.
  - **zero:** the marker is true and there are no human interactions.
  - **measured:** otherwise.
- **Replay safety.** The change is in the pure summary builder only. It adds no events, signals or commands. **Unverified:** that nothing pins `RunSummary`'s JSON shape.
  - Check whether `RunSummary` or `GateOutcomeSummary` set `extra="forbid"`.
  - Check whether any golden or fixture dump compares serialized summaries. The `2026-09-24-dashboard-fixture-dump-drift` backlog item suggests fixtures may need regenerating.
  - Read `src/sdlc/workflows/AGENTS.md` before touching `_retro`.

## D5. "Shipped" definition and the n floor

**Pick: keep the spec's definition and `MIN_RUNS = 5`. Make the plan pre-authorise the 7th run for an SC-2 shortfall.**

- `MIN_RUNS = MIN_OBSERVATIONS = 5` (`runs.py:38`, `sc_rollup.py:26`).
- Shipped means `deployed:` or `merged-not-deployed:`. That is narrower than SC-1's `REACHED_PREFIXES`, which also counts `rejected:merge` (`sc_rollup.py:34`). So SC-2's n is at most SC-1's n.
- With 6 runs, a single case failure leaves 5 shipped, exactly at the floor. Two failures leave n/a. The 7-run cap in B.3 is the only slack.
- The plan should say in advance: if shipped measured runs are below 5 after run 6, run 7 is pre-authorised. If SC-2 is still n/a after 7, report "not measurable at this n". Do not extend the delegation.
- **Zero-heavy medians.** Under SOFT, most runs may have no human interaction, so the median is probably 0 and trivially meets ≤15. The spec's zero-count and policy-mix lines (A2-AS4, A3) are the right guard. I'd add two figures:
  - the median over human-touched runs only;
  - the max.
  Both are supplementary and not the headline.
- **Policy mix.** Compute it from `{g.policy for s in summaries for g in s.gates}`. SC-6 already reads `g.policy` (`sc_rollup.py:178`). Benchmark runs force every gate to `spec.gate_policy` (`benchmarks/workflow.py:157-164`), so the mix is uniform within a fleet. Render it as a line beside SC-1 and SC-2.
- **Interaction with SC-1.** `_unattended_to_merge` fails a run on any human decision before the merge gate (`sc_rollup.py:92-101`). A run the owner answers an escalation for therefore costs SC-1 and adds to SC-2. The two numbers trade off, so report them together.

## D6. Q3: can the fleet be z.ai-only?

**Pick: say "z.ai-only holds for the deveval runs. todo-api, cat-cafe and the smoke stamp need the Anthropic judge." Don't build a `--no-judge` switch. Keep the case list.**

- **Judging is skipped when a stage has no rubric.**
  - `_build_judge_input` returns `None` for a missing or empty rubric (`judge.py:89-91`).
  - `_judge` then returns `QualityScore(score=None)` without calling the activity (`benchmark_host.py:146-158`).
  - `rubrics: {}` is set in readtime, geotext and lice. So those three runs make no workflow judge calls.
  - A repo grep found no `rubric` in any case's `oracle/` directory, so oracle rubric tasks look absent (`oracle.py:391-404` would call the judge for them). **Unverified:** I did not open the oracle files, only grepped.
- **todo-api has rubrics** for `architect` and `clarifier`. cat-cafe has them for `clarifier`, `architect`, `planner`, `qa` and `research`. Both set `judge_model: anthropic:claude-sonnet-5`. Those runs spend Anthropic.
- **The smoke stamp needs the judge.** `check_smoke` requires a non-`None` rubric score on every `clarify` and `architecture` record (`smoke.py:78-88`). Smoke runs the `smoke_case` (todo-api, `role: smoke`). A rubric-less case cannot pass it, so smoke cannot be made judge-free.
  - Cost is small: two rubric calls plus step generation (`judge.py:172`).
  - It is a separate announced line in the ceiling, as GATE 1 Q3 requires.
- **Adversary: it does not run in fleet runs, by default.**
  - `adversarial_review_enabled` defaults to `False` (`core/models.py:465`).
  - The adversary is gated on it at `code/step.py:822-829` and `review/step.py:199`.
  - A grep of `src`, `benchmarks` and the repo's yaml found no case or config that turns it on. That grep was not exhaustive for env or CLI overrides.
  - `agents/adversary/agent.yaml:13` is `anthropic:claude-sonnet-5`, so it would spend Anthropic if enabled. Every other agent yaml I listed is `zai:` or `zai-coding-plan/`.
  - **Pre-flight check:** confirm the fleet config resolves `adversarial_review_enabled` to `False`. Record it in the provenance.
- **Why no switch:**
  - It would change what the benchmark measures. Rubric scores feed quality columns and the smoke condition.
  - Dropping the two rubric cases to avoid it removes the only cases with held-out grading, tasks and vetoes. That is the cat-cafe rationale in B.3.
  - The cost is a few judge calls per run. It belongs on the ceiling as its own line.
- **Plan item:** price the judge line per case from the rubric count. cat-cafe has five rubric keys and todo-api has two. The plan should still cost them and not assume them negligible.

## D7. SC-3 expectation

**Pick: expect few loops and plan for SC-3 to render n/a. Report it as "not measurable at this n". Don't choose cases to force loops.**

- **Definition.** A loop is a `(run, task)` with any `code` record at `fix_attempts > 0`. It succeeds if the last attempt passes (`sc_rollup.py:117-131`). The n/a floor of 5 applies to loops, not runs (`sc_rollup.py:133-134`).
- **Trigger.** A loop starts when the attempt fails tests, QA, drift or review (`code/step.py:756`). The attempt budget is `max_fix_attempts = 2` (`core/models.py:424`). Exhaustion escalates to `task:<id>`, which is a human interaction for SC-2 as well.
- **No local evidence.** This host has no benchmark records: `runs/` holds only `pipeline`, and the spec admits the cost evidence was not found. I can't give an observed loop rate. **Unverified: all numbers below are guesses.**
- **Estimate.** If a run has a handful of tasks and a few percent to tens of percent of attempts fail, then 6 runs could produce roughly 0 to 6 loops. Reaching n≥5 is possible but not likely.
  - cat-cafe is the likeliest source: multi-task with held-out grading.
  - The small deveval cases are likelier to pass first try.
  - **Unverified:** I did not count tasks per case.
- **Implication.** Don't swap cases to buy loops. That selects for failure and breaks comparability (B.4). The spec's interpretation guard already covers this (spec.md, "Interpretation guard"). Report `n=<loops>` and "not measurable at this n" if it falls short.
- **Planning notes:**
  - Count the tasks per case from `tasks.yaml` and `case.yaml` before GATE 2, to put a number on the guess. That is one read.
  - A loop that exhausts and escalates is a case failure under B.5. It stays in SC-3 as a failed loop and counts in SC-2 when the owner answers.
  - If SC-3 is n/a, the P4 exit claim is "SC-3 not measurable at n=6". It is not "met". The fleet report must say so (FR-025).
