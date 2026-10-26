# Contract: console clause disposition (FR-071, FR-072)

`U/app.md` is the assembled-console contract. Dispositions:
- **keep**: unchanged text and test.
- **rewrite**: same number, new surface, text changed. A `(rewritten 018: …)` line follows the heading.
- **retire**: the heading is removed and a tombstone is added under `## Retired clauses` (research R-11).

Each disposition lands in the slice named, in the same commit as the code that changes the behaviour. Tests move into the split files `U/app.<screen>.pw.ts` in slice 1.

## 1. CONSOLE-1 to CONSOLE-29

| Clause | Today (short) | Disposition | Slice | New statement / reason |
|---|---|---|---|---|
| CONSOLE-1 | Fleet: one row per run, no empty state while runs exist | rewrite | 4 | One v5 row per run, with columns Run · Graph · Arm · Outcome · Where/reason · revise · Cost · Elapsed · Open; the empty state never shows while runs exist. |
| CONSOLE-2 | Header stats and inbox badge | rewrite | 1 | The header's Inbox item shows the badge when the provider reports items, and none otherwise. Stats removed (S4). |
| CONSOLE-3 | Fleet stage strip, 18 marks | **retire** (GATE 2 item) | 4 | v5's Fleet has no stage strip (S6). The per-run stage spine (PRD FR-601) is the Observe canvas. Canonical stages remain visible in the palette groups and the rail's per-stage cost. |
| CONSOLE-4 | Run canvas: one node per graph node, loop counter `used/max`, backward edge curved | keep (moves to `app.run.pw.ts`) | 2 | — |
| CONSOLE-5 | Deciding a gate on the canvas clears its controls | rewrite | 3 | Selecting a canvas node with a pending gate opens its card over the canvas (PRD FR-1205). Deciding there, or from the rail's call to action, closes the card. Once the next run state no longer lists the item, both the node's pending mark and the call to action are gone. |
| CONSOLE-6 | Legacy run: no-graph empty state plus stage strip | rewrite | 2 | A legacy run shows the no-graph empty state; the rail still shows the run block. The strip is gone. |
| CONSOLE-7 | Editor applies recorded YAML text; shape errors keep the canvas disabled | **retire** (in T063) | 6 | v5's Design draws no text pane; graphs are edited on the canvas (S, v5-only). The parse route stays served for Design's round-trip (CONSOLE-9). |
| CONSOLE-8 | Run view has no edit affordance; "open copy in editor" lands on the editor | rewrite | 6 | Observe offers no edit affordance. The Design switch lands on `/graphs/<sha>?from=run:<id>` holding the run's graph. |
| CONSOLE-9 | Editing an inspector field round-trips through parse | rewrite | 6 | In Design, changing an edge's `max_traversals` in the inspector round-trips through parse. The working copy gains the new sha and no error shows. |
| CONSOLE-10 | `?tab=` round trip; `?tab=gates` renders Graph | rewrite | 5 | `?tab=board` opens the Board view and a copied URL reopens it. Selecting Graph clears `?tab`. `?tab=cost` opens Observe with the rail's Cost section. An unknown value renders Observe. |
| CONSOLE-11 | Board rows of the pinned plan; detail, evidence, timeline | rewrite | 5 | Same statement, on the full Agent Board at `/runs/:id/board`. |
| CONSOLE-12 | Board counter strip "this run" | rewrite | 5 | Same, on the full Agent Board. |
| CONSOLE-13 | Board banners (no project, not found) | rewrite | 5 | Same banners on the kanban and the full Agent Board. |
| CONSOLE-14 | Zero tasks shows the explicit empty state | rewrite | 5 | Same, on the kanban and the full Agent Board. |
| CONSOLE-15 | Healthy board never shows the connection-lost line | rewrite | 5 | Same, on the full Agent Board. |
| CONSOLE-16 | Board→Graph→Board keeps the canvas; the run header persists | rewrite | 5 | Switching Board → Graph → Board keeps the Observe canvas node count. The header's run switch shows the run on both views. |
| CONSOLE-17 | Inbox: one entry per item; count equals the badge; run link | rewrite | 3 | v5 list: one row per item (kind label, age, title, where). The count equals the badge. Selecting a row shows its card. The card's run reference opens that run. |
| CONSOLE-18 | Clarify: accept suggestion; non-blank answer | rewrite | 3 | Same rules on the v5 clarify card. |
| CONSOLE-19 | Gate: approve and reject immediately; revise needs a comment | rewrite | 3 | Same rules on the v5 gate card (generic gate names). |
| CONSOLE-20 | Merge override: verdict, checks; override needs justification | rewrite | 3 | Same rules on the v5 override card. |
| CONSOLE-21 | Escalation: retry and quarantine resolve it | rewrite | 3 | The task card offers approve, revise (guidance, thaw tests) and reject. Each sends exactly that outcome, and retry is never sent as approve (R-3, V5). |
| CONSOLE-22 | All resolved → empty state, no badge | rewrite | 3 | Same: "Nothing waiting on you", and no badge. |
| CONSOLE-23 | Gate decided in the inbox is no longer offered on the canvas | rewrite | 3 | …is no longer offered in that run's rail. |
| CONSOLE-24 | Cost tab: role rows with calls, tokens, dollars and a total; `?tab=cost` | rewrite | 2 | The rail's Cost section: one row per role with calls, tokens and dollars, and a total. `?tab=cost` opens it (S3). |
| CONSOLE-25 | "not priced"; partial total; never `$0.00` | rewrite | 2 | Same rules in the rail's Cost section. |
| CONSOLE-26 | Budget figures, or "no budget" | rewrite | 2 | Same facts in the rail's budget block and Cost section. |
| CONSOLE-27 | Header spend total counts priced runs only | rewrite | 1 | The footer, on non-canvas screens, shows the fleet spend total of priced runs only and states how many runs it left out (spec 011 FR-003; S4). |
| CONSOLE-28 | Start form budget validation; budget shows on the Cost tab | rewrite | 6 | The start form opened from "Run this version" validates the budget the same way. A run started with a budget shows it in the rail. |
| CONSOLE-29 | Budget gate entry says what approving grants | rewrite | 3 | The budget card says approve grants one more increment and reject ends the run `rejected:budget` (V6). |

## 2. New clauses (CONSOLE-30 onward)

Each V clause starts its body with the V number. Every test asserts the corrected behaviour and the absence of the wrong one (R-11).

| Clause | Slice | Statement |
|---|---|---|
| CONSOLE-30 | 2 | V1 — A run that ended on a `halt` port lights the failed sink, which shows the node's result string. No element is labelled `halted`. |
| CONSOLE-31 | 2 | V2 — A revise edge at its limit states that the next revise escalates the run. An escalated run lights the escalated sink. |
| CONSOLE-32 | 2 | V3 — The completed sink lists every node that completed the run. In Design, an edgeless non-terminal out-port warns that it becomes a completion sink, and the terminal copy reads "rejected, failed or escalated". |
| CONSOLE-33 | 3 | V4 — The tool-escalation card offers Approve and Deny only and states that a timeout counts as not approved. No Halt action exists. |
| CONSOLE-34 | 3 | V5 — The task card states the reject consequence (`failed:quarantined-tasks` after the wave) before the action. |
| CONSOLE-35 | 2 | V6 — With no budget the rail reads "off" with no bar. A `rejected:budget` run shows that result string on Fleet (slice 4 extends the test). |
| CONSOLE-36 | 5 | V7 — The kanban has columns by wire task status only (no `claimed` or `queued`). A task whose live and authoritative statuses differ shows both. |
| CONSOLE-37 | 6 | V8 — The PipelineConfig panel's `validate_run_roles` check shows the registry's real reviewer and dev ids, and marks "same model weights" when their `model_id` is equal. |
| CONSOLE-38 | 6 | V9 — The Design palette groups node types by `canonical_stage` in served `CANONICAL_STAGES` order. Planned types are marked planned and cannot be placed. A planned type with no stage is labelled unmapped. |
| CONSOLE-39 | 4 | V10 — Fleet's arm cell shows harness and model id verbatim from the fixture, and an unpriced run's cost never reads `$0.00`. |
| CONSOLE-40 | 3 | FR-601 — A run with pending items shows one call to action per item in its rail. Each opens that item's card over the canvas with the Inbox's actions. |
| CONSOLE-41 | 3 | FR-022 — The rail's Events list past decisions for a live run (human decisions, timed, with the "automatic and timed-out decisions appear when the run ends" note) and for a closed run (untimed, "not approved" for a closed non-approval). The rail says history is unavailable when neither source exists. |
| CONSOLE-42 | 6 | Design refuses a drop whose payloads differ, and says why. No edge is created. |
| CONSOLE-43 | 6 | Design: a layout-only save keeps the sha and an edge change alters it. "Run this version" is available only for the saved, unchanged shipped `default` graph, and states its reason otherwise (R-15). |
| CONSOLE-44 | 6 | Graphs shows one card per shipped graph (name, sha, counts, "Open in Design") and the PipelineConfig panel. A value without a source reads `not measured`. |
| CONSOLE-45 | 7 | Compare shows one row per arm with SC and $/case per graph, `not measured` where absent, and heatmap columns in record-stage order (present stages only). An empty store shows the empty state naming the root it read. |
| CONSOLE-46 | 8 | Interfaces shows five rows and six columns. The installed, checkpoint and session columns read `not measured`. The family column is filled only on the dev harness's row. |
| CONSOLE-47 | 1 | The command palette opens on ⌘K or Ctrl+K, filters v5's commands, and runs the chosen one. The ⋯ menu's light theme switches `data-theme` on the document. |
| CONSOLE-48 | 1 | The header shows Fleet · Inbox · run-in-context and Graphs · Compare · Interfaces, each navigating. With no runs, the run entry is disabled and reads "No runs". |
| CONSOLE-49 | 2 | The Observe inspector of a node whose configured model differs from the answering model shows both ids and marks the difference. The `code` node shows the inner loop read-only. |
| CONSOLE-50 | 1 | The footer shows context left and hints right on every screen. |
| CONSOLE-51 | 2 | A run whose state cannot be projected (retention expired, registry drift) shows its reason under the rail's run block. The canvas shows its empty state, and a provider failure reads "could not load", not empty. |
| CONSOLE-52 | 2 | The rail's Cost section has a "Revise traversals" group with one row per revise edge, used against max (S16). |
| CONSOLE-53 | 4 | A Fleet row waiting on a person (gate, clarify or escalation) offers "Decide", the run in context offers "Open run", and every other row offers "Open" (S16). |

## 3. Component clauses

Each new library component (data-model §4.2) declares its own `<NAME>-n` clauses in its `.md`, cited by its `.spec.ts` and `.pw.ts`.
- `APP_HEADER-*` and `TOASTS-*` are rewritten in slice 1. Clauses that assert the old wordmark, uppercase labels or stats are retired by tombstone in `app_header.md`.
- `GATE_DECISION-*` retires with the component in slice 3 if nothing else uses it (verify then; otherwise keep).
- `STAGE_DOTS-*`, `FLEET_TABLE-*` and `FLEET_ROW-*` retire with their components in slice 4 (T049; `DotState` is re-homed in `F/api/types.ts`).
- `DS_BUNDLE-1..3` are **kept**. Their test (`U/scripts/build-ds-bundle.spec.ts`) is retargeted in T049 from the `stage_dots` profile to a surviving one (`status_pip/running`). The rule each asserts is unchanged.
- The `yaml_pane` and `schema_form` components retire with S15 (the YAML pane and the schema-form inspector) in slice 6 (T063). That is when their last importers go: `GraphEditorView.vue`, `GraphInspector.vue`'s schema-form fields, and `F/features/graphs/schemaCoverage.test.ts`. CONSOLE-7 is tombstoned in T063. CONSOLE-8 and CONSOLE-9 are kept: their tests are deleted in T063 and restored on Design in T066, within the same phase.

## 4. Bars

- `python scripts/check_clauses.py` at the end of every slice: 0 dangling. Untested may only list clauses that already had no test on the base, recorded in baseline.md at slice 0.
- V clauses (CONSOLE-30 to CONSOLE-39): the reviewer reverts the adapter or component line that implements each one and confirms the test fails. The results are recorded in verification.md.
