# Status Tag Component

Renders a status as a pip plus a word on its tint: the chip in a run header,
a task's status in the detail pane, "WAITING · gate" on a node. The caller
owns the status kind and, optionally, the words; the component owns the pip,
the tint, and the default wording.

Use Status Pip alone in dense rows where the column already says what it is;
use Status Tag where the status has to read on its own.

## Requirements

### STATUS_TAG-1
A Status Tag renders a Status Pip of the same kind and carries
`cmp-status-tag-<kind>`, whose tint and ink come from the kind's status tokens. [FR-1404]

### STATUS_TAG-2
Without a `label`, the tag reads the kind with underscores as spaces and the
first letter capitalised (`in_progress` → "In progress"). [FR-1400]

### STATUS_TAG-3
`mono` renders the label in the mono family, uppercase, for tags that sit
among identifiers on a canvas node. [FR-1400]

## Failure modes

An unknown kind renders the idle tint and secondary ink, and its pip carries
the unknown class (STATUS_PIP-1).
