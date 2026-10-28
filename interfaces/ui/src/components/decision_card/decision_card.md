# Decision Card Component

The v5 card shell for every decision kind (R-3): kicker and schema chip,
title, where, fact fields, an optional text area, actions whose
consequences render as visible text before the click, and a foot.
Presentational — the caller maps the item to props and turns `act` into
exactly one client call.

## Requirements

### DECISION_CARD-1
The card renders the kicker, the schema chip, the title, the where line,
one row per `{k, v}` field (the mono flag styles the value), and the
foot. Empty fields render no rows; an empty foot renders empty, never a
placeholder. [FR-601]

### DECISION_CARD-2
The text area renders only when `text` is given — labelled by its label,
hinted by its placeholder, carrying the initial value. Without `text`
there is no text area at all. [FR-601]

### DECISION_CARD-3
Each action renders its label as a button and its consequence title as
VISIBLE text beside it, before any click — a decision is taken with its
consequence in view, never from a tooltip alone. An action with
`needsText` is disabled while the current text is blank (a non-empty
initial value enables it at once; clearing disables it again). [FR-601]

### DECISION_CARD-4
`busy` disables every action, including actions whose text requirement
is already satisfied. [FR-302]

### DECISION_CARD-5
A click on an enabled action emits `act(id, text)` with the action id
and the current text (the empty string without a text block). Repeated
clicks emit repeatedly — de-duplication is the caller's busy-gating.
[FR-301]

### DECISION_CARD-6
A disabled action — gated or busy — emits nothing on click. An action
with `needsText` but no `text` block stays permanently disabled.
[FR-301]

## Failure modes

The card never invents a default action, a default text or a consequence
string; everything visible comes from the props.
