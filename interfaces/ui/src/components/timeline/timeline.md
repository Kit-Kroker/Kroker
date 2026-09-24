# Timeline Component

Renders a vertical history of status moves: a task's transitions, an event
trail, a run's gate decisions. Each entry is a mark, a "from → to" line, an
optional detail, and a time plus actor. The caller owns ordering (newest first
on the board) and wording; the component owns the rail and the hierarchy.

## Requirements

### TIMELINE-1
A Timeline renders one entry per item, in supplied order; it never sorts. [FR-1400]

### TIMELINE-2
Each entry's mark is a Status Pip of `kind`, or of `to` when `kind` is absent. [FR-1400]

### TIMELINE-3
`from` and `detail` render only when supplied; an entry with no `from` reads
as its `to` alone (a creation). [FR-1400]

### TIMELINE-4
With no items the list is absent and the `empty` slot renders instead. [FR-1400]

## Failure modes

A `to` that is not a status kind (e.g. "approved") renders an unstyled mark
unless the caller passes `kind`.
