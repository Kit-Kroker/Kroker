# Rail Component

The v5 run rail: the run-block head (title, state, fact rows, budget),
call-to-action buttons, segmented section tabs and one section slot per
tab. The caller owns the run, the active section and every consequence
of a click; the rail renders and reports.

## Requirements

### RAIL-1
The head renders the title, the state, one row per `{k, v}` fact, and
the budget: the spent figure and the note always; the progress bar only
when `limit` is a number — `limit: null` renders "off" and no bar
(a numeric limit, including 0, is not "off"). [FR-1205]

### RAIL-2
Exactly the active tab's section slot renders; an active id matching no
tab renders no section. A tab click emits `select(id)` — the caller owns
which section is active. [FR-1205]

### RAIL-3
Each `calls` entry renders as a call-to-action button, in order; a click
emits `call(index)` with the entry's index. A tab click never emits
`call`; a call click never emits `select`. [FR-1205]

## Failure modes

An empty rows array renders an empty rows block (the caller styles
emptiness). An empty calls array renders no buttons and no empty
control.
