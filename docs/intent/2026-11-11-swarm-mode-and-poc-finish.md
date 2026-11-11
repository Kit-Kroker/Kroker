# Intent — swarm mode and the PoC finish line

| | |
|---|---|
| Date | 2026-11-11 |
| Status | Confirmed by the owner in an interview session (explicit "yes" to the restate below) |
| Kind | Dated snapshot of intent. Not a spec, not a plan; those are downstream |
| Source | Architecture and roadmap review session, 2026-11-11 |

This records what the owner wants next, in the owner's terms. It does not
change `PRD.md`, `ARCHITECTURE.md`, `ROADMAP.md` or any ADR. Where it
disagrees with them, the disagreement is listed under "Conflicts with
current documents" and is still to be resolved.

## Confirmed intent

- **Outcome.** A general software factory for developing and supporting
  different kinds of software, where goal-driven agents working from a
  shared board are the default mode and the SDLC chain is one process
  inside it.
- **User.** The owner, for now. This is a PoC with no external consumer and
  no deadline.
- **Why now.** The chain PoC exists and the benchmark track is parked. The
  owner believes a swarm does research and fixes more effectively than a
  fixed stage order.
- **Success.**
  1. Swarm mode exists and is benchmarked against the chain on the same
     commit and the same cases.
  2. After that, the platform shell: multi-tenancy, an MCP surface, and
     interfaces per role.
- **Constraint.** One person. z.ai subscription models only; no Anthropic
  subscription arm. Paid runs only on the owner's word.
- **Trust layer.** Unchanged in principle: deterministic checks decide, and
  a human decides risky things. Both modes use the same layer.
- **Out of scope for now.** Tier 2 audit depth (E-50…E-56), the
  product-outcome loop (P8), the maintenance loop as designed (P4), further
  canvas work, and re-selecting model arms.

## What "second mode" means

The owner pointed at a description of three levels of organising agent work
in a company (<https://t.me/llm_under_hood/989>): personal assistants with
memory; agents handing tasks to each other through a shared tracker while
people watch; one integrated system with unified access and change control
where some processes run autonomously. The second mode is the second level
moving toward the third. It sits beside the pipeline as its own mode; it is
not a node type inside the pipeline graph.

## Condition on the benchmark comparison

The owner will run the benchmark once the swarm exists. For that comparison
to mean anything:

- Both arms (chain and swarm) run on one commit. The stored chain scores
  cannot serve as the baseline, by the same reasoning as the re-prove
  series (a cross-commit comparison also measures pipeline drift).
- About 6 to 7 runs per arm, with failed runs scored separately. The
  arm-reselection diagnosis found the n=3 rule cannot resolve a 0.15 margin
  at the measured spread
  (`.specify/assessments/arm-reselection-round/decision.md`).
- The comparison is topology against topology on one model, so it needs no
  second provider and is not blocked by the hold on arm re-selection.

## Proposed in the session, not explicitly accepted

The reviewer proposed three plan items alongside the restate. The owner's
"yes" answered the restate and did not address these one by one, so they
are open:

1. Fix the judge before the comparison. Reviewer and `dev` run the same
   model today (AP-1.0); a swarm judged by that reviewer inherits the hole.
2. Multi-tenancy last, after the benchmark result. It is the largest item
   and says nothing about whether the factory works.
3. Amend ADR-22, which currently excludes coordinator and swarm.

## Conflicts with current documents

- **ADR-22** (2026-10-11) excludes coordinator and swarm. This intent
  reverses that.
- **`ROADMAP.md` §8** ranks AP-0/AP-1 as the top open increment. This
  intent puts swarm mode first; AP-0's chain baseline is absorbed into the
  same-commit comparison.
- **`docs/roadmap/ordering.md`** makes E-57/E-58 conditional on an external
  tenant being near. This intent puts multi-tenancy inside the PoC finish
  line with no tenant named.
- **PRD phases P4–P8** are not ordered the way this intent orders the work.

## Open questions

- What does a swarm agent do when the deterministic checks cannot decide:
  stop, or raise a gate?
- Which actions count as risky enough for a human, and where is that
  enforced on a harness with no hook layer (opencode today)?
- Is the agent board (E-78) the coordination surface for the second mode,
  or a new one?
- Does the PoC count as proven on the platform shell alone, or does the
  swarm have to match or beat the chain on the comparison first? The owner
  did not answer this directly.
