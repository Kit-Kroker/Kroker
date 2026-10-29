# SDLC Factory Console — frontend

Vue 3 SPA for the AI-SDLC pipeline's human-in-the-loop surface. See
`docs/superpowers/specs/2026-07-05-dashboard-vue3-frontend-design.md` for the
design and `records/2026-07-12-factory-console/Factory Console.dc.html` for the visual/behavioral
prototype this was ported from.

## Run

```bash
npm install
npm run dev        # Vite dev server (http://localhost:5173)
```

## Scripts

| Script               | Purpose                                  |
|----------------------|------------------------------------------|
| `npm run dev`        | Vite dev server                          |
| `npm run build`      | `vue-tsc --noEmit` + production build    |
| `npm run preview`    | serve the production build               |
| `npm run test`       | Vitest (single run)                      |
| `npm run test:watch` | Vitest watch                             |
| `npm run typecheck`  | `vue-tsc --noEmit`                       |

## Data source

The UI talks only to `src/api/client.ts`, which exposes the `DashboardApi`
interface. The active provider is selected by `VITE_API`:

- `http` (default) — live provider (`src/api/http.ts`) talking to the backend.
- `VITE_API=mock` — the in-memory mock at `src/api/mock/`, which is what the
  showcase and the Playwright app tier run on.

## Status

The v5 console (spec 018): six screens over the `@kroker/ui` library.

- Fleet (`/`) — every run with its arm, graph, traversals, outcome and
  pending gates (the v5 read `/fleet/summary`).
- Decision inbox (`/inbox`) — everything waiting on a person across
  runs; resolves all four kinds: clarify answers, gate decisions, merge
  overrides, escalations.
- Run page (`/runs/:id`) — tab host: Graph (the observe canvas), Board
  (the v5 kanban over the run's tasks) and Cost (per-role spend,
  tokens, the priced/partial total and the budget block). The Gates tab
  is not built (disabled placeholder, ruling G7 of spec 002).
- Graphs (`/graphs`) — the shipped-graph catalog with the
  PipelineConfig panel; `/graphs/:sha` is the Design editor (palette,
  validation, undo/redo; "Run this version" for the saved shipped
  default).
- Compare (`/compare`) — benchmark arms × graphs with SC and $/case and
  the rework-by-canonical-stage heatmap; an unavailable root names
  itself.
- Interfaces (`/interfaces`) — the harness containment matrix (layers,
  strict parity, family) and the adapter facts.

The mock replays the recorded read fixtures (`src/api/__fixtures__/read/`);
`VITE_API=mock` needs no backend.
