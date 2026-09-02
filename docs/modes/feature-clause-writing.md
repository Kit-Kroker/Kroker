# Feature Clause Writing Guide

This guide establishes the methodology for authoring numbered behavioral
clauses in `<stage>.md` contracts when extracting or migrating a stage.

## The Clause ID Scheme

Clauses are identified as `<STAGE>-N` (for top-level requirements) and
`<STAGE>-N.M` (for sub-clauses narrowing the parent: an edge case, a failure
mode, or a state transition the parent implies but does not pin down).

Each clause is anchored to an existing identifier from the repo's established
namespaces:
- `[FR-xxx]` (functional requirements from `PRD.md` or `ROADMAP.md`)
- `[NFR-x]` (non-functional requirements)
- `[E-xx]` (epic numbers from `ROADMAP.md`)

**`ADR-xx` is not an anchor.** An Architectural Decision Record records a
decision and its rationale, not a product requirement. A clause citing an ADR
describes rationale rather than obligation.

### Why anchor to existing IDs?
The `FR-xxx`, `NFR-x`, and `E-xx` identifiers already span `PRD.md`,
`ROADMAP.md`, and `ARCHITECTURE.md`. An unanchored local namespace would create
a shadow taxonomy competing with the repo-wide requirements.

### Why local clauses at all?
An `FR` is too coarse to describe the atomic state transitions and specific
contract boundaries that automated tests need to cite. Numbered clauses provide
the fine-grained specification that maps directly to unit tests.

## How to write a clause

A well-formed clause satisfies four properties:
1. **Property of behaviour, not implementation:** It specifies what the stage
   observably guarantees to the pipeline, not the private internal functions,
   temporary variables, or private helper call sequences used to produce it.
2. **One obligation per clause:** Each clause carries exactly one obligation. If
   a requirement needs "and", it is two clauses.
3. **Present tense and stage as subject:** The subject of every clause is the
   stage (or its output artifact), never the developer or the author.
4. **Descriptive, never aspirational:** Write what the code does today on `main`.
   If existing code has a bug or limitation, document the observed behavior, file
   an issue/FR, and update the clause in the same PR that fixes the bug. Never
   write the fix into the contract first.

## Worked examples: good vs bad

### Bad:
> `CLARIFY-1. The clarify stage should handle open questions properly.`

*Why it fails:* "Should" is aspirational; "properly" is subjective and
untestable; there is no anchor; and it describes developer intention rather
than observable stage behavior.

### Good:
> `CLARIFY-1. Every open question the clarifier emits is either answered by a human or falls back to its suggested answer before the stage returns. [FR-xxx]`

*Why it succeeds:* Anchored to an existing requirement; states an observable,
invariant property; unambiguous outcome; completely testable.

## Pytest linkage note

Whether `pytest` gains a clause-citing test marker (e.g. `@pytest.mark.clause("CLARIFY-1.1")`)
is explicitly deferred to spec A, where a real migrated slice exists to try it
on.
