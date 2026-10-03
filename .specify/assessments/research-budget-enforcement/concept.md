# Concept: Research budget-enforcement defect cluster

- **Slug**: research-budget-enforcement
- **Created**: 2026-10-03
- **Recommended option**: B' — Option B re-cut after measurement: one small
  S-batch, then two separate M items (see "Recommendation — revised")

## What separates the options

The items split cleanly on one line: does the fix change what a run *does*
at a cap, or only what it *records* and how safely it stores state?

- **Record / storage / determinism** (H1 at the cap, H3, H5, notes): each has
  an in-repo precedent, changes no brief, and is expected to leave replays of
  clean runs identical.
- **Cap behaviour** (H2, N4, H4, and the architect's limits): the right fix
  depends on what a refusal actually does under CodeMode, which nobody has
  run. Sizing these now would be guessing.

## Options

### Option A — do nothing; the Gotchas are the mitigation

- **Sketch**: leave the code as is. `AGENTS.md` already warns editors. Correct
  only the notes that are wrong (the "uncapped" wording, the `scope == "run"`
  bullet, three stale docstrings).
- **Appetite**: small (under an hour, docs only).
- **Trade-offs**: zero risk to briefs and replays. Capped runs keep
  under-reporting research spend; the wedge-on-truncated-file and the
  workflow-side file read stay latent. Defensible only if caps are never hit —
  and one benchmark run is recorded as hitting one.
- **Rabbit holes**: none.

### Option B — repair the record and the hazards; measure before the rest

- **Sketch**: one small batch that makes a capped sub-question report its real
  model spend, makes the budget file write crash-safe, removes the page read
  from workflow code, and corrects the notes. Alongside it, one measurement
  task (E1 below) that shows what a budget refusal really does in production
  configuration. Everything that changes cap behaviour waits for that result
  and comes back as its own short spec.
- **Appetite**: small — one S-batch crew run (four S items plus one
  experiment).
- **Trade-offs**: fixes the only item that silently corrupts a record on an
  ordinary run, and the two that can bite on crash or replay, without
  altering any brief. Leaves P2 (lost work) and the H4 leak open, knowingly,
  until measured. Benchmark rows for capped runs will show *more* research
  spend than before — a visible break in history that needs a note.
- **Rabbit holes**:
  - the `calls` field: today it counts sub-questions, not model requests.
    Recovering usage must not quietly change its meaning — keep `calls` as is
    unless the user rules otherwise;
  - spend lost on attempts that raise (not return) is NOT repaired by this
    batch; it must be stated as a known residual, not implied fixed;
  - the retain change must be shown replay-identical for clean runs, and no
    replay fixture covers research today — the batch has to add one.

### Option C — close the whole cluster in one feature

- **Sketch**: Option B plus: treat `UnexpectedModelBehavior` as exhaustion,
  make refusals reach the model as data so it concludes, compensate the run
  counter, align the architect's ceilings and limits with the stage, and hand
  the architect's research spend back (6.2).
- **Appetite**: medium-to-large — a full spec and plan; several replay-visible
  changes.
- **Trade-offs**: one pass, no residuals. But it bundles a product decision
  (what the model is told at the cap changes briefs and benchmark
  comparability), an unmeasured mechanism, and a D1 re-ruling into what is
  otherwise a defect batch. Protocol sizing forbids batching M and larger
  items; this is at least three of them.
- **Rabbit holes**: salvaging partial work needs the agent's message history,
  because a brief exists only at run end; a two-counter transaction needs a
  lock order; every way of returning the architect's usage crosses an
  activity boundary.

## Recommendation — revised after E1/E2 and the skeptic's kill-case

Option B's line (record now, cap behaviour later) did not survive
measurement. E1 showed that on the production path the spend loss at a
budget cap runs through the uncaught `UnexpectedModelBehavior` (N4), which
sits in the same handler as H1, and that the run-counter leak (H4) is large
enough to drain sibling sub-questions. Splitting H1 from N4 and H4 would ship
a fix that misses the main production path. The skeptic also showed the H5
fix is not a one-line removal.

**Revised recommendation: Option B', the same appetite re-cut along what was
measured.**

1. **S-batch (two S items)** — crash-safe budget write (H3) and the notes.
2. **M-1, cap handling at the stage boundary** — H1, N4 and H4 together,
   one short spec. This is where the measured loss is.
3. **M-2, retain without workflow I/O** — H5, keeping the "only verified
   findings are retained" contract, with the first research replay test.
4. **Deferred / needs a ruling** — carrying partial work (H2 residual) and
   the architect surface (6.2, N2, N3).

After the skeptic's second pass, decide.md recommends scheduling items 1 and
2 and only queuing item 3; the skeptic would stop at item 1.

The original Option B text below is kept for the record.

### Original recommendation (superseded)

**Option B.** Of the five goals in problem.md it meets three outright (spend
reported at the cap, no file I/O in workflow code, notes correct), one in
part (counters stay readable after an interrupted write; over-charging on
refusal is deferred) and defers one (cap behaviour matching the contract).
The deferral is not avoidance: the size and even the shape of the cap-behaviour
fixes turn on experiment E1, and E1 is cheap.

Proposed follow-ups, each its own card, none in this batch:

1. **Cap behaviour (M, gated on E1)** — handle `UnexpectedModelBehavior` at
   the stage boundary, and fix run-counter compensation *before* any change
   that makes refusals repeatable.
2. **Carry partial work (L, needs a user ruling first)** — a behaviour change
   to briefs; may be declined.
3. **Architect research surface (M)** — configured run ceiling, request
   limit and uncaught limit error on the architect path, with 6.2 as its
   headline item. See the 6.2 ruling in decide.md.

## Experiments that gate the follow-ups (none run in this assessment)

| ID | Question | Shape | Gates |
|---|---|---|---|
| E1 | Under CodeMode, does a refused charge end in a concluded brief, `UnexpectedModelBehavior`, or `BudgetExceeded`? How many run-counter charges result? | scripted-model agent with CodeMode and a charging tool at cap 1, in the container | follow-up 1; size of the H4 leak |
| E2 | Does a caller-owned usage object hold the spend when the run aborts? | scripted-model run whose third tool call raises | the H1 fix itself — becomes its failing test |
| E3 | Failure shape of an unparsable budget file | write a truncated file, charge once | the H3 fix — becomes its failing test |
| E4 | Does the retain path run file reads in the sandbox, and does a replay without page files fail? | workflow test with a grounded brief and page file, then replay against an empty root | the H5 fix — becomes its regression test |

E2-E4 double as the repro-before-fix tests the brief requires; they belong
inside the batch. E1 is measurement only.

## Out of Scope (for the recommended option)

- Any change to what the model is told at a cap, or to brief content.
- Run-counter compensation (H4) and `UnexpectedModelBehavior` handling (N4).
- Spend lost on attempts that raise, and on `failed=True` findings.
- The architect path: N2, N3 and 6.2.
- Refine-after-degrade reusing sub-question ids (already a Gotcha; a sibling
  of the "retries inherit" trap, not one of the five).
- Cap values, attempt budgets, timeouts.
- Editing `docs/reports/external-ideas-2026-09.md`.

## Assumptions to Validate

- A caller-owned usage object holds the completed responses' spend on abort
  (advisor read the library code; E2 proves it).
- Removing the verifier call from the retain path schedules the same
  activities for every run that verified clean (argued from `step.py`; E4
  proves it).
- No replay fixture or golden trace depends on research-stage spend values
  for a capped run.
- Production research really runs with the exa provider and CodeMode (read in
  `agents/research/agent.yaml` and `agent.py`; not observed in a live run).
- The slice is unchanged since the Gotchas were written (confirmed by git log).
