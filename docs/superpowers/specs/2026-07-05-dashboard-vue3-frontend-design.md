# SDLC Factory Console — Vue 3 Frontend

| | |
|---|---|
| Status | Approved (design) |
| Date | 2026-07-05 |
| Related | `design/Factory Console.dc.html` (interactive React/DC prototype — the visual + behavioral spec), `design/support.js` (DC runtime, reference only), `ARCHITECTURE.md` §8 (Interfaces — Dashboard), `PRD.md` FR-601 (Dashboard), `src/sdlc/models.py` (data contracts), `src/sdlc/workflows/feature.py` (signals/queries), `src/sdlc/cli.py` (HITL operations) |

---

## 1. Problem & goal

The pipeline exposes its human-in-the-loop surface through Temporal
signals and queries (`submit_gate_decision`, `answer_question`; `status`,
`pending_gate`), reachable today only via `sdlc.cli`. ARCHITECTURE.md §8
and PRD FR-601 call for a **dashboard** (FastAPI + single-page UI): fleet
list, per-run 14-stage spine, decision inbox with one-click accept and
approve/reject-with-comments, polled every 5s.

A high-fidelity, fully-interactive **React/DC prototype** already exists at
`design/Factory Console.dc.html` (runtime: `design/support.js`). It uses
mock seed data and demonstrates the exact UX and decision flows desired.

**Goal:** translate that prototype into a **Vue 3 single-page app** that is
pixel-and-behavior equivalent, with a clean API boundary so a future
FastAPI service (talking to real Temporal) can drop in behind the UI
without touching components.

**Non-goal (this plan):** any backend, workflow-query extensions, real
Temporal calls, auth/API-key flow, rate limiting, SSE, or Docker. All
deferred to a later plan — the dashboard's documented home is prepared but
no Python is added.

## 2. Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Scope of this work | **Frontend-only, mocked API.** No backend/workflow changes. Mocks live behind a clean client interface for later swap. |
| Tooling | **Vite + Vue 3 + TypeScript**, `<script setup>` SFCs, **Pinia** state, **vue-router** (hash history), scoped CSS. |
| Location | `interfaces/dashboard/frontend/` (the dashboard's documented home, ARCHITECTURE.md §8/§10). |
| Visual fidelity | Exact port of the prototype's dark theme, IBM Plex Sans/Mono, grid layouts, and animations. |
| Behavioral fidelity | Mock API reproduces the prototype's `Component` class logic verbatim (decision flows + live cost ticker). |
| API swap path | UI calls only `api/client.ts`; `VITE_API=mock\|http` selects the provider (`api/mock/index.ts`, `api/http.ts`). Real backend = implement `DashboardApi` in `api/http.ts` with `fetch`. |
| Routing | vue-router hash mode (deep-linkable run pages; works under FastAPI `/static/` with no rewrites). |

## 3. Architecture

```
components/ ──call──▶ stores/ (Pinia) ──call──▶ api/client.ts (interface)
                                                          │
                                  ┌───────────────────────┴───────────────────────┐
                                  ▼ (selected by VITE_API)                         ▼
                          api/mock/ (in-memory,                            api/http.ts
                          seed data, simulateLive)                    (stub, future — fetch)
```

- **UI → stores only.** Components never import the API directly; stores
  own fetching, mutation, and UI-only state (drafts, editing toggles,
  toasts, modal open/close).
- **Stores → `api/client.ts` only.** `client.ts` is a typed interface
  (a set of async functions) plus a provider switch. Today it resolves to
  the mock provider; a future HTTP provider in `api/http.ts` reimplements
  the same surface against FastAPI.
- **No shared mutable globals** outside Pinia. The mock's in-memory fleet
  is owned by the mock provider, not a store — so swapping providers
  removes all mock state in one place.

### Routes (vue-router, hash history)
| Path | View | Loads |
|---|---|---|
| `#/` | Fleet | `stores/fleet` |
| `#/inbox` | Decision inbox | `stores/inbox` |
| `#/runs/:id` | Run detail | `stores/run` (also used for fleet/inbox cross-links) |

## 4. Data contracts (`api/types.ts`)

Modeled on `src/sdlc/models.py` + the prototype's runtime shape, so a real
backend maps cleanly. The UI never sees fields it cannot get from a real
API later — display-only derivations live in composables, not the contract.

```ts
export type Status         = 'running' | 'blocked' | 'failed' | 'done';
export type GateOutcome    = 'approve' | 'revise' | 'reject';
export type ProjectMode    = 'brownfield' | 'greenfield';
export type InboxKind      = 'clarify' | 'gate' | 'override' | 'escalation';

export interface Decision {
  ts: string; gate: string; outcome: GateOutcome;
  comment: string; decider: string;
}

export interface Run {
  id: string; title: string; mode: ProjectMode; repo: string;
  stageIdx: number;            // current 0-based index into STAGES
  status: Status;
  blocker: string;             // '' when none
  cost: number; budget: number;
  age: string;                 // pre-formatted; a real API returns a timestamp
  skipCtx: boolean;            // greenfield skips the 'context' stage
  stageNote: string;
  decisions: Decision[];
}

export interface ClarifyItem    { id: string; runId: string; round: number; age: string;
  type: 'clarify'; title: string; body: string;
  suggestion: string; confidence: string; }
export interface GateItem       { id: string; runId: string; round: number; age: string;
  type: 'gate'; gate: string; title: string; body: string; }
export interface CheckRow       { name: string; kind: 'ABSOLUTE'|'ADVISORY';
  ok: boolean; detail: string; }
export interface OverrideItem   { id: string; runId: string; round: number; age: string;
  type: 'override'; gate: 'merge'; title: string; body: string;
  verdict: string; checks: CheckRow[]; }
export interface EscalationItem { id: string; runId: string; round: number; age: string;
  type: 'escalation'; title: string; body: string; analysis: string; }

export type InboxItem = ClarifyItem | GateItem | OverrideItem | EscalationItem;
```

Constants (in `constants.ts`): `STAGES` (14 names), `ARTIFACTS` (14),
`STATUS_COLORS`, gate policies. These mirror the prototype's `STAGES` /
`ARTIFACTS` / `C` exactly and match the DAG in ARCHITECTURE.md §3.

> **Note on `age`:** the prototype stores a pre-formatted string. A real
> backend will return `started_at: datetime`; formatting will move into a
> `format.ts` composable then. For this plan we keep the string to stay
> behavior-identical, and document the seam.

## 5. API client surface (`api/client.ts`)

The interface the whole UI programs against:

```ts
export interface DashboardApi {
  listRuns(): Promise<Run[]>;
  getRun(id: string): Promise<Run | undefined>;
  listInbox(): Promise<InboxItem[]>;

  answerClarify(id: string, answer: string): Promise<void>;
  decideGate(id: string, outcome: GateOutcome, comment: string): Promise<void>;
  overrideMerge(id: string, approve: boolean, justification: string): Promise<void>;
  resolveEscalation(id: string, retry: boolean, guidance: string): Promise<void>;

  startRun(input: { title: string; repo: string; mode: ProjectMode }): Promise<Run>;
}
```

- No method returns display-shaped data; components derive colors/labels
  via composables (`useStatusMeta`, `useStageState`).
- `client.ts` exports a single `api: DashboardApi` chosen by `VITE_API`.
  Default `mock`. The `http` provider (`api/http.ts`) is a stub that throws
  "not wired" — it exists only to make the swap path explicit and keep
  imports honest.

## 6. Mock provider (`api/mock/`) — the behavioral spec

The prototype's `Component` class (`design/Factory Console.dc.html`
`<script>`) **is** the spec. The mock ports it faithfully:

- **Seed:** `seedRuns()` and `seedInbox()` copied verbatim (7 runs, 5
  inbox items covering all 4 kinds) — they are the acceptance fixtures.
- **Mutators** are straight ports of the prototype's methods, with the
  same side effects on the in-memory fleet/inbox:
  - `resolveClarify` — removes item, records decision, and when no
    clarify items remain for the run, advances it to architecture
    (`stageIdx 5`, status `running`).
  - `decideGate` — `approve` advances `stageIdx+1`; `revise` bumps round
    and re-enters producing stage; `reject` fails + abandons branch.
    Requires a comment for `revise`/`reject` (toast on violation).
  - `overrideMerge` — `approve` requires justification (audited),
    advances to deploy (`stageIdx 12`); `sendBack` drops to code
    (`stageIdx 7`) for coverage.
  - `resolveEscalation` — `retry` resumes with guidance; `quarantine`
    marks the task quarantined, wave continues.
  - `startRun` — slug from title (4-segment), seeded as in prototype.
- **Live ticker:** 4s interval bumps `cost` on `running` runs
  (`simulateLive` prop), identical to `componentDidMount`.
- **Latency:** every method waits 150–300ms (randomized) so loading &
  optimistic-update paths are exercised.

## 7. Stores (Pinia)

| Store | State | Actions (→ `api`) |
|---|---|---|
| `fleet` | `runs`, `loading`, `lastFetched` | `refresh()`, `getOrLoad(id)` |
| `inbox` | `items`, `drafts`, `editing`, `loading` | `refresh()`, `setDraft`, `toggleEdit`, `answerClarify`, `decideGate`, `overrideMerge`, `resolveEscalation` |
| `run` | reuses `fleet.runs` + derives current | `startRun()` |
| `ui` | `toasts[]`, `startOpen`, start-form fields | `toast()`, `openStart`/`closeStart`, form setters |

- Decision actions fire `ui.toast(...)` on success/violation, mirroring
  the prototype's toast messages and colors exactly.
- A single `setInterval` poll (5s, matching ARCHITECTURE.md "5s polling
  v1") refreshes `fleet` + `inbox` while the tab is visible; in mock this
  just re-reads the same in-memory arrays (the ticker is what moves them).

## 8. Components

All SFCs use `<script setup lang="ts">` + scoped CSS. Inline styles from
the prototype become scoped CSS rules; pseudo-classes (`style-hover`) become
`:hover`. Component split:

- `App.vue` — `<AppHeader>` + `<RouterView>` + `<Toasts>` + `<StartRunModal>`.
- `AppHeader.vue` — brand, FLEET/INBOX tabs (router-links), counters, START.
- **fleet/** `FleetTable.vue` (header row + list), `FleetRow.vue` (the
  7-column grid row; click → `#/runs/:id`), `StageDots.vue`.
- **inbox/** `InboxList.vue`, `InboxCard.vue` (dispatches by `type` to),
  `ClarifyCard.vue`, `GateCard.vue`, `OverrideCard.vue`, `EscalationCard.vue`.
- **run/** `RunDetail.vue`, `StageSpine.vue` (14-col grid),
  `DecisionLog.vue`, `ArtifactsPanel.vue`, `BudgetPanel.vue`.
- `StartRunModal.vue`, `Toasts.vue`.

### Composables
- `useStatusMeta(run)` → `{ color, label, anim }` (port of `statusMeta`).
- `useStageState(run, i)` → `'done'|'active'|'blocked'|'failed'|'skipped'|'pending'` (port of `stageState`).
- `format.ts` — `money(n)`, `budgetPct(cost,budget)`, `budgetColor(pct)`.

## 9. Styling & fidelity

- `styles/theme.css` (global): the prototype's `<helmet>` styles verbatim —
  `html,body` bg `#0c0f14`, IBM Plex font imports, `::-webkit-scrollbar`,
  `@keyframes fc-pulse` / `fc-toast`, focus outline. Plus a small token
  table (`--c-running`, `--c-blocked`, `--c-done`, surface colors) consumed
  by scoped CSS.
- Each component's scoped CSS is a port of the prototype's inline styles
  for that element, preserving exact colors, the `grid-template-columns`
  strings (fleet's 7 cols; spine's `repeat(14,1fr)`), border-radii, and
  hover affordances.
- Fonts loaded via `<link>` in `index.html` (Google Fonts), identical to
  the prototype.

## 10. Testing — Vitest + Vue Test Utils

Focus on the high-value **pure logic** and **decision flows**; no visual
snapshots.

- `useStageState` / `useStatusMeta`: skipCtx skip, boundary states,
  status mapping.
- Mock API flows (against the in-memory provider):
  - `answerClarify` → item removed, decision logged, last-clarify
    advances the run to architecture.
  - `decideGate` approve/revise/reject stage transitions; revise/reject
    require a comment (reject otherwise).
  - `overrideMerge` approve-requires-justification; send-back to code.
  - `resolveEscalation` retry vs quarantine effects.
  - `startRun` slug derivation + prepend.
- One component smoke test: `FleetRow` renders id/title/cost and routes
  on click (mount + stubbed router).

`package.json` scripts: `dev`, `build`, `preview`, `test`, `test:run`,
`typecheck` (`vue-tsc --noEmit`).

## 11. Repo integration & conventions

- Lives under `interfaces/dashboard/frontend/`; own `package.json`,
  `.gitignore` (excludes `node_modules/`, `dist/`). **Not** wired into
  `pyproject.toml` or any Python tooling — frontend and backend stay
  independent builds.
- Adds a short `interfaces/dashboard/frontend/README.md` documenting:
  `npm install`, the four scripts, the `VITE_API` switch, and exactly how
  a future FastAPI provider replaces the mock (reimplement
  `DashboardApi`, point `VITE_API=http`, set `VITE_API_BASE`).
- Node version pinned via `.nvmrc` (LTS) for reproducible CI later.

## 12. Out of scope (explicit, for a later plan)

FastAPI service; workflow query extensions (`stages`, `pending_decisions`,
artifacts, budget — currently only `status`/`pending_gate` exist); real
Temporal wiring; API-key auth + rate limiting (`fastapi-request-pipeline`);
SSE; serving the built SPA from FastAPI; Docker; the MCP server surface
(FR-602). This plan only prepares the dashboard's frontend home and the
swap-in seam.
