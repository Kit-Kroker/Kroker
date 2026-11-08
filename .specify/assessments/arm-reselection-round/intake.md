# Idea Intake: Arm re-selection round — restore a separable (or bar-based) corpus

- **Slug**: arm-reselection-round
- **Created**: 2026-11-08
- **Source**: repo path `.workspace/tasks/2026-11-03-arm-reselection-round.md` + pasted orchestrator TASK BRIEF
- **Type**: fix (measurement instrument broken) with an `exploration` component (choose among three arm strategies)

## Idea (as captured)

Task brief (pasted, orchestrator):

> Arm re-selection round: restore a separable (or bar-based) corpus after the
> R019 re-prove series showed glm-5.3 vs glm-5.3-flash does not separate. Read
> .workspace/tasks/2026-11-03-arm-reselection-round.md (candidates:
> flash-strong/no weak arm with absolute oracle bar; cross-provider pair under
> ADR-6; wait for z.ai catalog). Treat the card's numbers as hypotheses to
> verify against BENCHMARK.md and main 9a302401/d5d76150. Out of scope:
> lowering SEPARATION_MARGIN to fit data. NO PAID RUNS in assessment; proving
> runs need explicit user clearance. Stop at the decide gate.

Backlog card (excerpt, verbatim):

> The corpus has no working measurement pair. The 2026-11-03 paid series
> proved the post-R019 pairing `glm-5.3` / `glm-5.3-flash` does not separate
> (margins 0.000 / 0.074 / 0.125 against the 0.15 bar; readtime's weak arm
> died at clarify 3/3), and the weak arm is systemically fragile (7 lost
> weak runs across the series). Every additional rerun of this pairing is
> spent money on a question already answered.
>
> 1. **flash-strong, no weak arm** — flash was the series' best scorer
>    (0.92–0.94 on cat-cafe, above glm-5.3's mean). Turns the corpus from
>    "two arms separate" into "pipeline+model clears an absolute oracle
>    bar". […] changes acceptance semantics (verdict logic, `benchmark
>    accept`, SEPARATION_MARGIN becomes a bar, not a gap).
> 2. **Cross-provider pair under ADR-6** — real capability separation, but
>    needs a second provider budget (user's Anthropic access is
>    subscription-only) and untangles ADR-6 roles […].
> 3. **Wait for the z.ai catalog** — a future model (glm-5.4+) […]. Zero
>    work now, unknown date.
>
> Explicitly out: lowering SEPARATION_MARGIN to fit the measured margins.

## Restated

Choose (or reject all of) three ways to give the benchmark corpus a working
acceptance instrument again, now that the same-provider glm-5.3 / glm-5.3-flash
pair has been measured not to separate: drop the weak arm and judge against an
absolute oracle bar, pair across providers, or wait for a new z.ai model.

## Origin & Context

- **Raised by**: orchestrator, R019 re-prove series close-out (card filed 2026-11-03; opened on user's word 2026-11-08).
- **Trigger**: paid re-prove series (`2026-10-27-r019-reprove-separation-reruns`) — verdicts committed on main `9a302401`, living docs `d5d76150`; corpus tally 0 of 8.

## First-Glance Unknowns

- [NEEDS CLARIFICATION: do the card's figures (margins 0.000/0.074/0.125, bar 0.15, flash 0.92–0.94 on cat-cafe, "7 lost weak runs", n≤6/arm) match BENCHMARK.md and the 9a302401 verdict files?]
- [NEEDS CLARIFICATION: what does the corpus/acceptance gate actually exist to prove — that the *pipeline* adds value, or that the *benchmark* discriminates model capability? Option 1 answers a different question than options 2–3.]
- [NEEDS CLARIFICATION: is a second paid provider budget available at all (Anthropic is subscription-only per card)?]
- [NEEDS CLARIFICATION: is there any signal on z.ai catalog timing?]
- [NEEDS CLARIFICATION: is the weak-arm fragility a property of flash, of the pipeline's clarify stage, or of harness infrastructure?]
- [NEEDS CLARIFICATION: how much code/spec surface depends on the two-arm semantics (verdict logic, `benchmark accept`, SEPARATION_MARGIN)?]
