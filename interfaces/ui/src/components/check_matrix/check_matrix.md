# Check Matrix Component

The Interfaces screen's matrix (S12, FR-050/FR-051): harnesses by
column, cell marks by state, the planned row dimmed, facts with
severity. Presentational - the interfaces read maps into these display
shapes.

## Requirements

### CHECK_MATRIX-1
One header per column, showing the column's name and its ref; an empty
matrix renders its headers and nothing else, without throwing.
[FR-050]

### CHECK_MATRIX-2
One row per harness (harness and sub) and one cell per column.
[FR-050]

### CHECK_MATRIX-3
Each cell carries its state as a stable mark (`data-state`: yes, no,
partial, not_measured, planned) and shows its text where it has one.
[FR-050]

### CHECK_MATRIX-4
The planned row carries the dimmed treatment; measured rows do not.
[FR-050]

### CHECK_MATRIX-5
Each fact renders with its severity distinguishable (`data-severity`:
warn, error) and its who and text. [FR-051]

## Failure modes

The matrix never invents a mark, a row or a fact; everything visible
comes from the props. Marks ride the status tokens, never a literal
colour (TOKENS-2).
