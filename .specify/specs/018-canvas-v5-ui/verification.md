# Round 018 — canvas-v5 UI rework — verification

Branch `018-canvas-v5-ui`. Evidence gathered per task T083; the
reviewer verdicts live in `.workspace/tmp/reviewer-018-T*.md` and the
qa RED reports in `.workspace/tmp/qa-018-T*-red.md`.

## Gates

(to be recorded by T083)

## Redirects kept (T081)

The `/graphs?sha=` and `/graphs?from=run:` redirects are KEPT: in-app
links still produce them — the shell's Observe/Design switch and the
palette's Validate/Fit commands push
`/graphs/${sha}?from=run:${id}` (`F/app/App.vue`, `runCommand`), and
`/graphs?sha=` remains the bookmark form of "open this sha in Design"
(`F/app/router.redirects.test.ts` pins both). `?tab=cost` still lands
on the rail's Cost section — CONSOLE-24's test
(`U/app.run.pw.ts:128`, deep link at :135) is green in the final
`check_ui.py` run. `boundaries.test.ts` needed no new entry: it
polices import rules with planted fakes, not a folder enumeration, and
the new `features/compare/` and `features/interfaces/` screens follow
the existing boundaries.

## Clause report

(to be recorded by T083)

## Reviewer revert checks (CONSOLE-30..39)

(to be recorded by T083)

## Deletions

(to be recorded by T083)

## Diff guard

(to be recorded by T083)

## File sizes

(to be recorded by T083)

## Proposals (SG-2 — awaiting orchestrator approval; files NOT edited)

### `interfaces/AGENTS.md` — the screen table

The table predates v5 and now misstates three rows. Proposed:

| Screen | Route | Folder | View |
|---|---|---|---|
| Fleet | `/` | `src/features/fleet/` | `FleetView.vue` |
| Decision inbox | `/inbox` | `src/features/inbox/` | `InboxView.vue` |
| Run detail | `/runs/:id` | `src/app/RunPage.vue` + `src/features/run/` | `RunView.vue` (tab host) |
| Board | tab of `/runs/:id` (`?tab=board`) | `src/features/board/` | `BoardTab.vue` |
| Cost | tab of `/runs/:id` (`?tab=cost`) | `src/features/cost/` | `CostTab.vue` |
| Graphs (catalog) | `/graphs` | `src/features/graphs/` | `GraphsView.vue` |
| Graphs (Design) | `/graphs/:sha` | `src/features/graphs/` | `DesignView.vue` |
| Compare | `/compare` | `src/features/compare/` | `CompareView.vue` |
| Interfaces | `/interfaces` | `src/features/interfaces/` | `InterfacesView.vue` |

(The current table's "Graphs (editor) → GraphEditorView.vue" row names
a deleted view; the new Compare/Interfaces screens have no rows.)

### `interfaces/ui/AGENTS.md:10` — the stale clause-naming example

The example names the retired `stage_dots/` component. Proposed
replacement text, naming a surviving component:

> Name clause prefixes after the component directory:
> `status_pip/` → `STATUS_PIP-N`.

### `docs/adr.md` ADR-8 — the read-route amendment

Proposed one-line amendment (per plan.md's doc-change table):

> Read-only routes over file-backed stores the repo already owns
> (benchmark records, the containment policy, the agent registry) are
> allowed and remain stateless shells: they hold no state, write
> nothing, and re-read per request.

The four v5 read routes (`/fleet/summary`, `/graphs/shipped`,
`/compare`, `/interfaces`) operate exactly this way — the T074/T067
suites pin the no-write import rule and the request-time reads.
