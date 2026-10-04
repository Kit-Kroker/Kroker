# Advisor consult 1 — research-partial-salvage (after the research stage)

Role contract: consultation only — read tools, no edits to the repo, no
commits. Write your full answer to
`.workspace/tmp/research-partial-salvage-advisor-1.md` and reply in the
pane with only that path.

Read first: `.specify/assessments/research-partial-salvage/intake.md` and
`research.md` (and `experiments/e6_death_state.py` if you want the
harness). Treat every claim in them as a hypothesis — disproving one is the
most useful thing you can do.

## What I need from you

1. **Evidence gaps.** Which claims in research.md are wrong, overstated or
   missing a check I could still make without a live model run? In
   particular:
   - the death-class table (A–F): is a class missing, or misrouted? Is it
     true that after 008 classes A and B never reach `failed=True`?
   - M7: is it right that one unverifiable quote in a salvaged sub-question
     fails the whole stage closed (`step.py:279-298`), siblings included?
   - Q5: is the replay reasoning sound — activity-side salvage is
     replay-safe for old histories; the stage-level change at
     `step.py:269-271` is workflow code and needs a patch marker?
   - the open item on what `str()` of the gathered exception yields in
     `_findings_from_results`.
2. **Criteria.** I intend to judge mechanisms in the define/shape stages
   against these. Tell me which are wrong, missing or mis-weighted:
   - C1 never worse than today: a salvage attempt must not turn "one gap"
     into "stage failed" or lose usage.
   - C2 no new retry-semantics risk: transient errors still retried; no
     doomed-retry loops reintroduced.
   - C3 replay-safe: old histories replay; decisions live in activities.
   - C4 spend bounded and reported: any extra model call is counted,
     priced, and bounded per sub-question.
   - C5 distinguishable: a salvaged finding can be told apart in the brief
     and in the benchmark record.
   - C6 grounding rule unchanged: nothing loosens `verify_brief`.
   - C7 worth it: there is evidence the path is hit, or the cost of
     carrying the code is small enough not to need it.
3. **Candidate mechanisms** — I have not chosen. Say which you would rule
   out early and why, and whether one is missing:
   - K0 decline: keep gap-only (documented).
   - K1 wrap-up call inside the activity for classes A and B (one extra
     request from the captured history), with activity-side verification
     of the salvaged brief before it is returned (unverified grounded
     findings dropped or the salvage discarded), plus a provenance marker.
   - K2 mechanical only: record fetched URLs on deps, return them as
     `sources_consulted` on the degraded brief; no model call.
   - K3 stage-level only (design question 3): on synthesis failure keep
     the gathered findings via the pure `merge_briefs`; no sub-question
     salvage.
   - K4 prevention instead of salvage: reserve the last request(s) of the
     limit for a conclude turn so the run ends normally.
   - combinations (e.g. K3 now, K1 behind evidence).

Keep it short: findings first, each with file:line where you checked.
