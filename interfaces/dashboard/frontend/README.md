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

- Plan 1 (this code): foundation + Fleet view.
- Plan 2 (follow-up): decision inbox cards + run-detail panels.
