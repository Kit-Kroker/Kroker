# Catalog Card Component

The Graphs catalog card (S8, FR-044): kicker, name, sha, description,
when-used, count chips and the single action. Presentational — the
Graphs view maps the shipped-graphs read to these props and turns `act`
into navigation.

## Requirements

### CATALOG_CARD-1
The card renders the kicker, the name, the sha in mono, the description
and the when line. A null description or when renders `not measured`,
never the string `null` or `undefined`. [FR-044]

### CATALOG_CARD-2
The card renders one count chip per `{label, n}` entry with its label
and number; zero renders as 0 — a real count, never hidden. [FR-044]

### CATALOG_CARD-3
The action renders its label as a button; a click emits `act` (the
parent decides what the act means). [FR-044]

## Failure modes

The card never invents a description, a date or a count; everything
visible comes from the props.
