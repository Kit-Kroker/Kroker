# Status Pip Component

Renders a compact colored pip representing a run or task lifecycle status.
The caller owns status mapping and selection of status kind; the component
owns the visual representation, sizing, styling classes, and pulsing animations.

## Requirements

### STATUS_PIP-1
A Status Pip renders a mark carrying its status kind as a stable class,
`cmp-status-pip-<kind>`, independent of the token color that class resolves to. [FR-1404]

### STATUS_PIP-2
The `running` and `blocked` states are the only marks that pulse when active. [FR-1404]

## Failure modes

An unknown status kind falls back to an unstyled mark or caller error; the component
accepts any kind string and emits `cmp-status-pip-<kind>`.
