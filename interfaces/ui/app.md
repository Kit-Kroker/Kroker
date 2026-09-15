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

### CONSOLE-3
The fleet strip renders one mark per canonical stage the provider's catalog
serves (18 today), keyed by name. [FR-1205, E-76 U4]

### CONSOLE-7
The graph editor renders the canvas after applying well-shaped recorded text,
and keeps the canvas disabled while showing shape errors after applying text
that does not parse. [FR-1205, E-76 U5]

### CONSOLE-9
In the graph editor, editing one inspector field of a recorded graph and
applying it round-trips through the provider's parse and commits: the
working copy gains the parse's sha and the inspector shows no error. [FR-1205,
E-76 U8]

## Failure modes

Both clauses are asserted by `app.pw.ts` against the built dashboard on
`VITE_API=mock` (the mock is what makes the whole SPA runnable headless
with no backend). A failure here is usually not a component fault but an
assembly fault: an adapter mapping, a store refresh, or the provider
selection in `dashboard/frontend/src/api/client.ts`.
