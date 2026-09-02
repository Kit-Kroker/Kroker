# Instructions for docs/features/

Rules and conventions for authoring and maintaining narrative cross-DAG feature
documents under `docs/features/`.

## Narrative Across the DAG

An area document in this directory (e.g. `docs/features/brownfield.md`) is a
**narrative companion across the DAG** explaining how several stages compose to
serve an end-to-end outcome.

It is not a per-stage contract. Contractual stage behavior belongs exclusively in
each vertical slice's contract file: `src/sdlc/stages/<stage>/<stage>.md`.
Duplicating clauses or specifications here creates two documents that will drift.

## Links Down, Never Restates

An area document links down to slice contracts and never restates their clauses:
- When describing stage contributions, cite the stage contract directly:
  `[CLARIFY-1.1](../../src/sdlc/stages/clarify/clarify.md)`.
- Use narrative prose to explain data flow, cross-stage coordination, and user
  outcomes.

## Tracks main Only

Like `ARCHITECTURE.md` and `ROADMAP.md`, feature documents reflect only what has
actually landed and is operational on `main`.

In-flight features and planned future capabilities live in their design
specifications under `docs/superpowers/specs/` until their code has merged.

## Who May Edit

**Orchestrator agents only.**
Files in `docs/features/` may only be modified by orchestrator agents working in
the primary repository checkout.

Sandboxed coding harnesses (`claude -p`, `opencode run`) operating inside
per-task git worktrees may not edit documents in this directory. This enforces the
sandbox boundary defined in the root [`AGENTS.md`](../../AGENTS.md): a harness
may modify only code and tests, never architecture or living specifications.
