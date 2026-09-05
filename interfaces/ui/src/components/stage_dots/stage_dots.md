# Stage Dots Component

Renders one mark per pipeline stage, in supplied order, showing how far a
run has progressed. The caller owns stage identity, stage order, and the
resolution of a run's position into per-stage states; the component owns
the mark vocabulary and its visual behaviour.

## Requirements

### STAGE_DOTS-1
A Stage Dots renders exactly one mark per supplied stage, in supplied
order. [FR-1400]

### STAGE_DOTS-1.1
An empty stage list renders no marks and is not an error: a run whose
pipeline is not yet resolved has nothing to show. [FR-1400]

### STAGE_DOTS-1.2
An unknown state fails rendering rather than falling back to a default.
A silently-wrong progress mark is worse than a visible failure. [FR-1401]

### STAGE_DOTS-2
Each mark carries its state as a stable class, `cmp-stage-dot-<state>`,
independent of the colour that class resolves to. [FR-1404]

### STAGE_DOTS-3
The `active` and `blocked` states are the only animated marks. [FR-1403]

### STAGE_DOTS-4
Each mark exposes its stage name and state as an accessible title, so a
mark is identifiable without colour vision. [NFR-4]

## Failure modes

An unknown state raises at render time (STAGE_DOTS-1.2). A missing
`dots` prop is a caller error and renders nothing (STAGE_DOTS-1.1).
