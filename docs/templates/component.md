# <Component Name> Component

One paragraph: what this component renders, what inputs (props) it receives,
and how it fits into the console or design system. Components must never
import domain types or perform I/O.

What the caller owns versus what this component owns. Be specific -- the
caller owns domain data mapping, order, and labels; the component owns
markups, styling classes, slots, and presentation behaviour.

> **Note on Clause Identifiers:** Clause prefixes must match the component's
> snake_case directory name converted to uppercase, using underscores only
> (`<COMPONENT_NAME>-N`), never hyphens. `scripts/check_clauses.py` requires
> underscores to parse headings.

## Requirements

### <COMPONENT_NAME>-1
A requirement, stated as a property of the component's markup or visual
behaviour in one sentence. [FR-xxxx]

### <COMPONENT_NAME>-1.1
A sub-clause narrowing the parent: an edge case (e.g. empty list), a failure
mode, or a boundary state. [FR-xxxx]

### <COMPONENT_NAME>-2
Each mark or visual state carries a stable class, `cmp-<component>-<state>`,
independent of token colours or resolved styles. [FR-xxxx]

### <COMPONENT_NAME>-3
Accessible attributes, titles, or keyboard navigation properties ensuring
usable presentation without reliance on color vision alone. [NFR-x]

## Failure modes

What this component does when its props are missing, empty, or invalid.
Invalid states should throw at render time rather than silently falling back
to misleading defaults. Each failure mode is anchored to the clause that
governs it.
