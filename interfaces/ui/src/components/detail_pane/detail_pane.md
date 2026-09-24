# Detail Pane Component

Renders the right-hand pane of a list/detail view: an eyebrow line (identifier
plus badges), a title, a key/value grid, then sections. Detail Section is its
sibling: an uppercase section label with an optional action, over any content
(evidence, history, merge checks, a form). The caller owns every value; the
components own the hierarchy and the grid.

## Requirements

### DETAIL_PANE-1
A Detail Pane renders one `dt`/`dd` pair per field, in supplied order; values
render in the mono family unless the field sets `mono: false`. [FR-1400]

### DETAIL_PANE-2
A field whose value is `null`, `undefined` or empty renders an em dash,
never an empty cell. [FR-1400]

### DETAIL_PANE-3
The title is the pane's `h2` and each Detail Section label is an `h3`, so the
pane reads as an outline. [FR-1400]

### DETAIL_PANE-4
With no fields the grid is absent, not an empty `dl`. [FR-1400]

## Failure modes

Long identifiers (run ids, sha256) wrap anywhere inside their cell rather than
widening the pane.
