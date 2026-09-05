# Fleet Table Component

Renders a table panel of fleet runs, with column headers and one row per run.
The caller owns fetching, filtering, and adapting runs into row props;
the component owns the table header markup, row container layout, and empty state display.

## Requirements

### FLEET_TABLE-1
A Fleet Table renders exactly one row per supplied run, in supplied order. [FR-1400]

### FLEET_TABLE-1.1
An empty fleet renders the table header and an explicit empty state, not a bare header. [FR-1400]

## Failure modes

Passing an empty rows array renders the explicit empty state message rather than failing.
An undefined rows prop defaults to an empty list.
