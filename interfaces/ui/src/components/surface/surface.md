# Surface Component

Renders a raised panel: a card when `flat`, a popover, menu, tooltip, decision
card or command palette when `overlay`. The caller owns placement (absolute,
anchored, centred) and content; the component owns ground, line, radius and
shadow, so every floating thing in the console looks like one family.

## Requirements

### SURFACE-1
A Surface carries its elevation as a stable class, `cmp-surface-flat` or
`cmp-surface-overlay`; only `overlay` casts `--shadow-overlay`. [FR-1400]

### SURFACE-2
A Surface renders as the element named by `as` (default `div`), so a menu
can be a `ul` and a card an `article` without a wrapper. [FR-1400]

### SURFACE-3
A Surface carries its padding step as `cmp-surface-pad-<none|sm|md>`; menus
use `sm` so their rows reach the edge. [FR-1400]

## Failure modes

Placement is caller-owned: an overlay Surface with no positioning renders in
flow, which is what the showcase shows.
