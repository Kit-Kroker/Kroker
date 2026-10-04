# Idea Intake: Salvage partial research work when a sub-question run dies

- **Slug**: research-partial-salvage
- **Created**: 2026-10-05
- **Source**: repo path `.workspace/tmp/assess-brief-h2-salvage.md` (task
  brief, pasted via the orchestrator); register row C11 in
  `docs/reports/external-ideas-2026-09.md:79`; prior assessment
  `.specify/assessments/research-budget-enforcement/` (H2 residual)
- **Type**: improvement

## Idea (as captured)

Task brief, subject paragraph:

> Carry partial research work when a sub-question run ends in an exception
> (request limit, N4 `UnexpectedModelBehavior`) instead of dropping it for a
> gap-only brief. The user ruled 2026-10-05 to proceed with the DESIGN WORK:
> this assessment decides HOW (mechanism and scope), not whether. It ends at
> a USER GATE via the orchestrator; a documented decline (keep gap-only) is
> an acceptable outcome — the register row itself says "may be declined".

Register row C11 (`docs/reports/external-ideas-2026-09.md:79`):

> **Salvage partial research work** — when a sub-question run ends in an
> exception (request limit, N4), carry the partial findings instead of
> dropping them for a gap-only brief | assessment
> `research-budget-enforcement` (H2 residual) | New — needs its own ruling
> (changes briefs and benchmark comparability; may be declined) |
> `src/sdlc/stages/research/`

Prior assessment's ruling on the parent item
(`research-budget-enforcement/decide.md:55`):

> **H2** exhaustion discards partial work — **not a defect as stated;
> residual is a design question** … Work is lost only when the run ends in
> an exception: request limit, or N4. No structured partial finding exists
> to carry — the brief is the run's final output.

The brief also hands over five design questions the concept must commit to
or decline, quoted in short form:

> 1. What partial state exists at death-time?
> 2. Raise vs return in the activity.
> 3. The stage-level drop at `step.py:271`.
> 4. Salvage cost and comparability.
> 5. Replay determinism.

And four current-code hypotheses, flagged by the brief itself as "verify
before trusting":

> - `src/sdlc/stages/research/models.py:87-100`: `SubQuestionFinding`
>   already carries `brief: ResearchBrief` … plus `usage`, `failed`,
>   `error`. The schema is salvage-shaped — the open question is what
>   populates `brief` when a run dies.
> - `src/sdlc/stages/research/step.py:105-113` (`_findings_from_results`):
>   a gathered exception becomes `failed=True` + error string only; the
>   partial `brief` field stays at its default (empty).
> - `step.py:56-66` `RESEARCH_SQ_ACT`: 6 attempts, non-retryable
>   `BudgetExceeded` / `UsageLimitExceeded`.
> - `step.py:254-271`: stage-level try — all-failed → degraded gap-only
>   brief; on any exception → `findings = []`, so even already-successful
>   sub-question findings are dropped when synthesis or fan-out raises.

## Restated

When a research sub-question run ends in an exception rather than a final
answer, the stage today records only a failure marker for it; the proposal
is to carry whatever partial work that run produced into the research
brief. The assessment is asked to settle the mechanism and scope of doing
so, or to document a decline that keeps the current gap-only behaviour.

## Origin & Context

- **Raised by**: the `research-budget-enforcement` assessment (H2 residual,
  deferred there as "needs ruling"); recorded by the user as register row
  C11.
- **Trigger**: user ruling of 2026-10-05 to proceed with the design work,
  relayed by the orchestrator's task brief. The original H2 item came from
  the research-budget cluster in the inbox (SG-5).
- **Landed since the parent assessment** (per the brief, not yet
  re-verified here): 008 on main `d51eef5` — caller-owned usage survives
  aborts, refusal record on deps, the `UnexpectedModelBehavior` clause
  degrades only when refusals are non-empty; 009 on main `bcfbffc` — retain
  is pure from the verification pair, replay determinism pinned by tests.
- **Constraints carried in with the idea**: D1 (architect usage surface,
  register C12) is out of scope; the register file is user-owned and not
  edited; cap values, attempt budgets and the other fail-and-continue
  Gotchas are out of scope; artifacts live only under this assessment
  directory; any measurement runs in the `kroker-dev` container.

## First-Glance Unknowns

- [NEEDS CLARIFICATION: do the four current-code hypotheses still hold on
  main `bcfbffc`? Line numbers and behaviour predate nothing in particular
  but are unverified.]
- [NEEDS CLARIFICATION: Q1 — what partial state exists when a sub-question
  run dies? Is there any intermediate structured brief, or only message
  history and tool results, and what of that can the caller still read
  after `UnexpectedModelBehavior` or a request limit?]
- [NEEDS CLARIFICATION: Q2 — if the activity catches a doomed run and
  returns `failed=True` plus a partial brief, which error classes are
  caught and which still raise for Temporal's transient retry?]
- [NEEDS CLARIFICATION: Q3 — should the stage-level except keep gather
  successes when only synthesis or part of the fan-out failed? Is that the
  same change as sub-question salvage or a separate one?]
- [NEEDS CLARIFICATION: Q4 — does turning raw partials into brief content
  need an extra LLM call or a mechanical fold, and how are salvaged
  findings told apart from clean ones in the brief and in the benchmark
  record?]
- [NEEDS CLARIFICATION: Q5 — can any of this be done with every decision
  inside activities, leaving workflow code deterministic under replay?]
- [NEEDS CLARIFICATION: how often does a sub-question run actually end in
  an exception in real runs? The parent assessment measured the mechanism,
  not the frequency.]
- [NEEDS CLARIFICATION: who consumes a salvaged brief downstream (the
  research gate, later stages), and would partial, unverified material
  help or mislead them compared with an explicit gap?]
- [NEEDS CLARIFICATION: the parent assessment stated "no structured partial
  finding exists to carry" — does 008's refusal record or caller-owned
  usage change that statement?]
