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

- Built: the Fleet view, the run page (Graph, Board and Cost tabs), the
  graph editor, and the decision inbox (`src/features/inbox/` — it lists
  every item waiting on a person across runs and resolves all four kinds:
  clarify answers, gate decisions, merge overrides, escalations). The Cost
  tab (`src/features/cost/`, 011) shows per-role spend and tokens, the
  priced/partial total, and the budget block with the dollars counted
  toward the gate.
- Not built: the run page's Gates tab (disabled placeholder, ruling G7 of
  spec 002).
