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

### CONSOLE-4
The run view of a graph-executed run renders one canvas node per graph node,
a loop-edge counter as `used/max`, and its backward edge curved. [FR-1205]

### CONSOLE-5
Deciding a pending gate from the run view's canvas clears that gate's
controls once the provider's next run state no longer lists it. [FR-1205,
FR-301/302]

### CONSOLE-6
The run view of a run that predates graph execution shows the no-graph empty
state and still renders the stage strip. [FR-1205, E-76 U7]

### CONSOLE-8
The run view offers no edit affordance; its "open copy in editor" link lands
on the graph editor holding the run's graph. [FR-1205]

### CONSOLE-10
The run page's tab state round-trips through the URL: `?tab=board` opens the
Board tab, a copied board URL reopens it, selecting Graph clears `?tab`, and
unknown (`?tab=nonsense`) or disabled (`?tab=cost`) values render Graph with
the URL left untouched. [FR-017, SC-005]

### CONSOLE-11
The Board tab renders one row per task of the run's pinned plan (the plan
version this run published, else the project's current plan), and selecting
a row shows the detail pane's fields, the task's evidence section, and its
timeline entries. [FR-019, FR-021, FR-021a]

### CONSOLE-12
The Board tab's counter strip reads "this run": per-status counts, fix
attempts, errored and diverged counts are derived from this run's task rows,
never from the project's stored stats. [FR-019]

### CONSOLE-13
The Board tab degrades to a banner — never an exception — when the run has
no project (the no-project banner) and when its project answers unknown (the
not-found banner); the rest of the run page keeps working. [FR-022, SC-006]

### CONSOLE-14
A reachable project with zero tasks for this run shows the explicit empty
state rather than a bare list. [SC-006]

### CONSOLE-15
While the board is healthy the connection-lost line never shows; a transient
board fetch failure shows it without evicting rendered data. The positive
path is pinned at the unit tier (`board.store.test.ts` and
`BoardTab.test.ts` drive real failures through the store); this tier pins
the healthy absence so the line cannot rot into a permanent fixture.
[FR-023a]

### CONSOLE-16
Switching Board → Graph → Board leaves the Graph tab unchanged (same canvas
node count), and the run header — title and stage strip — persists above the
tab bar on every tab. [FR-017, FR-018]

## Failure modes

Both clauses are asserted by `app.pw.ts` against the built dashboard on
`VITE_API=mock` (the mock is what makes the whole SPA runnable headless
with no backend). A failure here is usually not a component fault but an
assembly fault: an adapter mapping, a store refresh, or the provider
selection in `dashboard/frontend/src/api/client.ts`.
