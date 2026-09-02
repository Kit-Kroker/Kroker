# Lesson-to-Skill Guide

The discipline of transforming engineering mistakes into durable mechanisms that
prevent recurrence.

## The Improvement Loop

The feedback cycle runs:

    Task → Failure → Reflection → Lesson → Durable Artifact → Future Runs

A lesson that remains in an LLM chat transcript or personal note evaporates the
moment the session ends. A lesson that becomes a durable, executable artifact
(a test, a linter, or a pre-commit hook) protects the repository forever without
requiring future contributors or agents to remember it.

## The Four Levels of Enforcement (Ascending Strength)

When encoding a lesson, always choose the strongest level that fits the problem:

1. **Level 1: Prose in an `AGENTS.md` file.**
   *Weakest.* Relies on the agent finding, reading, and attending to the text
   amidst full context.
2. **Level 2: A documented rule in `docs/documentation-rules.md` or `docs/modes/`.**
   Reviewable during pull requests, but still advisory at commit time.
3. **Level 3: An automated regression test.**
   Executable and deterministic. The bug cannot silently recur in CI without
   breaking the build.
4. **Level 4: A pre-commit hook or verification gate in `scripts/verify.py`.**
   *Strongest.* The violation cannot even be committed to git.

### The Bar for Promotion
If a mistake occurs once, a Level 1 or 2 rule may suffice.
**If a mistake costs time twice, it must be promoted to Level 3 or Level 4.**
Restating an advisory rule that already existed and was ignored is not learning a
lesson; it is ignoring evidence that the enforcement mechanism was too weak.

## Worked Examples from This Repo's History

Two real examples illustrate the necessity of mechanical enforcement:

1. **`_escalation_round` Concurrency Defect (Level 2 failed → Needs Level 3):**
   `src/sdlc/workflows/gates.py:84-88` explicitly documented the danger of
   storing gate confidence on workflow instance attributes due to concurrent
   execution and interleaving. Despite this Level 2 prose rule, `_escalation_round`
   was subsequently added to `FeatureWorkflow` as instance state (`feature.py:865`,
   `:2025`), creating an identical concurrency hazard. A prose warning failed to
   prevent an identical architectural defect.
2. **The File-Size Ceiling (Level 1 failed → Solved by Level 4):**
   For months, "keep files modular and small" was oral tradition and prose
   guidance. Files quietly swelled past 1500 and 3500 lines. The issue was only
   solved when `scripts/check_file_size.py` established a strict 1000-line ceiling
   enforced by pre-commit and CI at Level 4.

## Scope Boundary

This guide applies strictly to **developing this repository**.
Lessons about how the Kroker pipeline behaves for end users on target repositories
belong in product documentation, user evals, and runtime telemetry, never in this
development harness guide.
