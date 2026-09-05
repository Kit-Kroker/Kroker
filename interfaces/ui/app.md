# The assembled console

Every component contract in this tree covers one component in isolation,
rendered from a profile in the showcase. This one covers the console that
actually ships: the dashboard SPA assembled from the library and the
dashboard's own adapters and stores, running on a provider. It exists
because a net stretched only over the showcase misses the pages that ship
(spec C, §6).

## Requirements

### CONSOLE-1
The fleet view renders one row per run reported by the active provider;
while the provider reports runs, the empty state never shows. Asserted
against the mock provider on a built SPA. [FR-601]

### CONSOLE-2
The header renders the live run counter and spend stats from provider
state, and the inbox badge appears when the provider reports inbox items.
[FR-601]

## Failure modes

Both clauses are asserted by `app.pw.ts` against the built dashboard on
`VITE_API=mock` (the mock is what makes the whole SPA runnable headless
with no backend). A failure here is usually not a component fault but an
assembly fault: an adapter mapping, a store refresh, or the provider
selection in `dashboard/frontend/src/api/client.ts`.
