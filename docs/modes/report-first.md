# Report-First Engineering Guide

The methodology for brownfield archaeology and high-risk refactoring on
unfamiliar or heavily-coupled code.

## The Rule: Diagnostic Artifact First, Zero Code Edits

When beginning work on unfamiliar, complex, or heavily-coupled subsystems, the
first task produces a **diagnostic artifact and no code changes at all**.

The ban on code edits during archaeology is the core mechanism, not an arbitrary
formality. An agent or developer permitted to "just fix this one quick thing"
while mapping complex code immediately stops mapping and becomes entangled in
premature implementation.

## Why: Catching Misunderstandings Early

1. **Cheap corrections:** A reviewer can inspect a two-page diagnostic report and
   say *"Your model of how this subsystem works is wrong"* in five minutes, before
   a single line of production code moves. The same correction after a large
   refactor costs the entire refactor.
2. **Explicit beliefs:** An agent or engineer that has committed its mental model
   to a written report can be tested, critiqued, and contradicted. One that has
   only read code cannot.

## Contents of an Archaeology Report

An archaeology report includes:
- **Entry points:** Where control flow enters the subsystem.
- **Structural map:** Component hierarchy and boundaries.
- **Coupling audit:** What the subsystem reaches for, and what reaches for it.
- **Data flows:** How inputs, state mutations, and outputs traverse the code.
- **Undocumented load-bearing behavior:** Quirks, edge cases, and implicit
  invariants discovered in the code.
- **Missing tests:** Gaps where existing behavior lacks regression protection.
- **Checkable hypotheses:** An explicit list of hypotheses about system invariants,
  each phrased so it can be proven or disproven by inspection or test.

## Where Reports Live: `docs/reports/`

Diagnostic archaeology reports are authored in **`docs/reports/`** using the
naming convention `<YYYY-MM-DD>-<topic>.md`.

- `docs/reports/` is explicitly designated for dated one-off diagnostic snapshots
  that are true when written and never updated.
- **Do not use `records/`:** `records/` is reserved for verbatim vendor/design
  exports and is exempt from the file-size ceiling on rationale that does not
  apply to authored engineering artifacts.
- **Do not use `.workspace/`:** `.workspace/` is gitignored, meaning the artifact
  could never be reviewed in a pull request diff, cited in commit messages, or
  referenced by future agents.

## Worked Example: Spec A's Opening Task

Spec A begins with a report-first archaeology task before modifying workflow
code: producing `docs/reports/<date>-feature-py-archaeology.md`.

For each of the 15 stages in `FeatureWorkflow._pipeline`, the report catalogs:
1. Stage line range in `src/sdlc/workflows/feature.py`.
2. Every `self._x` attribute or method the stage touches.
3. Which of `StageContext`'s eleven services each access maps to.
4. What capabilities the stage touches that no `StageContext` service covers.
5. All enumeration-identity (`is`) comparison sites in the stage's body.
6. Any child workflows started by the stage.

This audit table **is** the migration sequence: stages with minimal unmapped
dependencies become the immediate successors to the pilots, making subsequent
slice migrations predictable and mechanical.

## When Report-First Does Not Apply

A localized change or bug fix inside code the author already understands does
not need an archaeology report. Report-first is a disciplined tool for
unfamiliar ground and architectural transitions, not a ceremony for every diff.
