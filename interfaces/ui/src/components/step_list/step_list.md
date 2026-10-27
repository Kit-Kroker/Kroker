# Step List Component

The read-only inner-loop list: one row per step with a status pip, the
step's name, its ref and its meta line. No control of any kind — the
inspector that hosts it owns everything interactive.

## Requirements

### STEP_LIST-1
One row per supplied step, in order, showing the step's name and ref,
and a pip whose class carries the step's status string (every
`CanvasStatus` value). [FR-1205]

### STEP_LIST-2
No row contains any interactive control — no button, link, input,
select or textarea. An empty steps array renders no rows; emptiness is
the caller's to style. [FR-1205]

## Failure modes

A step with empty meta renders its row with name and ref and no
placeholder text — never "undefined" or "null".
