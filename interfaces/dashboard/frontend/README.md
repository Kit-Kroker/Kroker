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

- `VITE_API=mock` (default) — the in-memory mock at `src/api/mock/`, a
  line-for-line port of the React prototype's seed data and decision flows.
- `VITE_API=http` — reserved for the future FastAPI provider
  (`src/api/http.ts`, not yet wired). Reimplement `DashboardApi` there with
  `fetch` against `VITE_API_BASE`.

When the FastAPI provider lands, no component or store changes are needed:
implement `DashboardApi`, set `VITE_API=http`, and the UI points at the real
Temporal-backed service.

## Status

- Plan 1 (this code): foundation + Fleet view.
- Plan 2 (follow-up): decision inbox cards + run-detail panels.
