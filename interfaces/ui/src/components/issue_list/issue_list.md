# Issue List Component

Lists validation issues for a draft graph. The caller owns where issues come
from (the backend validator, never TypeScript), their order, and how an issue
maps onto a canvas element; the component owns the list and focus requests.

## Requirements

### ISSUE_LIST-1
An Issue List renders one row per supplied issue, in supplied order, each
carrying its severity as a stable class `cmp-issue-<severity>`; an empty list
renders "no issues". Severities are the validator's -- `error`, `warning`,
`not_executable` (E-75 design §7.3) -- each with its own class; the component
never reclassifies. [FR-1205]

### ISSUE_LIST-2
An issue with a `focusKey` offers its target as a control that emits
`focus` with that key; a graph-level issue (`focusKey: null`) offers none.
[FR-1205]

## Failure modes

Severity and wording are the validator's; the component never reclassifies.
