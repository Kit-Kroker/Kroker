# ROADMAP.html — personal status dashboard for the implementation tracker

| | |
|---|---|
| Status | Design — approved, awaiting spec review |
| Date | 2026-07-18 |
| Source | `ROADMAP.md` |
| Audience | The maintainer (single-user personal dashboard) |
| Scope guard | One self-contained HTML file. No build, no framework, no client-side markdown parsing, no generator script. |

## 1. Problem

`ROADMAP.md` is the project's living tracker (~300 lines, 9 sections, ~80
items). It is accurate but not glanceable: phase-level progress, the 15-stage
DAG status, and "what moved recently" all require reading prose. The maintainer
wants a 5-second view of where the project stands, with the detail one click
away.

## 2. Goals / non-goals

**Goals**
- Render the ROADMAP as a single HTML page that opens in any browser via
  `file://` — no server, no network, no build step.
- Surface the four status classes (`[x]` / `[ ] ⚠️` / `[ ]` / `—`) consistently
  across every section.
- Make the 15-stage DAG and phase-level progress the first thing the eye lands
  on; push per-item detail below the fold.
- Stay readable as a PDF export (`@media print`).
- Match the project's docs aesthetic (GitHub-flavored light) — feels like a
  rendered version of the `.md`, not a separate app.

**Non-goals**
- Not a team/stakeholder presentation piece.
- Not an interactive explorer (no tabbed sidebar, no per-item drilldown pages).
- Not a generator: data is hand-extracted into a JSON literal once. When
  `ROADMAP.md` changes, the maintainer re-runs the build conversationally.
- Not dark mode, not themeable.
- Not wired into CI or `mkdocs`.

## 3. Approach considered

| Option | Why not |
|---|---|
| Client-side markdown fetch + parse | `file://` CORS blocks `fetch()`. Would require running a server. |
| mkdocs / docs-site integration | Pulls in a build toolchain and a theme dependency for a one-page artifact. Wrong weight. |
| Tabbed sidebar explorer | Heavier DOM, app-like, drifts from "GitHub-flavored doc" aesthetic the user picked. |
| **Embedded JSON literal, static render** | **Chosen.** Self-contained, instant open, no dependencies, print-friendly. Costs a hand-extraction step. |

## 4. File

`docs/roadmap.html` — one file, all CSS inline in `<style>`, all JS inline in
`<script>`. Linked from nowhere (yet); the maintainer opens it directly. The
location next to `docs/foundation.md` etc. keeps it inside the existing docs
tree without entangling it with the markdown-rendered doc set.

## 5. Data model

The HTML embeds a single JS object literal:

```js
const ROADMAP = {
  meta: {
    lastVerified: "2026-07-17",
    source: "ROADMAP.md",
    legend: { done: "[x]", partial: "[ ] ⚠️", notstarted: "[ ]", notmeasurable: "—" }
  },
  phases: [
    { id: "P1", title: "Greenfield pipeline …", status: "done",
      exit: "one project shipped end-to-end", note: "…" },
    { id: "P2", title: "Brownfield, dashboard …", status: "partial", note: "…" },
    { id: "P3", title: "Hindsight memory …",    status: "partial", note: "…" },
    { id: "P4", title: "MCP surface …",         status: "notstarted", note: "…" }
  ],
  stages: [ /* 15 entries, id 0..14, name + status + note */ ],
  items: [
    /* flat list of every FR / NFR / SC / US / ADR / §7 / E- item,
       tagged with section: "FR" | "NFR" | "SC" | "US" | "ADR" | "STRUCT" | "E",
       with id, title, status, note, recent:boolean */
  ]
};
```

**Status normalization** (mechanical):

| ROADMAP.md token | `status` |
|---|---|
| `- [x]` | `done` |
| `- [ ] ⚠️` | `partial` |
| `- [ ]` (no ⚠️) | `notstarted` |
| `- [ ] —` or ` — ` mid-row | `notmeasurable` |

**`recent` heuristic.** `true` if the item's `note` contains any of:
- a date `2026-` (e.g. `2026-07-16-registry-drives-every-role`),
- the literal `**(new)**`,
- the literal `**Done**` (used in §8 strikethroughs),
- the literal `~~` (markdown strikethrough — marks completed increments).

This is the only non-trivial extraction rule and it is documented inline in the
`<script>` so a future refresh knows how to re-derive it.

## 6. Layout (top → bottom)

### 6.1 Header
- `<h1>` "Implementation Roadmap — Agentic SDLC Factory".
- Subtitle: source-of-truth pointer (`PRD.md`, `ARCHITECTURE.md`, `SDLC-spec.md`)
  and "Last verified 2026-07-17".
- Legend row: four chips with status color + token (`[x] Done`, etc.).

### 6.2 Summary dashboard (the 5-second view)

Rendered as a single column of blocks (no grid cleverness):

1. **Phase progress** — one row per phase: `[P1] [██████████ 100%] ✓ one project shipped end-to-end`.
   Bar fill color = status color. Bar width = phase completion (P1 = 100%, P2/P3
   estimated from items + note, P4 = 0%). Phase completion is encoded in the
   data, not computed — it's a single `phasePct` field per phase.

2. **15-stage DAG strip** — horizontal row of 15 numbered cells,
   `0 → 1 → 2 → … → 14`, joined by `→` glyphs. Each cell is a small square
   colored by status; the stage name sits under the number. Hover tooltip =
   stage name + status + truncated note. This is the single most informative
   visual in the page.

3. **Section grid** — six small tiles in a 3×2 grid (FR / NFR / SC / US / ADR /
   E-items). Each tile shows `done / total` and a thin progress bar. Clicking a
   tile scrolls to that section in the detail list. Phases (§0) and the DAG
   (§1) have their own dedicated blocks above and need no tile; §7 STRUCT has
   too few items (~5) to merit a tile and renders only in the detail list.

4. **Status totals** — four big numbers in a row:
   `Done: 23  ·  Partial: 18  ·  Not started: 31  ·  Not measurable: 6`.
   Computed from `items` at render time.

### 6.3 Filter bar (sticky)
Above the detail list, sticks to viewport top on scroll:
- **Filter chips:** `All · Done · Partial · Not-started · Not-measurable · Recently changed`.
  Multi-select; clicking toggles membership in an active-filter set. `All` clears.
- **Search box:** text input, filters rows by substring across `id + title + note`,
  case-insensitive, debounced via `input` event.

### 6.4 Detail list
One `<section>` per ROADMAP.md heading, in source order:
- §0 Phases
- §1 Pipeline — 15-stage DAG
- §2 Functional requirements
- §3 Non-functional requirements
- §4 Success criteria
- §5 User stories
- §6 ADRs
- §7 Structural / repo-hardening
- §9 Filesystem-first work items (`E-`)

Each item is a row:
```
[status-chip] [id-link] title ............ [optional ⚠ recent marker]
              note (truncated to 140 chars; click to expand)
```
- `id-link` for FR/NFR/SC/US/ADR items points to `../ROADMAP.md` (relative
  link works from `docs/roadmap.html` to repo root).
- Long notes (>140 chars) render truncated with a "…" button that toggles a
  `.expanded` class showing the full text inline.
- §8 (Recommended next increments) is rendered as its own section since it
  carries the "what's next" narrative — not item-rows but a styled ordered list.

## 7. Styling

### 7.1 Tokens
```
bg:           #ffffff
fg:           #1f2328
muted:        #57606a
border:       #d0d7de          (GitHub's exact border)
mono:         ui-monospace, SFMono-Regular, "Cascadia Code", Menlo, monospace
sans:         -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif

status.done:          #1a7f37   (GitHub green)
status.partial:       #bf8700   (amber)
status.notstarted:    #57606a   (gray)
status.notmeasurable: #8250df   (GitHub purple)
```

### 7.2 Component styling
- Page max-width `1012px` (GitHub's content column), centered, `16px` padding.
- `h1` 32px / `h2` 24px / `h3` 18px, weights matching GitHub.
- Status chip: a 14×14 colored dot + small uppercase label.
- Phase bar: 12px tall, 4px radius, `#eaeef2` track, status-color fill.
- DAG cell: 40×40px, 6px radius, status color fill at 15% opacity, status
  color border at 100%, stage number in bold inside, name as 11px label below.
- Section tile: 1px border, 8px radius, 16px padding.
- Detail row: `border-bottom: 1px solid #eaeef2`, 12px vertical padding.
- `id-link`: monospace, 13px, status color, `text-decoration: none`, hover
  underline.

### 7.3 Print
```css
@media print {
  .filter-bar, .search-box, .expand-btn { display: none; }
  .detail-row .full { display: inline !important; }   /* expand all notes */
  body { max-width: none; }
  a { color: #1f2328; text-decoration: none; }
}
```

## 8. Interactivity

~80 lines of vanilla JS, no libraries:

- **Render** on `DOMContentLoaded`: build phase bars, DAG strip, section tiles,
  totals, then iterate `items` to build detail rows grouped by section.
- **Filter chips** maintain a `Set<status>` plus a `recentlyChanged` boolean.
  `All` = set of all four statuses + `recentlyChanged=false`. Clicking a status
  chip toggles its membership. `Recently changed` is independent (AND-combined).
  Re-render iterates rows and sets `display:none` based on the active filter.
- **Search** adds a substring filter AND-combined with chips. Debounced 100ms.
- **Expand buttons** toggle a `.expanded` class on the parent row.
- **DAG cell tooltips** are CSS `:hover` tooltips via `data-tip` attribute and a
  `::after` pseudo-element — no JS for the tooltip itself.
- **Section tile clicks** scroll-to the section heading via
  `element.scrollIntoView({behavior:'smooth'})`.

## 9. Out of scope (YAGNI, explicitly)

- No dark mode.
- No tabs / sidebar.
- No client-side markdown rendering.
- No generator script (one-shot hand extraction).
- No dependency on Chart.js / D3 / any CSS framework.
- No CI hook to regenerate on `ROADMAP.md` change.
- No anchor permalinks within the HTML (item ids link out to `ROADMAP.md` only).
- No "open in editor" affordance.

## 10. Testing / verification

Manual checklist (no test framework for an HTML file):

1. Open `docs/roadmap.html` directly via `file://` in Chrome and Firefox.
2. Verify the four status totals match a hand-count of `ROADMAP.md`.
3. Verify the 15-stage DAG renders all 15 cells with the right colors (7 done
   out of 15 per §1).
4. Verify each filter chip narrows the detail list correctly; `All` restores.
5. Verify search matches across id, title, and note.
6. Verify `Print → Save as PDF` produces a clean export with no filter UI.
7. Verify all `id-link`s resolve to `../ROADMAP.md` (open one of each section).
8. Verify the page weighs <30 KB (inline CSS + JS + data, no images).

## 11. Risks

- **Data drift.** The HTML is a snapshot. Mitigation: the date stamp in the
  header makes staleness visible; the inline comment explains the extraction
  rule so a refresh is mechanical.
- **Subjective phase %s.** Phase completion is hand-encoded, not derived.
  Mitigation: encode it conservatively (P2/P3 sit at "partial" but with
  explicit percentages from the note prose), and document the choice in the
  data comment.
- **Inline-data weight.** ~80 items × ~250 bytes each ≈ 20 KB. Gzipped
  transitively negligible; on disk fine.

## 12. Open follow-ups (not in this increment)

- A `tools/extract_roadmap.py` that parses `ROADMAP.md` → JSON, if drift
  becomes annoying. Defer until the second refresh.
- A mkdocs embed if this ever needs to live on a docs site. Defer.
