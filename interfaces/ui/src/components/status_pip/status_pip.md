# Status Pip Component

Renders a compact mark representing a run, stage or task lifecycle status.
The caller owns status mapping and selection of status kind; the component
owns the visual representation, sizing, styling classes, and pulsing animations.

Kinds: `running`/`in_progress`, `blocked`/`waiting`, `failed`, `done`,
`pending`, `quarantined`, `idle`/`skipped` — the union of run status and
the board's `TaskStatus`.

## Requirements

### STATUS_PIP-1
A Status Pip renders a mark carrying its status kind as a stable class,
`cmp-status-pip-<kind>`, independent of the token color that class resolves to. [FR-1404]

### STATUS_PIP-2
The `running` and `blocked` states are the only marks that pulse when active. [FR-1404]

### STATUS_PIP-3
`pending` and `quarantined` render hollow (a ring, no fill), so the two
states that mean "nothing is happening" read apart from every filled state
without a sixth colour. [FR-1404]

## Failure modes

An unknown status kind falls back to an unstyled mark or caller error; the component
accepts any kind string and emits `cmp-status-pip-<kind>`.
