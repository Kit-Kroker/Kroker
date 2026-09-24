# List Row Component

Renders one selectable row of a list that drives a detail pane: a board task,
an artifact version, an event, an inbox decision, an execution step. The
caller owns the row's content (through slots) and which row is selected; the
component owns hover, selected and focus treatment and the leading/main/meta
layout.

## Requirements

### LIST_ROW-1
A selected row carries `is-selected` and `aria-current="true"`; an unselected
row carries no `aria-current`. [FR-1400]

### LIST_ROW-2
Pressing an enabled row emits `select`; a disabled row emits nothing. [FR-1400]

### LIST_ROW-3
A row is a native `button`, so a list of rows is reachable and operable from
the keyboard with no extra handling. [FR-1400]

### LIST_ROW-4
The `leading` and `meta` slots render only when supplied; the main slot
truncates rather than wrapping the meta off the row. [FR-1400]

## Failure modes

Selection is caller-owned; pressing a row never marks itself selected.
