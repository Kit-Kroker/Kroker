# Focused Design Specs Guide

Conventions for authoring architectural design specifications under
`docs/superpowers/specs/`, harvested from established practice across the
existing specs in that directory.

`docs/superpowers/specs/2026-09-01-e50-assessment-gate-checks-design.md` is the
canonical model.

## The Metadata Block

Every spec opens with a standard metadata block:

```markdown
# [Title]

- **Date:** YYYY-MM-DD
- **Status:** Draft | Approved | Merged
- **Scope:** [One sentence summarizing the architectural scope]
- **Satisfies:** [FR-xxx, E-xx, or issue reference]
- **Baseline:** [Git commit SHA against which the spec was drafted]
- **Does not cover:** [Explicit list of out-of-scope concerns]
```

### `Does not cover` is not optional
A specification that does not explicitly state what it excludes will be read as
promising to solve it. Out-of-scope boundaries prevent sprawl and scope creep.

## Problem before Decision

Structure the document so that the **Problem** section strictly precedes the
**Decision** section:
- The Problem statement establishes what is broken, inefficient, or ambiguous
  today.
- It must present concrete evidence, citing file locations and system behavior.
- The Decision then presents the solution directly addressing that evidence.

## Anchoring: claims must be checkable

Anchor all claims to `file:line`. A specification that asserts existing system
behavior without a line-number anchor is asserting a memory rather than an
inspected fact.

## Rejected alternatives are mandatory

An architectural document that does not say what was considered and discarded has
not made a decision; it has made a suggestion. Explain the alternatives
considered, why they were attractive, and the specific failure modes that ruled
them out.

## Specs are write-once after they land

Design specifications are **write-once**:
- They record the state of thinking and the codebase at the time of the decision.
- Once merged, they are never updated or retrofitted when subsequent work alters
  the code.
- Superseding work produces a **new specification** that cites the previous spec;
  the historical document remains untouched.
