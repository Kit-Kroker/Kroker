# Tab Bar Component

Renders the second-level navigation inside a run: Graph, Board, Gates, Cost.
The caller owns which tabs exist, which is active and what selecting one does
(usually a route change); the component owns the underline, the waiting badge
and tab semantics.

Top-level navigation stays in App Header. Switching the view of one thing is a
Segmented Control.

## Requirements

### TAB_BAR-1
The active tab carries the stable class `tab-active` and `aria-selected="true"`;
every other tab carries `aria-selected="false"`. [FR-1404]

### TAB_BAR-2
Pressing an inactive, enabled tab emits `select` with its id; pressing the
active or a disabled tab emits nothing. [FR-1400]

### TAB_BAR-3
A tab's count badge renders only for a count above zero, never as "0"
(the same rule as APP_HEADER-1.1): the badge means something is waiting. [FR-1400]

## Failure modes

An `active` matching no tab renders every tab inactive.
