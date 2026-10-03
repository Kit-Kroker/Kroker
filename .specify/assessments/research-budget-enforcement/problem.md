# Problem Definition: Research budget-enforcement defect cluster

- **Slug**: research-budget-enforcement
- **Created**: 2026-10-03
- **Inputs used**: intake.md, research.md
- **Baseline**: main `269fa29`

## Problem Statement

When a research run reaches one of its bounds, or is interrupted while
charging one, the research stage does not do what its own contract says:
model spend already incurred goes unrecorded, the work already gathered is
thrown away without the model being told to conclude, and the persisted
budget state can be left over-charged or unreadable. Separately, the retain
step reads page files from workflow code, so a clean run's replay depends on
the local disk.

Each of these is silent: the stage still records a normal-looking result.

## The problems, separated

The cluster is five symptoms of four distinct problems (evidence in
research.md):

| # | Problem | Hypotheses | Fires on |
|---|---|---|---|
| P1 | **Spend is lost at the cap.** A sub-question that hits a bound hands back zero usage, so the benchmark row under-reports. The architect's research sub-run never hands usage back at all (6.2). | H1, 6.2 | any cap hit; every architect research call |
| P2 | **A sub-question that ends in an exception loses all its work.** The contract says the model sees the refusal and concludes with what it has. In production (CodeMode) the model does see the refusal, but if it keeps failing the run ends in an exception the stage does not handle (`UnexpectedModelBehavior`, N4): six doomed retries, then a failed finding with no usage and no work. A request-limit hit ends the same way, as a gap-only brief. | H2, N4 | request limit; repeated refusals (unmeasured) |
| P3 | **Persisted budget state is fragile.** An interrupted write leaves an unreadable counter that disables the scope; a refused scope charge leaves the run counter over-charged; a lock timeout is not treated as exhaustion; the architect path ignores the configured run ceiling. | H3, H4, lock timeout, N2 | crash mid-write; scope refusal; lock contention |
| P4 | **Verifier I/O runs in workflow code.** Retention re-reads page files outside an activity, although the same check already ran in one. | H5 | every approved brief with grounded findings |
| P5 | **Local notes are wrong.** Two docstrings call the persisted counter future work; the Gotchas `scope == "run"` bullet describes a path the architect does not take. | stale docstrings, N1 | editing the slice |

## Affected Users & Stakeholders

- **Users**:
  - whoever reads benchmark and cost records — research spend is
    under-reported in exactly the runs that hit a cap (research.md H1);
  - the operator resuming or replaying a run — exposed to a wedged budget
    scope (H3) and to a replay that depends on page files (H5);
  - downstream stages and the human at the research gate — receive a
    gap-only brief where partial findings existed (H2);
  - editors of the research slice — misled by stale notes (P5).
- **Stakeholders**:
  - the user (roadmap owner) — decides go / kill at the USER GATE and whether
    D1 is re-ruled for 6.2;
  - the orchestrator — owns sequencing and any commit after the gate.

## Goals

- A sub-question that hits a bound reports the model spend it incurred.
- Hitting a bound produces the behaviour the contract documents, or the
  contract is changed to say what actually happens — one of the two, on
  purpose.
- An interrupted or refused budget charge leaves the persisted counters
  readable and correct.
- No file I/O in research workflow code.
- The slice's notes describe the code.

## Non-Goals

- Pricing LLM tokens against the research budget caps (the caps price tool
  calls from constants by design — research.md, Data & Constraints).
- Changing cap values, attempt budgets or timeouts.
- The other fail-and-continue Gotchas (shared `try` around fan-out and
  synthesis, `id_offset` reset after a degraded round, degraded brief
  recorded PASS, rejection recording no benchmark row). They are real, listed
  in `AGENTS.md`, and outside the five; folding them in would turn a defect
  batch into a redesign of the stage's degradation policy.
- Defect 6.3 (oversized prompt) — delivered separately as 007.
- Whether 6.2 is a goal is NOT settled here; it is an explicit ruling in the
  decide artifact.

## Success Metrics

- For each surviving defect, a regression test that fails on `269fa29` and
  passes after the fix (baseline: no such test exists for H1's lost spend,
  H3's unreadable file, H4's reverse direction, or H5 — research.md).
- Benchmark row for a run whose sub-question exhausts `max_requests` shows
  non-zero research tokens for that sub-question (baseline: zero).
- `grep` for file reads reachable from `step.py` outside an activity returns
  nothing (baseline: one path, via `retain.py`).
- Existing replay / golden-trace tests still pass unchanged for runs that do
  not hit a cap (qualitative until it is known which fixtures cover research
  — open question).

## Cost of Inaction

- Research cost in benchmark history stays understated for capped runs, and
  comparisons between models that cap at different rates stay skewed. The
  size of the skew is unknown — no run data was examined.
- A crash at the wrong instant disables research tools for the rest of that
  run until someone deletes a file by hand.
- A replay of a research run on a machine without its page files can fail as
  non-deterministic.
- None of this has been observed in a real run; all of it is read from code.
  Doing nothing is survivable. The documented Gotchas already warn editors.

## Open Questions

- [NEEDS CLARIFICATION: how often do real runs hit a research cap? Decides
  how much P1 and P2 matter in practice.]
- [NEEDS CLARIFICATION: for P2, is the intended behaviour "model concludes
  with what it has" (the written contract) or "abort to a gap" (the code)?
  This is a product choice, not something code reading can settle.]
- Resolved by experiment E1: a budget refusal under CodeMode reaches the
  model as a retry prompt. If the model concludes, the contract holds; if it
  retries, the run ends in an uncaught `UnexpectedModelBehavior` and every
  refused call over-charges the run counter (research.md, M2-M4).
- [NEEDS CLARIFICATION: how often does a real model retry rather than
  conclude? Not measurable with fakes.]
- Resolved by the advisor from library code (read, not run): the spend can be
  recovered at the cap with a caller-owned `RunUsage`.
- [NEEDS CLARIFICATION: do replay fixtures cover a research stage with
  grounded findings? Decides how P4 is verified.]
- [NEEDS CLARIFICATION: is D1 (6.2 out of scope) to be re-ruled?]
