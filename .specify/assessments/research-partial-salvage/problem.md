# Problem Definition: Research work lost when a run ends in an exception

- **Slug**: research-partial-salvage
- **Created**: 2026-10-05
- **Inputs used**: intake.md, research.md (experiments E6, E6b)
- `R/` = `src/sdlc/stages/research/`

## Problem Statement

When part of the research stage ends in an exception instead of a final
answer, work that was already done and paid for is thrown away and
replaced by a one-line gap. This happens at two levels: a single
sub-question that hits its request limit or a model dead end returns
nothing of what it read, and a failed synthesis step discards every
sub-question's finished findings. The human at the research gate then
decides on less than the run actually learned, and a refine round pays for
the same ground again.

The idea arrived as a solution ("carry the partial findings"). The
underlying problems are three, and they are not equally strong:

| # | Problem | Where | Work lost | Strength of the case |
|---|---|---|---|---|
| P1 | A sub-question that dies in a way the activity already handles (request limit; retry exhaustion after a budget refusal) returns a gap and nothing else, though its full history is still in hand at that moment. | `R/stage.py:307-342` | partial — raw material, no conclusions yet (research M1, M2) | mechanism measured; never observed in a real run |
| P2 | A synthesis failure discards findings that are complete and already verified-shaped, and poisons the next refine round's ids and budgets. | `R/step.py:269-271`; `R/AGENTS.md:49-54` | complete findings from every sub-question | read; a documented trap; never observed in a real run |
| P3 | A sub-question that dies of a model dead end with no budget refusal is retried from scratch up to six times and ends as a gap whose stated cause is the generic "Activity task failed". Its spend is not reported either. | `R/stage.py:329-330`; `R/step.py:109-110`; `tests/replay/golden/context_reject.json:2` | up to six attempts' work, their usage, and the cause itself | measured on a scripted model; error string confirmed by a golden |

## Affected Users & Stakeholders

- **Users**
  - The human at the research gate — approves, rejects or asks for a
    refine round on a brief that under-represents what the run read
    (research: "Who reads the brief").
  - The research judge and the benchmark record — score and record a brief
    that is thinner than the work behind it; since 008 the spend is on the
    record, so the row shows cost without the corresponding content.
  - Episodic memory — receives no verified findings from a dead
    sub-question, so later runs cannot recall them.
  - Downstream stages are **not** direct users: they receive only the
    digest of grounded findings (`src/sdlc/workflows/feature.py:376-392`).
- **Stakeholders**
  - The user (register owner) — rules on whether briefs and benchmark
    comparability may change; ruled 2026-10-05 that the design work
    proceeds.
  - Editors of the research slice — carry whatever code and invariants
    this adds.
  - Anyone comparing benchmark rows across the change.

## Goals

- G1 When work exists at the moment a run stops, the brief shows more than
  a gap — or the assessment records, with reasons, why a gap is the right
  answer for that case.
- G2 A stopped run is never *worse* for the stage than it is today: no new
  way for one sub-question's trouble to fail the stage or lose its
  siblings' work.
- G3 Anything carried from a stopped run is recognisable as such by the
  human, the judge and a reader of the benchmark record.
- G4 A reader of the brief can tell why a sub-question stopped.
- G5 Each of the brief's five design questions is committed to or declined.

## Non-Goals

- Changing cap values, attempt budgets or timeouts.
- The architect's research surface (D1, register C12).
- The other fail-and-continue Gotchas: degraded briefs recording PASS,
  rejection recording no row, refine-loop breakouts.
- Loosening the grounding rule or the verifier in any way.
- Making a run killed from outside (timeout, worker loss) recoverable.
- Preventing sub-questions from hitting caps in the first place by tuning
  prompts or limits.
- Editing the register.

## Success Metrics

- For each death class in scope: a test in which a scripted run stops with
  N pages read yields a brief containing more than the gap, where today it
  yields the gap alone. (baseline: 0 grounded, 0 sources — measured, E6
  D1/D2)
- No scenario in which a stopped sub-question causes a stage-level
  grounding failure that today's code would not have caused. (baseline:
  impossible today — a gap-only brief has nothing to verify)
- Extra model requests per stopped sub-question: bounded and reported on
  the research row. (baseline: 0 extra)
- Clean runs: byte-identical activity inputs and results, existing replay
  fixture unchanged. (baseline: 009's fixture passes)
- A synthesis failure with k successful sub-questions yields a brief with
  their findings. (baseline: 0 findings, stage-level gap)
- *Qualitative, unmeasurable in this pass*: a real model produces a usable
  brief when asked to conclude from a long history. (baseline: unknown)

## Cost of Inaction

Nothing breaks. Every case is already explained by a gap, spend is already
reported (008), and the human can ask for a refine round. What is paid:

- per stopped sub-question, up to 40 requests of work reduced to one line;
- on a synthesis failure, all findings of the wave, plus a refine round
  that restarts ids at `sq-0` against spent per-scope budgets;
- for class-C stops, a gap that does not say what went wrong.

No local record shows any of these happening (research: Users & Demand).
The cost of inaction is therefore a latent cost, sized by a frequency
nobody has measured.

## Criteria for judging a mechanism

To be applied in shape and decide. Revised after advisor consult 1
(`.workspace/tmp/research-partial-salvage-advisor-1.md`); listed in
weight order.

- C6 **Grounding rule unchanged** — carried findings pass the same
  `verify_brief`; filtering out what fails is allowed, relaxing the check
  is not.
- C1 **Never worse than gap-only** — a salvage attempt cannot make the
  recorded outcome worse than today's: no grounding violation reachable
  from carried content, no usage lost, no retry removed.
- C3 **Replay-safe** — existing histories replay. A change lives inside
  the result of an activity the old history already ran, or behind a patch
  marker; a new activity on an old branch is not safe.
- C2 **Retry semantics intact** — transient errors still retried; no
  doomed-retry loop reintroduced; a model dead end with no refusal keeps
  raising unless the change is aware of the last attempt.
- C4 **Spend bounded and reported honestly** — every extra request is on
  the finding's usage and priced. A call made after a request-limit stop
  is request N+1 of N; whether that is allowed is the user's ruling, not a
  detail.
- C5 **Distinguishable** — (a) in the brief, for the human and the judge;
  (b) in the benchmark record (precedent: the 008 break marker). A new
  field on the brief also changes what the judge is shown.
- C8 **Small blast radius** — lines of workflow code touched; new fields
  on shared models.
- C7 **Worth carrying** — a gate, not a weight: with no observed stopped
  sub-question, declining is the default and any mechanism must beat it on
  evidence that can be had cheaply.

## Open Questions

- [NEEDS CLARIFICATION: how often each of P1–P3 fires in real runs — no
  local evidence; needs live runs.]
- [NEEDS CLARIFICATION: does the production model conclude usefully when
  asked to, on a long history? Decides whether P1 is solvable at all.]
- [NEEDS CLARIFICATION: is a brief that changes on capped paths acceptable
  for benchmark comparability with a marker (the 008 precedent), or must
  salvage be switchable off for benchmark cells?]
- [NEEDS CLARIFICATION: is P3's uninformative cause in scope here, or a
  separate small item? It is not salvage, but it is the same loss seen
  from the gate.]
- [NEEDS CLARIFICATION: does any stored history exist in which synthesis
  failed? Decides whether P2 needs a patch marker.]
