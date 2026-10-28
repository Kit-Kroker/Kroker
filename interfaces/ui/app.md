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
The header's inbox badge appears when the provider reports inbox items and
carries the pending count. The v5 header shows no run counter and no spend
stats — totals live in the footer (CONSOLE-27, CONSOLE-50). [FR-601]

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
Selecting a canvas node with a pending gate opens its card over the
canvas (PRD FR-1205). Deciding there, or from the rail's call to
action, closes the card. Once the next run state no longer lists the
item, both the node's pending mark and the call to action are gone.
[FR-1205, FR-301/302]

### CONSOLE-6
A legacy run shows the no-graph empty state; the rail still shows the
run block. The run header's stage strip is gone — v5 draws none on the
run. [FR-1205, E-76 U7]

### CONSOLE-8
The run view offers no edit affordance; its "open copy in editor" link lands
on the graph editor holding the run's graph. [FR-1205]

### CONSOLE-10
The run page's tab state round-trips through the URL: `?tab=board` opens the
Board tab, a copied board URL reopens it, selecting Graph clears `?tab`, and
unknown (`?tab=nonsense`) or disabled (`?tab=gates`) values render Graph with
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

### CONSOLE-17
v5 list: one row per item (kind label, age, title, where). The count
equals the badge. Selecting a row shows its card. The card's run
reference opens that run. [FR-601, FR-305]

### CONSOLE-18
Same rules on the v5 clarify card: accepting the suggestion is one
action; a typed answer is sent only when it is not blank. [FR-601]

### CONSOLE-19
Same rules on the v5 gate card (generic gate names): approve and
reject send at once; revise is unavailable until a comment is entered.
[FR-601, FR-301/302]

### CONSOLE-20
Same rules on the v5 override card: the verdict and one row per check
render; override is unavailable until a justification is entered, and
send-back is not. [FR-601, FR-304]

### CONSOLE-21
The task card offers approve, revise (guidance, thaw tests) and
reject. Each sends exactly that outcome, and retry is never sent as
approve (R-3, V5). [FR-601]

### CONSOLE-22
When every waiting item has been resolved the inbox shows "Nothing
waiting on you" and the header shows no badge. [FR-601]

### CONSOLE-23
A gate decided in the inbox is no longer offered in that run's rail.
[FR-601, FR-302]

### CONSOLE-29
The budget card says approve grants one more increment and reject ends
the run `rejected:budget` (V6). [FR-008, FR-701]

### CONSOLE-24
The rail's Cost section: one row per role with calls, tokens and
dollars, and a total. `?rail=cost` opens it, and the legacy `?tab=cost`
deep link still lands on it (S3). [FR-001, FR-701]

### CONSOLE-25
A role or total that has tokens and no price reads "not priced", and a
total that mixes priced and unpriced roles is marked partial; no such
figure reads `$0.00` — the same rules in the rail's Cost section.
[FR-003, FR-701]

### CONSOLE-26
The budget figures — amount, limit, counted, share, crossings, the
scope note — or "no budget": the same facts in the rail's budget block
and Cost section. [FR-001b, FR-701]

### CONSOLE-27
The footer's total sums priced runs only and states how many runs it left
out; when nothing is priced it reads `not priced`, and with no runs `—`.
The figure never folds a pricing miss in as zero. [FR-003]

### CONSOLE-28
The start form accepts an optional budget; a budget that is not a number
greater than zero blocks the start with a message, and a run started with a
budget shows that budget on its Cost tab. [FR-006, FR-007]

### CONSOLE-48
The header shows Fleet · Inbox · run-in-context and Graphs · Compare ·
Interfaces, each navigating. With no runs, the run entry is disabled and
reads "No runs". (Slice 1: Compare and Interfaces are not yet available —
they appear with their routes; the no-runs entry is covered at the unit
tier until a zero-fleet mock exists.)

### CONSOLE-50
The footer shows context left and hints right on every screen.

### CONSOLE-47
The command palette opens on ⌘K or Ctrl+K, filters v5's commands, and
runs the chosen one. The ⋯ menu's light theme switches `data-theme` on
the document.

### CONSOLE-30
V1 — A run that ended on a `halt` port lights the failed sink, which
shows the node's result string. No element is labelled `halted`.

### CONSOLE-31
V2 — A revise edge at its limit states that the next revise escalates
the run. An escalated run lights the escalated sink.

### CONSOLE-32
V3 — The completed sink lists every node that completed the run. (In
Design, an edgeless non-terminal out-port warns that it becomes a
completion sink, and the terminal copy reads "rejected, failed or
escalated" — with the Design slice.)

### CONSOLE-35
V6 — With no budget the rail reads "off" with no bar. A
`rejected:budget` run shows that result string on Fleet (slice 4
extends the test).

### CONSOLE-49
The Observe inspector of a node whose configured model differs from the
answering model shows both ids and marks the difference. The `code`
node shows the inner loop read-only.

### CONSOLE-51
A run whose state cannot be projected (retention expired, registry
drift) shows its reason under the rail's run block. The canvas shows
its empty state, and a provider failure reads "could not load", not
empty.

### CONSOLE-52
The rail's Cost section has a "Revise traversals" group with one row
per revise edge, used against max (S16).

### CONSOLE-33
V4 — The tool-escalation card offers Approve and Deny only and states
that a timeout counts as not approved. No Halt action exists.

### CONSOLE-34
V5 — The task card states the reject consequence
(`failed:quarantined-tasks` after the wave) before the action.

### CONSOLE-40
FR-601 — A run with pending items shows one call to action per item in
its rail. Each opens that item's card over the canvas with the Inbox's
actions.

### CONSOLE-41
FR-022 — The rail's Events list past decisions for a live run (human
decisions, timed, with the "automatic and timed-out decisions appear
when the run ends" note) and for a closed run (untimed, "not approved"
for a closed non-approval). The rail says history is unavailable when
neither source exists.

## Retired clauses

- GATE_DECISION-1..3 — retired 018 T044: the gate_decision component is
  deleted (the decision card replaces it; a grep shows no importer, and
  the ds-bundle spec never referenced it). Their rules live on in
  DECISION_CARD-1..6 and CONSOLE-5.

## Failure modes

Both clauses are asserted by `app.pw.ts` against the built dashboard on
`VITE_API=mock` (the mock is what makes the whole SPA runnable headless
with no backend). A failure here is usually not a component fault but an
assembly fault: an adapter mapping, a store refresh, or the provider
selection in `dashboard/frontend/src/api/client.ts`. The inbox's
load-failure, incomplete-list and already-decided states are pinned at
the unit tier (`inbox.store.test.ts`, `InboxView.test.ts`): the mock
provider cannot fail a read or report an unreadable run, and it refuses a
write only in the few seconds between a decision taken on another screen
and the next poll, which a test cannot hit reliably. A closed run recorded
before role tracking shows its total with "No breakdown recorded".
