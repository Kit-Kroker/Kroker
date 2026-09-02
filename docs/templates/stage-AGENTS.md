# AGENTS.md — <stage>

Local rules for editing this slice. Repo-wide rules are in the root
[`AGENTS.md`](../../../../AGENTS.md); the seam contract and the Temporal
rules are in [`docs/framework.md`](../../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

What must not change without changing `<stage>.md` first. What this slice
owns and what it must never reach for.

## Temporal notes for this slice

Which of `framework.md`'s four rules bite here, and where. Name the
specific imports that must be passed through and why -- model modules for
enum identity, the agent registry for import-time construction, any child
workflow class this stage starts. If none of them bite, say so; an empty
section is information.

## State

Which values arrive as parameters and which come from `StageContext`.
Any per-loop counter this slice keeps, and where it lives (never on the
workflow instance -- see `gates.py:84-88` for why).

## Activities

The `@activity.defn` functions this slice owns, and confirmation that all
of them are listed in `ACTIVITIES`.

## Tests

    pytest tests/<stage>/ -q

Anything a test here needs that is not obvious: fixtures, markers, why a
test is in `tests/integration/` instead.
