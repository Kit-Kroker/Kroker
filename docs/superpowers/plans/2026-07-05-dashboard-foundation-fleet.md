# Dashboard Foundation + Fleet View — Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Vue 3 dashboard SPA at `interfaces/dashboard/frontend/` with the full data layer (types, constants, composables, mock API provider, API client, Pinia stores) and a fully working Fleet view, plus app shell (header, toasts, start-run modal, router). Inbox and Run-detail views are stubbed here and completed in Plan 2.

**Architecture:** Components → Pinia stores → `api/client.ts` (`DashboardApi` interface). Today the client resolves to an in-memory mock provider that is a line-for-line port of the React prototype's behavior (`design/Factory Console.dc.html` `<script>`). A future FastAPI provider reimplements the same interface behind `VITE_API=http`.

**Tech Stack:** Vite 5, Vue 3 (`<script setup lang="ts">`), TypeScript 5, Pinia 2, vue-router 4 (hash history), Vitest 1 + @vue/test-utils + jsdom.

## Global Constraints

- **Location:** everything lives under `interfaces/dashboard/frontend/`. Do not touch any Python file or `pyproject.toml`.
- **Node:** LTS (v20), pinned via `.nvmrc`. Package manager is **npm**.
- **Visual source of truth:** `design/Factory Console.dc.html` — colors, grid `grid-template-columns` strings, fonts, animations are ported verbatim. The dark theme base is `#0c0f14`; fonts are IBM Plex Sans/Mono (already linked in `index.html`).
- **Behavioral source of truth:** the prototype's `Component` class methods (`statusMeta`, `stageState`, `resolveClarify`, `gateDecide`, `overrideDecide`, `escalationDecide`, `submitStart`). The mock provider reproduces their observable effects exactly.
- **Type discipline:** `strict`, `noUnusedLocals`, `noUnusedParameters` on. `npm run typecheck` (`vue-tsc --noEmit`) must pass at every commit.
- **No comments in code** unless requested. No emojis.
- **Commit style:** repo uses lowercase conventional prefixes (`feat:`, `docs:`, `test:`, `chore:`, `fix:`). Stage only the files your task creates/modifies.

## File structure built by this plan

```
interfaces/dashboard/frontend/
├── .nvmrc
├── .gitignore
├── index.html
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── README.md
└── src/
    ├── main.ts
    ├── App.vue                    (shell: header + <RouterView> + toasts + modal)
    ├── App.test.ts                (boot smoke — rewritten in Task 7)
    ├── router.ts
    ├── constants.ts
    ├── vite-env.d.ts
    ├── api/
    │   ├── types.ts               (Run, InboxItem union, DashboardApi, etc.)
    │   ├── client.ts              (selectApi → mock | http stub)
    │   ├── client.test.ts
    │   └── mock/
    │       ├── index.ts           (createMockApi, tickCosts, getMockApi)
    │       └── index.test.ts
    ├── stores/
    │   ├── fleet.ts
    │   ├── inbox.ts
    │   ├── ui.ts
    │   └── stores.test.ts
    ├── composables/
    │   ├── status.ts              (statusMetaOf)
    │   ├── stageState.ts          (stageStateOf)
    │   ├── format.ts              (money, budgetPct, budgetColor)
    │   └── composables.test.ts
    ├── styles/theme.css           (global tokens, fonts, scrollbars, keyframes)
    ├── components/
    │   ├── AppHeader.vue
    │   ├── AppHeader.test.ts
    │   ├── Toasts.vue
    │   ├── Toasts.test.ts
    │   ├── StartRunModal.vue
    │   ├── StartRunModal.test.ts
    │   └── fleet/
    │       ├── FleetTable.vue
    │       ├── FleetRow.vue
    │       ├── StageDots.vue
    │       └── FleetTable.test.ts
    └── views/
        ├── FleetView.vue
        ├── InboxView.vue          (stub — Plan 2 fills cards)
        └── RunView.vue            (stub — Plan 2 fills detail)
```

---

### Task 1: Scaffold the Vite + Vue 3 + TS project

**Files:**
- Create: `interfaces/dashboard/frontend/.nvmrc`
- Create: `interfaces/dashboard/frontend/.gitignore`
- Create: `interfaces/dashboard/frontend/package.json`
- Create: `interfaces/dashboard/frontend/tsconfig.json`
- Create: `interfaces/dashboard/frontend/tsconfig.node.json`
- Create: `interfaces/dashboard/frontend/vite.config.ts`
- Create: `interfaces/dashboard/frontend/index.html`
- Create: `interfaces/dashboard/frontend/src/vite-env.d.ts`
- Create: `interfaces/dashboard/frontend/src/main.ts`
- Create: `interfaces/dashboard/frontend/src/App.vue`
- Create: `interfaces/dashboard/frontend/src/App.test.ts`

**Interfaces:**
- Produces: a building/typechecking/testable app skeleton mounting `App.vue`. Later tasks replace `App.vue` and `main.ts`.

- [ ] **Step 1: Create config + entry files**

`interfaces/dashboard/frontend/.nvmrc`:
```
20
```

`interfaces/dashboard/frontend/.gitignore`:
```
node_modules
dist
*.local
.DS_Store
coverage
```

`interfaces/dashboard/frontend/package.json`:
```json
{
  "name": "sdlc-dashboard",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "vue-tsc --noEmit"
  },
  "dependencies": {
    "pinia": "^2.1.7",
    "vue": "^3.4.21",
    "vue-router": "^4.3.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.4",
    "@vue/test-utils": "^2.4.5",
    "jsdom": "^24.0.0",
    "typescript": "^5.4.5",
    "vite": "^5.2.0",
    "vitest": "^1.6.0",
    "vue-tsc": "^2.0.13"
  }
}
```

`interfaces/dashboard/frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "preserve",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`interfaces/dashboard/frontend/tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

`interfaces/dashboard/frontend/vite.config.ts`:
```ts
/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: false,
  },
})
```

`interfaces/dashboard/frontend/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>SDLC Factory Console</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap"
      rel="stylesheet"
    />
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

`interfaces/dashboard/frontend/src/vite-env.d.ts`:
```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API?: 'mock' | 'http'
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

`interfaces/dashboard/frontend/src/main.ts` (sentinel; rewritten in Task 7):
```ts
import { createApp } from 'vue'
import App from './App.vue'

createApp(App).mount('#app')
```

`interfaces/dashboard/frontend/src/App.vue` (sentinel; rewritten in Task 7):
```vue
<script setup lang="ts"></script>

<template>
  <div data-testid="boot-sentinel">SDLC Factory Console</div>
</template>
```

- [ ] **Step 2: Write the failing boot test**

`interfaces/dashboard/frontend/src/App.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import App from './App.vue'

describe('App', () => {
  it('boots and renders the sentinel', () => {
    const w = mount(App)
    expect(w.find('[data-testid="boot-sentinel"]').text()).toBe('SDLC Factory Console')
  })
})
```

- [ ] **Step 3: Install dependencies**

Run (from `interfaces/dashboard/frontend`):
```bash
npm install
```
Expected: installs vue, vue-router, pinia, vite, vitest, etc. with no peer-dep errors.

- [ ] **Step 4: Run test, typecheck, and build to verify the skeleton is sound**

Run (from `interfaces/dashboard/frontend`):
```bash
npm run test
npm run typecheck
npm run build
```
Expected: 1 test passes; typecheck clean; `dist/` produced.

- [ ] **Step 5: Commit**

```bash
git add interfaces/dashboard/frontend
git commit -m "chore(dashboard): scaffold Vite + Vue 3 + TS app with vitest"
```

---

### Task 2: Types and constants

**Files:**
- Create: `interfaces/dashboard/frontend/src/api/types.ts`
- Create: `interfaces/dashboard/frontend/src/constants.ts`
- Create: `interfaces/dashboard/frontend/src/constants.test.ts`

**Interfaces:**
- Produces: `Run`, `Status`, `Decision`, `GateOutcome`, `ProjectMode`, `InboxKind`, `InboxItem` (union of `ClarifyItem | GateItem | OverrideItem | EscalationItem`), `CheckRow`, `StartRunInput`, `DashboardApi` — all consumed by every later task. Also `STAGES`, `ARTIFACTS`, `STATUS_COLORS`, `STAGE_LABELS`.

- [ ] **Step 1: Write the failing test**

`interfaces/dashboard/frontend/src/constants.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { STAGES, ARTIFACTS, STATUS_COLORS } from './constants'

describe('constants', () => {
  it('has 14 stages aligned with 14 artifacts', () => {
    expect(STAGES).toHaveLength(14)
    expect(ARTIFACTS).toHaveLength(14)
  })

  it('matches the DAG indices used elsewhere', () => {
    expect(STAGES[0]).toBe('intake')
    expect(STAGES[2]).toBe('context')
    expect(STAGES[5]).toBe('architecture')
    expect(STAGES[11]).toBe('quality_gate')
    expect(STAGES[13]).toBe('retro')
  })

  it('exposes the status color palette', () => {
    expect(STATUS_COLORS.running).toBe('#5b9dd9')
    expect(STATUS_COLORS.blocked).toBe('#e0b050')
    expect(STATUS_COLORS.failed).toBe('#e06c55')
    expect(STATUS_COLORS.done).toBe('#4fae7f')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- constants`
Expected: FAIL — `./constants` does not exist.

- [ ] **Step 3: Write the constants**

`interfaces/dashboard/frontend/src/constants.ts`:
```ts
export const STAGES = [
  'intake',
  'constitution',
  'context',
  'requirements',
  'clarify',
  'architecture',
  'planning',
  'code',
  'review',
  'analyze',
  'qa',
  'quality_gate',
  'deploy',
  'retro',
] as const

export type StageName = (typeof STAGES)[number]

export const ARTIFACTS = [
  'IdeaBrief',
  'Constitution',
  'CodebaseMap',
  'Requirements',
  'Clarifications',
  'Architecture',
  'TaskPlan',
  'CodeArtifact',
  'ReviewReport',
  'AnalysisReport',
  'TestReport',
  'GateReport',
  'DeployReport',
  'RunSummary',
] as const

export const STATUS_COLORS = {
  running: '#5b9dd9',
  blocked: '#e0b050',
  failed: '#e06c55',
  done: '#4fae7f',
  quarantined: '#b98fdc',
  pending: '#2a3140',
  skipped: '#1b202b',
} as const

export const STAGE_LABELS = {
  done: 'done',
  active: 'in flight',
  blocked: 'gate open',
  failed: 'failed',
  skipped: 'skipped',
  pending: '·',
} as const
```

- [ ] **Step 4: Write the API data contracts**

`interfaces/dashboard/frontend/src/api/types.ts`:
```ts
export type Status = 'running' | 'blocked' | 'failed' | 'done'
export type GateOutcome = 'approve' | 'revise' | 'reject'
export type ProjectMode = 'brownfield' | 'greenfield'
export type InboxKind = 'clarify' | 'gate' | 'override' | 'escalation'

export interface Decision {
  ts: string
  gate: string
  outcome: GateOutcome
  comment: string
  decider: string
}

export interface Run {
  id: string
  title: string
  mode: ProjectMode
  repo: string
  stageIdx: number
  status: Status
  blocker: string
  cost: number
  budget: number
  age: string
  skipCtx: boolean
  stageNote: string
  decisions: Decision[]
}

export interface ClarifyItem {
  id: string
  runId: string
  round: number
  age: string
  type: 'clarify'
  title: string
  body: string
  suggestion: string
  confidence: string
}

export interface GateItem {
  id: string
  runId: string
  round: number
  age: string
  type: 'gate'
  gate: string
  title: string
  body: string
}

export interface CheckRow {
  name: string
  kind: 'ABSOLUTE' | 'ADVISORY'
  ok: boolean
  detail: string
}

export interface OverrideItem {
  id: string
  runId: string
  round: number
  age: string
  type: 'override'
  gate: 'merge'
  title: string
  body: string
  verdict: string
  checks: CheckRow[]
}

export interface EscalationItem {
  id: string
  runId: string
  round: number
  age: string
  type: 'escalation'
  title: string
  body: string
  analysis: string
}

export type InboxItem =
  | ClarifyItem
  | GateItem
  | OverrideItem
  | EscalationItem

export interface StartRunInput {
  title: string
  repo: string
  mode: ProjectMode
}

export interface DashboardApi {
  listRuns(): Promise<Run[]>
  getRun(id: string): Promise<Run | undefined>
  listInbox(): Promise<InboxItem[]>
  answerClarify(id: string, answer: string): Promise<void>
  decideGate(id: string, outcome: GateOutcome, comment: string): Promise<void>
  overrideMerge(id: string, approve: boolean, justification: string): Promise<void>
  resolveEscalation(id: string, retry: boolean, guidance: string): Promise<void>
  startRun(input: StartRunInput): Promise<Run>
}
```

- [ ] **Step 5: Run tests and typecheck**

Run:
```bash
npm run test
npm run typecheck
```
Expected: constants tests pass; typecheck clean.

- [ ] **Step 6: Commit**

```bash
git add interfaces/dashboard/frontend/src/constants.ts interfaces/dashboard/frontend/src/constants.test.ts interfaces/dashboard/frontend/src/api/types.ts
git commit -m "feat(dashboard): add API data contracts and pipeline constants"
```

---

### Task 3: Composables (pure derivations)

**Files:**
- Create: `interfaces/dashboard/frontend/src/composables/format.ts`
- Create: `interfaces/dashboard/frontend/src/composables/status.ts`
- Create: `interfaces/dashboard/frontend/src/composables/stageState.ts`
- Create: `interfaces/dashboard/frontend/src/composables/composables.test.ts`

**Interfaces:**
- Consumes: `Run`, `Status` from `api/types`; `STATUS_COLORS` from `constants`.
- Produces:
  - `money(n: number): string`
  - `budgetPct(cost: number, budget: number): number`
  - `budgetColor(pct: number): string`
  - `StatusMeta { color: string; label: string; anim: string }`
  - `statusMetaOf(run: Pick<Run, 'status'>): StatusMeta`
  - `StageState = 'done' | 'active' | 'blocked' | 'failed' | 'skipped' | 'pending'`
  - `stageStateOf(run: Pick<Run, 'stageIdx' | 'status' | 'skipCtx'>, i: number): StageState`

- [ ] **Step 1: Write the failing tests**

`interfaces/dashboard/frontend/src/composables/composables.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { money, budgetPct, budgetColor } from './format'
import { statusMetaOf } from './status'
import { stageStateOf } from './stageState'
import type { Run } from '../api/types'

const run = (over: Partial<Run>): Run => ({
  id: 'x',
  title: 't',
  mode: 'brownfield',
  repo: 'r',
  stageIdx: 5,
  status: 'running',
  blocker: '',
  cost: 1,
  budget: 10,
  age: '1m',
  skipCtx: false,
  stageNote: '',
  decisions: [],
  ...over,
})

describe('format', () => {
  it('formats USD', () => {
    expect(money(3.1)).toBe('$3.10')
    expect(money(0)).toBe('$0.00')
  })
  it('caps budget pct at 100', () => {
    expect(budgetPct(5, 10)).toBe(50)
    expect(budgetPct(20, 10)).toBe(100)
  })
  it('colors budget by threshold', () => {
    expect(budgetColor(50)).toBe('#4fae7f')
    expect(budgetColor(70)).toBe('#e0b050')
    expect(budgetColor(90)).toBe('#e06c55')
  })
})

describe('statusMetaOf', () => {
  it('maps each status to color/label/anim', () => {
    expect(statusMetaOf(run({ status: 'running' })).label).toBe('running')
    expect(statusMetaOf(run({ status: 'blocked' })).label).toBe('awaiting human')
    expect(statusMetaOf(run({ status: 'failed' })).anim).toBe('none')
    expect(statusMetaOf(run({ status: 'done' })).color).toBe('#4fae7f')
  })
})

describe('stageStateOf', () => {
  it('marks prior stages done', () => {
    expect(stageStateOf(run({ stageIdx: 5 }), 3)).toBe('done')
  })
  it('marks the current stage active when running', () => {
    expect(stageStateOf(run({ stageIdx: 5, status: 'running' }), 5)).toBe('active')
  })
  it('marks the current stage blocked when run is blocked', () => {
    expect(stageStateOf(run({ stageIdx: 5, status: 'blocked' }), 5)).toBe('blocked')
  })
  it('skips the context stage for greenfield', () => {
    expect(stageStateOf(run({ stageIdx: 5, skipCtx: true }), 2)).toBe('skipped')
  })
  it('marks future stages pending', () => {
    expect(stageStateOf(run({ stageIdx: 5 }), 9)).toBe('pending')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test -- composables`
Expected: FAIL — modules do not exist.

- [ ] **Step 3: Implement the composables**

`interfaces/dashboard/frontend/src/composables/format.ts`:
```ts
export function money(n: number): string {
  return '$' + n.toFixed(2)
}

export function budgetPct(cost: number, budget: number): number {
  return Math.min(100, (cost / budget) * 100)
}

export function budgetColor(pct: number): string {
  if (pct > 85) return '#e06c55'
  if (pct > 60) return '#e0b050'
  return '#4fae7f'
}
```

`interfaces/dashboard/frontend/src/composables/status.ts`:
```ts
import type { Run, Status } from '../api/types'
import { STATUS_COLORS } from '../constants'

export interface StatusMeta {
  color: string
  label: string
  anim: string
}

const MAP: Record<Status, StatusMeta> = {
  running: { color: STATUS_COLORS.running, label: 'running', anim: 'fc-pulse 1.8s infinite' },
  blocked: { color: STATUS_COLORS.blocked, label: 'awaiting human', anim: 'fc-pulse 1.4s infinite' },
  failed: { color: STATUS_COLORS.failed, label: 'failed', anim: 'none' },
  done: { color: STATUS_COLORS.done, label: 'done', anim: 'none' },
}

export function statusMetaOf(run: Pick<Run, 'status'>): StatusMeta {
  return MAP[run.status] ?? MAP.running
}
```

`interfaces/dashboard/frontend/src/composables/stageState.ts`:
```ts
import type { Run } from '../api/types'

export type StageState = 'done' | 'active' | 'blocked' | 'failed' | 'skipped' | 'pending'

export function stageStateOf(
  run: Pick<Run, 'stageIdx' | 'status' | 'skipCtx'>,
  i: number,
): StageState {
  if (i === 2 && run.skipCtx) return 'skipped'
  if (i < run.stageIdx) return 'done'
  if (i === run.stageIdx) {
    if (run.status === 'blocked') return 'blocked'
    if (run.status === 'failed') return 'failed'
    if (run.status === 'done') return 'done'
    return 'active'
  }
  return 'pending'
}
```

- [ ] **Step 4: Run tests and typecheck**

Run:
```bash
npm run test
npm run typecheck
```
Expected: all composables tests pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add interfaces/dashboard/frontend/src/composables
git commit -m "feat(dashboard): add status/stage/format composables"
```

---

### Task 4: Mock API provider (the behavioral port)

**Files:**
- Create: `interfaces/dashboard/frontend/src/api/mock/index.ts`
- Create: `interfaces/dashboard/frontend/src/api/mock/index.test.ts`

**Interfaces:**
- Consumes: all types from `api/types`.
- Produces:
  - `tickCosts(runs: Run[]): Run[]` — pure cost-tick (testable).
  - `createMockApi(opts?: { simulateLive?: boolean }): DashboardApi & { dispose(): void }`
  - `getMockApi(): DashboardApi` — process-wide singleton used by `client.ts`.
  - Seeds: 7 runs and 5 inbox items identical to the prototype's `seedRuns()`/`seedInbox()`.

- [ ] **Step 1: Write the failing tests**

`interfaces/dashboard/frontend/src/api/mock/index.test.ts`:
```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createMockApi, tickCosts } from './index'
import type { Run } from '../types'

const mk = (over: Partial<Run>): Run => ({
  id: 'x', title: 't', mode: 'brownfield', repo: 'r', stageIdx: 5, status: 'running',
  blocker: '', cost: 1, budget: 10, age: '1m', skipCtx: false, stageNote: '', decisions: [],
  ...over,
})

describe('tickCosts', () => {
  it('bumps running runs and leaves others untouched', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    const runs = [mk({ id: 'a', status: 'running', cost: 1 }), mk({ id: 'b', status: 'done', cost: 5 })]
    const out = tickCosts(runs)
    expect(out[0].cost).toBeCloseTo(1.05, 5)
    expect(out[1].cost).toBe(5)
    vi.restoreAllMocks()
  })
})

describe('mock api decision flows', () => {
  let api: ReturnType<typeof createMockApi>
  beforeEach(() => {
    api = createMockApi({ simulateLive: false })
  })

  it('seeds 7 runs and 5 inbox items', async () => {
    expect(await api.listRuns()).toHaveLength(7)
    expect(await api.listInbox()).toHaveLength(5)
  })

  it('answers a clarify question and logs a decision', async () => {
    await api.answerClarify('q1', 'Use OIDC.')
    const inbox = await api.listInbox()
    expect(inbox.find((i) => i.id === 'q1')).toBeUndefined()
    const run = await api.getRun('feature-add-sso')
    expect(run?.decisions.some((d) => d.outcome === 'approve' && d.gate.includes('clarify Q1'))).toBe(true)
  })

  it('advances a run to architecture when the last clarify is answered', async () => {
    await api.answerClarify('q1', 'OIDC')
    await api.answerClarify('q2', 'Keep password behind a flag')
    const run = await api.getRun('feature-add-sso')
    expect(run?.stageIdx).toBe(5)
    expect(run?.status).toBe('running')
  })

  it('approving a gate advances the stage', async () => {
    await api.decideGate('g2', 'approve', '')
    const run = await api.getRun('feature-usage-metering')
    expect(run?.status).toBe('running')
    expect(run?.stageIdx).toBeGreaterThan(5)
  })

  it('rejecting a gate fails the branch', async () => {
    await api.decideGate('g2', 'reject', 'wrong layering')
    const run = await api.getRun('feature-usage-metering')
    expect(run?.status).toBe('failed')
  })

  it('override approve moves run to deploy (stageIdx 12)', async () => {
    await api.overrideMerge('g1', true, 'retry branches covered indirectly')
    const run = await api.getRun('feature-billing-webhooks')
    expect(run?.stageIdx).toBe(12)
    expect(run?.status).toBe('running')
  })

  it('override send-back drops run to code (stageIdx 7)', async () => {
    await api.overrideMerge('g1', false, '')
    const run = await api.getRun('feature-billing-webhooks')
    expect(run?.stageIdx).toBe(7)
  })

  it('escalation retry resumes the task', async () => {
    await api.resolveEscalation('e1', true, 'inject a clock')
    const run = await api.getRun('fix-rate-limit-retry')
    expect(run?.blocker).toContain('repair attempt 4')
  })

  it('escalation quarantine keeps the wave going', async () => {
    await api.resolveEscalation('e1', false, '')
    const run = await api.getRun('fix-rate-limit-retry')
    expect(run?.blocker).toContain('quarantined')
    expect(run?.status).toBe('running')
  })

  it('startRun slugs the title and prepends the run', async () => {
    const r = await api.startRun({ title: 'Add SSO to customer portal', repo: '', mode: 'brownfield' })
    expect(r.id).toBe('feature-add-sso-to')
    expect((await api.listRuns())[0].id).toBe(r.id)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test -- mock`
Expected: FAIL — `./index` does not exist.

- [ ] **Step 3: Implement the mock provider**

`interfaces/dashboard/frontend/src/api/mock/index.ts`:
```ts
import type {
  DashboardApi,
  GateOutcome,
  Run,
  InboxItem,
  ClarifyItem,
  GateItem,
  OverrideItem,
  EscalationItem,
  StartRunInput,
} from '../types'

export function tickCosts(runs: Run[]): Run[] {
  return runs.map((r) =>
    r.status === 'running'
      ? { ...r, cost: +(r.cost + 0.02 + Math.random() * 0.06).toFixed(2) }
      : r,
  )
}

function seedRuns(): Run[] {
  return [
    {
      id: 'feature-add-sso',
      title: 'Add SSO to customer portal',
      mode: 'brownfield',
      repo: 'git@github.com:acme/portal',
      stageIdx: 4,
      status: 'blocked',
      blocker: 'clarify gate — 2 questions',
      cost: 3.12,
      budget: 40,
      age: '2h 14m',
      skipCtx: false,
      stageNote: 'clarify: 2 low-confidence questions routed to human (gate round 1). 4 others auto-answered ≥ 0.95.',
      decisions: [
        { ts: '09:12', gate: 'clarify r1 (partial)', outcome: 'approve', comment: '4 questions auto-answered, confidence ≥ 0.95', decider: 'policy (soft)' },
      ],
    },
    {
      id: 'feature-billing-webhooks',
      title: 'Outbound webhooks for billing events',
      mode: 'brownfield',
      repo: 'git@github.com:acme/billing',
      stageIdx: 11,
      status: 'blocked',
      blocker: 'merge gate — advisory: coverage',
      cost: 18.4,
      budget: 60,
      age: '9h 03m',
      skipCtx: false,
      stageNote: 'quality_gate: absolutes green · advisory diff coverage 0.68 < 0.80 — awaiting human GateDecision.',
      decisions: [
        { ts: '02:20', gate: 'architecture r1', outcome: 'approve', comment: 'delta grounded in CodebaseMap', decider: 'human · mika' },
        { ts: '03:05', gate: 'plan r1', outcome: 'approve', comment: '7 tasks / 3 waves, DAG valid', decider: 'policy (soft)' },
        { ts: '08:44', gate: 'task T-04 repair', outcome: 'approve', comment: 'review fix loop 1/2 green', decider: 'policy' },
      ],
    },
    {
      id: 'feature-onboarding-v2',
      title: 'Self-serve onboarding flow (new service)',
      mode: 'greenfield',
      repo: 'git@github.com:acme/onboard',
      stageIdx: 7,
      status: 'running',
      blocker: '',
      cost: 9.75,
      budget: 50,
      age: '4h 41m',
      skipCtx: true,
      stageNote: 'code: wave 2/3 — 4 tasks in flight in isolated worktrees, cut from integration head (ADR-14).',
      decisions: [
        { ts: '11:02', gate: 'clarify r1', outcome: 'approve', comment: 'all suggestions accepted', decider: 'human · sam' },
        { ts: '11:38', gate: 'architecture r1', outcome: 'revise', comment: 'split auth from profile service', decider: 'human · sam' },
        { ts: '12:19', gate: 'architecture r2', outcome: 'approve', comment: '', decider: 'human · sam' },
        { ts: '12:31', gate: 'plan r1', outcome: 'approve', comment: 'confidence 0.97', decider: 'policy (soft)' },
      ],
    },
    {
      id: 'fix-rate-limit-retry',
      title: 'Fix: retry budget exhausted under burst load',
      mode: 'brownfield',
      repo: 'git@github.com:acme/gateway',
      stageIdx: 10,
      status: 'blocked',
      blocker: 'escalation — T-07 resolver 3/3',
      cost: 6.2,
      budget: 30,
      age: '6h 27m',
      skipCtx: false,
      stageNote: 'qa: T-07 red after 3 resolver attempts — escalated to human (retry-with-guidance | quarantine).',
      decisions: [{ ts: '13:15', gate: 'plan r1', outcome: 'approve', comment: '', decider: 'policy (soft)' }],
    },
    {
      id: 'feature-usage-metering',
      title: 'Usage metering for billing tiers',
      mode: 'brownfield',
      repo: 'git@github.com:acme/billing',
      stageIdx: 5,
      status: 'blocked',
      blocker: 'architecture gate — round 1',
      cost: 2.05,
      budget: 45,
      age: '1h 02m',
      skipCtx: false,
      stageNote: 'architecture: delta spec awaiting approval (adds MeteringService; 3 contracts added, 0 removed).',
      decisions: [{ ts: '14:30', gate: 'clarify r1', outcome: 'approve', comment: 'auto, confidence 0.96', decider: 'policy (soft)' }],
    },
    {
      id: 'feature-audit-export',
      title: 'Audit-trail export (events.jsonl + report)',
      mode: 'brownfield',
      repo: 'git@github.com:acme/portal',
      stageIdx: 13,
      status: 'running',
      blocker: '',
      cost: 14.02,
      budget: 40,
      age: '11h 50m',
      skipCtx: false,
      stageNote: 'retro: RunSummary building; learnings retained to Hindsight.',
      decisions: [
        { ts: '05:12', gate: 'merge r1', outcome: 'approve', comment: 'all checks green', decider: 'policy (soft)' },
        { ts: '06:01', gate: 'deploy r1', outcome: 'approve', comment: 'PR #482 merged, staging deploy', decider: 'human · mika' },
      ],
    },
    {
      id: 'feature-dark-mode',
      title: 'Dark mode for settings pages',
      mode: 'brownfield',
      repo: 'git@github.com:acme/portal',
      stageIdx: 14,
      status: 'done',
      blocker: '',
      cost: 7.88,
      budget: 30,
      age: '1d 3h',
      skipCtx: false,
      stageNote: '',
      decisions: [
        { ts: 'yday', gate: 'merge r1', outcome: 'approve', comment: '', decider: 'policy (soft)' },
        { ts: 'yday', gate: 'deploy r1', outcome: 'approve', comment: '', decider: 'human · sam' },
      ],
    },
  ]
}

function seedInbox(): InboxItem[] {
  return [
    {
      id: 'q1',
      type: 'clarify',
      runId: 'feature-add-sso',
      round: 1,
      age: '38m',
      title: 'Q1 — Which identity protocol should SSO support?',
      confidence: '0.82',
      body: 'The repo has no auth-provider abstraction. Requirements mention "enterprise SSO" but not a protocol; the CodebaseMap shows session middleware in portal/auth/session.py.',
      suggestion: 'OIDC (Authorization Code + PKCE). It fits the existing session middleware; defer SAML to a follow-up run if an enterprise customer requires it.',
    },
    {
      id: 'q2',
      type: 'clarify',
      runId: 'feature-add-sso',
      round: 1,
      age: '38m',
      title: 'Q2 — Should password login remain enabled after SSO ships?',
      confidence: '0.74',
      body: 'US-1 is silent on migration. Disabling password auth immediately would lock out users whose IdP mapping fails on first login.',
      suggestion: 'Keep password auth behind a feature flag for 2 releases, then retire it once SSO adoption is > 95%.',
    },
    {
      id: 'g2',
      type: 'gate',
      gate: 'architecture',
      runId: 'feature-usage-metering',
      round: 1,
      age: '54m',
      title: 'Architecture (delta) — usage metering',
      body: 'Adds MeteringService (event ingest + hourly rollup), modifies billing-worker to emit usage events, adds 3 contracts (UsageEvent, MeterReading, TierQuota). No removals. Grounded in CodebaseMap @ a41c9e.',
    },
    {
      id: 'g1',
      type: 'override',
      gate: 'merge',
      runId: 'feature-billing-webhooks',
      round: 1,
      age: '1h 12m',
      title: 'Merge gate — advisory check needs a decision',
      body: 'All absolute checks pass. One advisory check fails; merging requires an audited human override (FR-106).',
      verdict: 'MergeVerdict 0.91 — approve. Uncovered lines are retry/backoff branches exercised indirectly by the integration suite; direct unit coverage would need an injected clock.',
      checks: [
        { name: 'lint', kind: 'ABSOLUTE', ok: true, detail: 'clean' },
        { name: 'security (critical)', kind: 'ABSOLUTE', ok: true, detail: '0 critical findings' },
        { name: 'build / integration', kind: 'ABSOLUTE', ok: true, detail: 'green · 4m12s' },
        { name: 'diff coverage', kind: 'ADVISORY', ok: false, detail: '0.68 — target 0.80' },
        { name: 'criterion→test traceability', kind: 'ADVISORY', ok: true, detail: '9/9 criteria mapped' },
        { name: 'review severity', kind: 'ADVISORY', ok: true, detail: 'max severity: medium' },
      ],
    },
    {
      id: 'e1',
      type: 'escalation',
      runId: 'fix-rate-limit-retry',
      round: 1,
      age: '2h 05m',
      title: 'T-07 "retry budget accounting" — resolver exhausted (3/3)',
      body: 'QA fix loop hit MAX_REPAIR_ATTEMPTS. The task branch stays parked on its worktree; wave 3 is holding.',
      analysis: 'test_retry_budget flakes on wall-clock timing. A reliable fix needs an injected clock in RateLimiter, but rate_limiter/core.py is outside the task’s declared file scope. Recommend widening scope or quarantining.',
    },
  ]
}

export interface MockOptions {
  simulateLive?: boolean
}

export function createMockApi(opts: MockOptions = {}): DashboardApi & { dispose(): void } {
  const simulateLive = opts.simulateLive ?? true
  let runs: Run[] = seedRuns()
  let inbox: InboxItem[] = seedInbox()

  const delay = () => new Promise<void>((r) => setTimeout(r, 120 + Math.random() * 180))

  const now = () => {
    const d = new Date()
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
  }
  const patchRun = (id: string, patch: Partial<Run> | ((r: Run) => Partial<Run>)) => {
    runs = runs.map((r) => (r.id === id ? { ...r, ...(typeof patch === 'function' ? patch(r) : patch) } : r))
  }
  const addDecision = (runId: string, d: { ts?: string; gate: string; outcome: GateOutcome; comment?: string; decider?: string }) =>
    patchRun(runId, (r) => ({
      decisions: [...r.decisions, { ts: now(), decider: 'human · you', comment: '', ...d }],
    }))
  const removeItem = (id: string) => {
    inbox = inbox.filter((i) => i.id !== id)
  }
  const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x))

  const api: DashboardApi & { dispose(): void } = {
    async listRuns() {
      await delay()
      return clone(runs)
    },
    async getRun(id: string) {
      await delay()
      const r = runs.find((x) => x.id === id)
      return r ? clone(r) : undefined
    },
    async listInbox() {
      await delay()
      return clone(inbox)
    },

    async answerClarify(id: string, answer: string) {
      await delay()
      const it = inbox.find((i) => i.id === id) as ClarifyItem | undefined
      if (!it) return
      removeItem(id)
      addDecision(it.runId, {
        gate: `clarify Q${it.id.slice(1)} r${it.round}`,
        outcome: 'approve',
        comment: answer.length > 60 ? answer.slice(0, 57) + '…' : answer,
      })
      const left = inbox.some((i) => i.runId === it.runId && i.type === 'clarify')
      if (!left) {
        patchRun(it.runId, { status: 'running', stageIdx: 5, blocker: '', stageNote: 'architecture: drafting delta spec from Clarifications @ r1.' })
      }
    },

    async decideGate(id: string, outcome: GateOutcome, comment: string) {
      await delay()
      const it = inbox.find((i) => i.id === id && i.type === 'gate') as GateItem | undefined
      if (!it) return
      removeItem(id)
      addDecision(it.runId, { gate: `${it.gate} r${it.round}`, outcome, comment })
      if (outcome === 'approve') {
        patchRun(it.runId, (r) => ({ status: 'running', stageIdx: r.stageIdx + 1, blocker: '', stageNote: 'gate approved — pipeline resumed.' }))
      } else if (outcome === 'revise') {
        patchRun(it.runId, { status: 'running', blocker: `revising — round ${it.round + 1}`, stageNote: `revise: producing stage re-entered with your comments (round ${it.round + 1} of MAX_GATE_ROUNDS=2).` })
      } else {
        patchRun(it.runId, { status: 'failed', blocker: `rejected at ${it.gate}`, stageNote: 'branch abandoned — rejection recorded with identity + timestamp.' })
      }
    },

    async overrideMerge(id: string, approve: boolean, justification: string) {
      await delay()
      const it = inbox.find((i) => i.id === id && i.type === 'override') as OverrideItem | undefined
      if (!it) return
      removeItem(id)
      if (approve) {
        addDecision(it.runId, { gate: `merge r${it.round}`, outcome: 'approve', comment: `ADVISORY OVERRIDE: ${justification}`, decider: 'human · you (override)' })
        patchRun(it.runId, { status: 'running', stageIdx: 12, blocker: '', stageNote: 'deploy: DeployPlan proposed — PR opened against main.' })
      } else {
        addDecision(it.runId, { gate: `merge r${it.round}`, outcome: 'revise', comment: justification || 'raise diff coverage to 0.80' })
        patchRun(it.runId, { status: 'running', stageIdx: 7, blocker: 'revising — coverage', stageNote: 'code: developer session resumed to add coverage for retry/backoff branches.' })
      }
    },

    async resolveEscalation(id: string, retry: boolean, guidance: string) {
      await delay()
      const it = inbox.find((i) => i.id === id && i.type === 'escalation') as EscalationItem | undefined
      if (!it) return
      removeItem(id)
      if (retry) {
        addDecision(it.runId, { gate: 'escalation T-07', outcome: 'approve', comment: `retry w/ guidance: ${guidance || '(none)'}` })
        patchRun(it.runId, { status: 'running', blocker: 'repair attempt 4 (guided)', stageNote: 'qa: resolver resumed same harness session with your guidance.' })
      } else {
        addDecision(it.runId, { gate: 'escalation T-07', outcome: 'reject', comment: guidance ? `quarantined: ${guidance}` : 'quarantined' })
        patchRun(it.runId, { status: 'running', blocker: 'T-07 quarantined', stageNote: 'qa: T-07 quarantined; remaining tasks proceed — plan marked partial.' })
      }
    },

    async startRun(input: StartRunInput) {
      await delay()
      const t = input.title.trim()
      const id = 'feature-' + t
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '')
        .split('-')
        .slice(0, 4)
        .join('-')
      const run: Run = {
        id,
        title: t,
        mode: input.mode,
        repo: input.repo || 'git@github.com:acme/portal',
        stageIdx: 3,
        status: 'running',
        blocker: '',
        cost: 0.04,
        budget: 40,
        age: 'just now',
        skipCtx: input.mode === 'greenfield',
        stageNote: 'requirements: Product agent drafting stories from IdeaBrief.',
        decisions: [],
      }
      runs = [run, ...runs]
      return clone(run)
    },

    dispose() {
      if (timer) clearInterval(timer)
    },
  }

  let timer: ReturnType<typeof setInterval> | null = null
  if (simulateLive && typeof window !== 'undefined') {
    timer = setInterval(() => {
      runs = tickCosts(runs)
    }, 4000)
  }

  return api
}

let singleton: DashboardApi | null = null
export function getMockApi(): DashboardApi {
  if (!singleton) singleton = createMockApi({ simulateLive: true })
  return singleton
}
```

- [ ] **Step 4: Run tests and typecheck**

Run:
```bash
npm run test
npm run typecheck
```
Expected: all mock tests pass (10+ assertions); typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add interfaces/dashboard/frontend/src/api/mock
git commit -m "feat(dashboard): in-memory mock API provider ported from the prototype"
```

---

### Task 5: API client (provider switch)

**Files:**
- Create: `interfaces/dashboard/frontend/src/api/client.ts`
- Create: `interfaces/dashboard/frontend/src/api/client.test.ts`

**Interfaces:**
- Consumes: `DashboardApi` from `api/types`; `createMockApi`/`getMockApi` from `api/mock`.
- Produces:
  - `selectApi(mode: 'mock' | 'http'): DashboardApi`
  - `api: DashboardApi` — resolved from `import.meta.env.VITE_API` (default `mock`).

- [ ] **Step 1: Write the failing test**

`interfaces/dashboard/frontend/src/api/client.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { selectApi } from './client'

describe('selectApi', () => {
  it('mock provider seeds 7 runs', async () => {
    const api = selectApi('mock')
    expect(await api.listRuns()).toHaveLength(7)
  })

  it('http provider rejects (not wired)', async () => {
    const api = selectApi('http')
    await expect(api.listRuns()).rejects.toThrow(/not wired/)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- client`
Expected: FAIL — `./client` does not exist.

- [ ] **Step 3: Implement the client**

`interfaces/dashboard/frontend/src/api/client.ts`:
```ts
import type { DashboardApi } from './types'
import { getMockApi } from './mock'

const notWired = (method: string) => () =>
  Promise.reject(new Error(`Dashboard http provider not wired (VITE_API=http): ${method}`))

function httpApi(): DashboardApi {
  return {
    listRuns: notWired('listRuns'),
    getRun: notWired('getRun'),
    listInbox: notWired('listInbox'),
    answerClarify: notWired('answerClarify'),
    decideGate: notWired('decideGate'),
    overrideMerge: notWired('overrideMerge'),
    resolveEscalation: notWired('resolveEscalation'),
    startRun: notWired('startRun'),
  }
}

export function selectApi(mode: 'mock' | 'http'): DashboardApi {
  return mode === 'http' ? httpApi() : getMockApi()
}

export const api: DashboardApi = selectApi(import.meta.env.VITE_API === 'http' ? 'http' : 'mock')
```

- [ ] **Step 4: Run tests and typecheck**

Run:
```bash
npm run test
npm run typecheck
```
Expected: client tests pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add interfaces/dashboard/frontend/src/api/client.ts interfaces/dashboard/frontend/src/api/client.test.ts
git commit -m "feat(dashboard): API client with mock/http provider switch"
```

---

### Task 6: Pinia stores (fleet, inbox, ui)

**Files:**
- Create: `interfaces/dashboard/frontend/src/stores/fleet.ts`
- Create: `interfaces/dashboard/frontend/src/stores/inbox.ts`
- Create: `interfaces/dashboard/frontend/src/stores/ui.ts`
- Create: `interfaces/dashboard/frontend/src/stores/stores.test.ts`

**Interfaces:**
- Consumes: `api` from `api/client`; types from `api/types`.
- Produces:
  - `useFleetStore()` → `{ runs, loading, lastFetched, refresh(), getOrLoad(id), startRun(input), blockedCount, activeCount, totalCost }`
  - `useInboxStore()` → `{ items, drafts, editing, loading, refresh(), setDraft(id,v), toggleEdit(id) }` (decision *actions* are added in Plan 2 alongside the cards)
  - `useUiStore()` → `{ toasts, startOpen, startTitle, startRepo, startMode, toast(msg,color?), openStart(), closeStart(), resetStartForm() }` and type `Toast`

- [ ] **Step 1: Write the failing tests**

`interfaces/dashboard/frontend/src/stores/stores.test.ts`:
```ts
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api/client', () => {
  const fakeRuns = [{ id: 'r1', status: 'blocked' }, { id: 'r2', status: 'running' }]
  const api = {
    listRuns: vi.fn(async () => fakeRuns),
    listInbox: vi.fn(async () => [{ id: 'q1', type: 'clarify' }]),
    startRun: vi.fn(async (input: { title: string }) => ({ id: 'feature-new', title: input.title })),
  }
  return { api }
})

import { useFleetStore } from './fleet'
import { useInboxStore } from './inbox'
import { useUiStore } from './ui'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('fleet store', () => {
  it('refresh loads runs', async () => {
    const fleet = useFleetStore()
    await fleet.refresh()
    expect(fleet.runs).toHaveLength(2)
    expect(fleet.blockedCount).toBe(1)
    expect(fleet.activeCount).toBe(2)
  })

  it('getOrLoad finds by id', async () => {
    const fleet = useFleetStore()
    await fleet.refresh()
    expect(fleet.getOrLoad('r2')?.id).toBe('r2')
  })

  it('startRun refreshes the fleet', async () => {
    const fleet = useFleetStore()
    await fleet.startRun({ title: 'New', repo: '', mode: 'brownfield' })
    expect(fleet.runs).toHaveLength(2)
  })
})

describe('inbox store', () => {
  it('refresh loads items', async () => {
    const inbox = useInboxStore()
    await inbox.refresh()
    expect(inbox.items).toHaveLength(1)
  })
  it('setDraft and toggleEdit manage UI state', () => {
    const inbox = useInboxStore()
    inbox.setDraft('q1', 'hello')
    expect(inbox.drafts['q1']).toBe('hello')
    inbox.toggleEdit('q1')
    expect(inbox.editing['q1']).toBe(true)
  })
})

describe('ui store', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('toasts appear and auto-dismiss', () => {
    const ui = useUiStore()
    ui.toast('hi')
    expect(ui.toasts).toHaveLength(1)
    vi.advanceTimersByTime(4000)
    expect(ui.toasts).toHaveLength(0)
  })

  it('openStart/closeStart toggle the modal', () => {
    const ui = useUiStore()
    ui.openStart()
    expect(ui.startOpen).toBe(true)
    ui.closeStart()
    expect(ui.startOpen).toBe(false)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test -- stores`
Expected: FAIL — store modules do not exist.

- [ ] **Step 3: Implement the stores**

`interfaces/dashboard/frontend/src/stores/fleet.ts`:
```ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'
import type { Run, StartRunInput } from '../api/types'

export const useFleetStore = defineStore('fleet', () => {
  const runs = ref<Run[]>([])
  const loading = ref(false)
  const lastFetched = ref<number | null>(null)

  async function refresh() {
    loading.value = true
    try {
      runs.value = await api.listRuns()
    } finally {
      loading.value = false
      lastFetched.value = Date.now()
    }
  }

  function getOrLoad(id: string): Run | undefined {
    return runs.value.find((r) => r.id === id)
  }

  async function startRun(input: StartRunInput) {
    await api.startRun(input)
    await refresh()
  }

  const blockedCount = computed(() => runs.value.filter((r) => r.status === 'blocked').length)
  const activeCount = computed(() => runs.value.filter((r) => r.status === 'running' || r.status === 'blocked').length)
  const totalCost = computed(() => +runs.value.reduce((a, r) => a + r.cost, 0).toFixed(2))

  return { runs, loading, lastFetched, refresh, getOrLoad, startRun, blockedCount, activeCount, totalCost }
})
```

`interfaces/dashboard/frontend/src/stores/inbox.ts`:
```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import type { InboxItem } from '../api/types'

export const useInboxStore = defineStore('inbox', () => {
  const items = ref<InboxItem[]>([])
  const drafts = ref<Record<string, string>>({})
  const editing = ref<Record<string, boolean>>({})
  const loading = ref(false)

  async function refresh() {
    loading.value = true
    try {
      items.value = await api.listInbox()
    } finally {
      loading.value = false
    }
  }

  function setDraft(id: string, v: string) {
    drafts.value[id] = v
  }
  function toggleEdit(id: string) {
    editing.value[id] = !editing.value[id]
  }

  return { items, drafts, editing, loading, refresh, setDraft, toggleEdit }
})
```

`interfaces/dashboard/frontend/src/stores/ui.ts`:
```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ProjectMode } from '../api/types'

export interface Toast {
  id: number
  msg: string
  color: string
}

export const useUiStore = defineStore('ui', () => {
  const toasts = ref<Toast[]>([])
  const startOpen = ref(false)
  const startTitle = ref('')
  const startRepo = ref('')
  const startMode = ref<ProjectMode>('brownfield')
  let next = 1

  function toast(msg: string, color = '#4fae7f') {
    const id = next++
    toasts.value.push({ id, msg, color })
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id)
    }, 3800)
  }

  function openStart() {
    startOpen.value = true
  }
  function closeStart() {
    startOpen.value = false
  }
  function resetStartForm() {
    startTitle.value = ''
    startRepo.value = ''
    startMode.value = 'brownfield'
  }

  return { toasts, startOpen, startTitle, startRepo, startMode, toast, openStart, closeStart, resetStartForm }
})
```

- [ ] **Step 4: Run tests and typecheck**

Run:
```bash
npm run test
npm run typecheck
```
Expected: store tests pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add interfaces/dashboard/frontend/src/stores
git commit -m "feat(dashboard): Pinia stores (fleet, inbox, ui)"
```

---

### Task 7: App shell — theme, router, views, mounted App

**Files:**
- Create: `interfaces/dashboard/frontend/src/styles/theme.css`
- Create: `interfaces/dashboard/frontend/src/router.ts`
- Create: `interfaces/dashboard/frontend/src/views/FleetView.vue`
- Create: `interfaces/dashboard/frontend/src/views/InboxView.vue`
- Create: `interfaces/dashboard/frontend/src/views/RunView.vue`
- Modify: `interfaces/dashboard/frontend/src/main.ts`
- Modify: `interfaces/dashboard/frontend/src/App.vue` (replace sentinel)
- Modify: `interfaces/dashboard/frontend/src/App.test.ts` (replace boot test with plugin-mounted shell test)

**Interfaces:**
- Consumes: `useFleetStore`, `useInboxStore` (mounted refresh + 5s poll); router links `/`, `/inbox`, `/runs/:id`.
- Produces: a mountable shell `<App>` that refreshes both stores on mount, polls every 5s while visible, and renders `<AppHeader>` + `<RouterView>` + `<Toasts>` + `<StartRunModal>`. Stub views render a placeholder. (The header/toasts/modal components come from Tasks 8–10; this task uses them via imports — so execute Tasks 8–10 before this one if running strictly linearly, OR temporarily inline minimal placeholders. The recommended order is: do Tasks 8, 9, 10 first, then Task 7. The plan numbers them 7–10 by layer, but tasks 8–10 have no dependency on Task 7's router/views except the RouterLink usage which is satisfied by vue-router. **Execute Task 7 after Tasks 8, 9, 10.**)

> **Execution order note:** Tasks 8 (AppHeader), 9 (Toasts), 10 (StartRunModal) must be implemented **before** Task 7, because `App.vue` imports them. Do Tasks 8 → 9 → 10 → 7 in that order.

- [ ] **Step 1: Write the theme CSS**

`interfaces/dashboard/frontend/src/styles/theme.css` (port of the prototype's `<helmet>` styles):
```css
html,
body {
  margin: 0;
  padding: 0;
  background: #0c0f14;
}
* {
  box-sizing: border-box;
}
::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}
::-webkit-scrollbar-thumb {
  background: #2a3140;
  border-radius: 5px;
  border: 2px solid #0c0f14;
}
::-webkit-scrollbar-track {
  background: transparent;
}
@keyframes fc-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}
@keyframes fc-toast {
  from {
    transform: translateY(8px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}
textarea:focus,
input:focus {
  outline: 1px solid #4a6da8;
}
```

- [ ] **Step 2: Create the router**

`interfaces/dashboard/frontend/src/router.ts`:
```ts
import { createRouter, createWebHashHistory } from 'vue-router'
import FleetView from './views/FleetView.vue'
import InboxView from './views/InboxView.vue'
import RunView from './views/RunView.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'fleet', component: FleetView },
    { path: '/inbox', name: 'inbox', component: InboxView },
    { path: '/runs/:id', name: 'run', component: RunView, props: true },
  ],
})
```

- [ ] **Step 3: Create the three views (FleetView is a placeholder here; Task 11 fleshes it out)**

`interfaces/dashboard/frontend/src/views/FleetView.vue`:
```vue
<script setup lang="ts"></script>

<template>
  <main data-testid="fleet-view" data-screen-label="Fleet" class="view">
    <div class="hint">Fleet view — implemented in Task 11.</div>
  </main>
</template>

<style scoped>
.view {
  flex: 1;
  overflow: auto;
  padding: 20px 20px 40px;
}
.hint {
  color: #5d6675;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
}
</style>
```

`interfaces/dashboard/frontend/src/views/InboxView.vue` (stub; Plan 2 fills the cards):
```vue
<script setup lang="ts"></script>

<template>
  <main data-testid="inbox-view" data-screen-label="Decision inbox" class="view">
    <div class="hint">Decision inbox — implemented in Plan 2.</div>
  </main>
</template>

<style scoped>
.view {
  flex: 1;
  overflow: auto;
  padding: 20px 20px 60px;
}
.hint {
  color: #5d6675;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
}
</style>
```

`interfaces/dashboard/frontend/src/views/RunView.vue` (stub; Plan 2 fills the detail):
```vue
<script setup lang="ts">
defineProps<{ id: string }>()
</script>

<template>
  <main data-testid="run-view" data-screen-label="Run detail" class="view">
    <div class="hint">Run detail for {{ id }} — implemented in Plan 2.</div>
  </main>
</template>

<style scoped>
.view {
  flex: 1;
  overflow: auto;
  padding: 20px 20px 60px;
}
.hint {
  color: #5d6675;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
}
</style>
```

- [ ] **Step 4: Replace `App.vue` with the shell**

`interfaces/dashboard/frontend/src/App.vue`:
```vue
<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useFleetStore } from './stores/fleet'
import { useInboxStore } from './stores/inbox'
import AppHeader from './components/AppHeader.vue'
import Toasts from './components/Toasts.vue'
import StartRunModal from './components/StartRunModal.vue'

const fleet = useFleetStore()
const inbox = useInboxStore()
let pollId: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await Promise.all([fleet.refresh(), inbox.refresh()])
  pollId = setInterval(() => {
    if (document.visibilityState === 'visible') {
      fleet.refresh()
      inbox.refresh()
    }
  }, 5000)
})

onUnmounted(() => {
  if (pollId) clearInterval(pollId)
})
</script>

<template>
  <div class="console">
    <AppHeader />
    <RouterView />
    <Toasts />
    <StartRunModal />
  </div>
</template>

<style scoped>
.console {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #0c0f14;
  color: #d9dfe9;
  font-family: 'IBM Plex Sans', sans-serif;
  font-size: 13px;
  overflow: hidden;
}
</style>
```

- [ ] **Step 5: Replace `main.ts` to wire Pinia + router + theme**

`interfaces/dashboard/frontend/src/main.ts`:
```ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import './styles/theme.css'

createApp(App).use(createPinia()).use(router).mount('#app')
```

- [ ] **Step 6: Rewrite the App boot test to mount the shell**

`interfaces/dashboard/frontend/src/App.test.ts` (replace the sentinel boot test from Task 1):
```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import App from './App.vue'
import { router } from './router'

vi.mock('./api/client', () => ({
  api: {
    listRuns: vi.fn(async () => []),
    listInbox: vi.fn(async () => []),
  },
}))

beforeEach(() => setActivePinia(createPinia()))

describe('App shell', () => {
  it('mounts and renders the header brand', async () => {
    const w = mount(App, { global: { plugins: [router] } })
    await new Promise((r) => setTimeout(r, 0))
    expect(w.text()).toContain('SDLC·FACTORY')
  })
})
```

- [ ] **Step 7: Run tests and typecheck**

Run:
```bash
npm run test
npm run typecheck
```
Expected: App shell test passes (header renders); all prior tests still pass; typecheck clean. (Requires Tasks 8–10 components to exist.)

- [ ] **Step 8: Commit**

```bash
git add interfaces/dashboard/frontend/src
git commit -m "feat(dashboard): app shell — router, theme, mounted stores with 5s poll"
```

---

### Task 8: AppHeader

**Files:**
- Create: `interfaces/dashboard/frontend/src/components/AppHeader.vue`
- Create: `interfaces/dashboard/frontend/src/components/AppHeader.test.ts`

**Interfaces:**
- Consumes: `useFleetStore` (`activeCount`, `totalCost`), `useInboxStore` (`items` length), `useUiStore` (`openStart`).
- Produces: a header with brand, FLEET/INBOX router-link tabs (INBOX shows a count badge when items exist), counters, and a `+ START RUN` button that opens the modal.

- [ ] **Step 1: Write the failing test**

`interfaces/dashboard/frontend/src/components/AppHeader.test.ts`:
```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AppHeader from './AppHeader.vue'
import { useFleetStore } from '../stores/fleet'
import { useInboxStore } from '../stores/inbox'
import { useUiStore } from '../stores/ui'

const RouterLinkStub = { template: '<a><slot /></a>' }

beforeEach(() => setActivePinia(createPinia()))

describe('AppHeader', () => {
  it('shows the inbox badge count from the store', () => {
    const inbox = useInboxStore()
    inbox.items = [
      { id: 'q1', type: 'clarify', runId: 'r', round: 1, age: '1m', title: 't', body: 'b', suggestion: 's', confidence: '0.8' },
      { id: 'g1', type: 'gate', gate: 'merge', runId: 'r', round: 1, age: '1m', title: 't', body: 'b' },
    ] as any
    const fleet = useFleetStore()
    fleet.runs = [{ id: 'r1', status: 'running', cost: 2 } as any, { id: 'r2', status: 'blocked', cost: 3 } as any]

    const w = mount(AppHeader, { global: { stubs: { RouterLink: RouterLinkStub } } })
    expect(w.text()).toContain('INBOX')
    expect(w.find('[data-testid="inbox-count"]').text()).toBe('2')
    expect(w.text()).toContain('$5.00')
  })

  it('START button opens the modal', async () => {
    const ui = useUiStore()
    const w = mount(AppHeader, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await w.find('[data-testid="start-btn"]').trigger('click')
    expect(ui.startOpen).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- AppHeader`
Expected: FAIL — component does not exist.

- [ ] **Step 3: Implement AppHeader**

`interfaces/dashboard/frontend/src/components/AppHeader.vue`:
```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useFleetStore } from '../stores/fleet'
import { useInboxStore } from '../stores/inbox'
import { useUiStore } from '../stores/ui'
import { money } from '../composables/format'

const fleet = useFleetStore()
const inbox = useInboxStore()
const ui = useUiStore()

const inboxCount = computed(() => inbox.items.length)
const hasInbox = computed(() => inboxCount.value > 0)
const totalCost = computed(() => money(fleet.totalCost))
</script>

<template>
  <header class="hdr">
    <div class="brand">
      <span class="mark">SDLC·FACTORY</span>
      <span class="sub">temporal · ai-sdlc queue</span>
    </div>
    <nav class="tabs">
      <RouterLink to="/" class="tab" active-class="tab-active">FLEET</RouterLink>
      <RouterLink to="/inbox" class="tab" active-class="tab-active">
        INBOX
        <span v-if="hasInbox" data-testid="inbox-count" class="badge">{{ inboxCount }}</span>
      </RouterLink>
    </nav>
    <div class="spacer" />
    <div class="stats">
      <span>runs <b>{{ fleet.activeCount }}</b>/50</span>
      <span>spend today <b>{{ totalCost }}</b></span>
      <button data-testid="start-btn" class="start" @click="ui.openStart()">+ START RUN</button>
    </div>
  </header>
</template>

<style scoped>
.hdr {
  flex: none;
  height: 52px;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 20px;
  background: #090b0f;
  border-bottom: 1px solid #1e242f;
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.mark {
  font-family: 'IBM Plex Mono', monospace;
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.08em;
  color: #e8edf5;
}
.sub {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10.5px;
  color: #4d5665;
}
.tabs {
  display: flex;
  gap: 4px;
  height: 100%;
}
.tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  height: 100%;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
  letter-spacing: 0.04em;
  color: #7d8697;
  border-bottom: 2px solid transparent;
  text-decoration: none;
  cursor: pointer;
}
.tab:hover {
  color: #e8edf5;
}
.tab-active {
  color: #e8edf5;
  border-bottom-color: #e0b050;
}
.badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #e0b050;
  color: #1a1405;
  border-radius: 9px;
  font-size: 10.5px;
  font-weight: 600;
}
.spacer {
  flex: 1;
}
.stats {
  display: flex;
  align-items: center;
  gap: 18px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  color: #7d8697;
}
.stats b {
  color: #d9dfe9;
}
.start {
  cursor: pointer;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  font-weight: 600;
  padding: 7px 14px;
  background: #e0b050;
  color: #1a1405;
  border: none;
  border-radius: 4px;
}
.start:hover {
  background: #ecc06a;
}
</style>
```

- [ ] **Step 4: Run tests and typecheck**

Run:
```bash
npm run test
npm run typecheck
```
Expected: AppHeader tests pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add interfaces/dashboard/frontend/src/components/AppHeader.vue interfaces/dashboard/frontend/src/components/AppHeader.test.ts
git commit -m "feat(dashboard): app header with tabs, inbox badge, start button"
```

---

### Task 9: Toasts

**Files:**
- Create: `interfaces/dashboard/frontend/src/components/Toasts.vue`
- Create: `interfaces/dashboard/frontend/src/components/Toasts.test.ts`

**Interfaces:**
- Consumes: `useUiStore` (`toasts`).
- Produces: a fixed-position stack rendering each toast (`msg`, `color` left-border) with the `fc-toast` animation.

- [ ] **Step 1: Write the failing test**

`interfaces/dashboard/frontend/src/components/Toasts.test.ts`:
```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Toasts from './Toasts.vue'
import { useUiStore } from '../stores/ui'

beforeEach(() => setActivePinia(createPinia()))

describe('Toasts', () => {
  it('renders each toast from the ui store', () => {
    const ui = useUiStore()
    ui.toasts.push({ id: 1, msg: 'saved', color: '#4fae7f' })
    ui.toasts.push({ id: 2, msg: 'rejected', color: '#e06c55' })
    const w = mount(Toasts)
    const items = w.findAll('[data-testid="toast"]')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('saved')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- Toasts`
Expected: FAIL — component does not exist.

- [ ] **Step 3: Implement Toasts**

`interfaces/dashboard/frontend/src/components/Toasts.vue`:
```vue
<script setup lang="ts">
import { useUiStore } from '../stores/ui'
const ui = useUiStore()
</script>

<template>
  <div class="stack">
    <div
      v-for="t in ui.toasts"
      :key="t.id"
      data-testid="toast"
      class="toast"
      :style="{ borderLeftColor: t.color }"
    >
      {{ t.msg }}
    </div>
  </div>
</template>

<style scoped>
.stack {
  position: fixed;
  right: 18px;
  bottom: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 60;
  pointer-events: none;
}
.toast {
  background: #161c26;
  border: 1px solid #2a3140;
  border-left: 3px solid #4fae7f;
  border-radius: 5px;
  padding: 10px 14px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  color: #c8cfdb;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  animation: fc-toast 0.18s ease-out;
}
</style>
```

- [ ] **Step 4: Run tests and typecheck**

Run:
```bash
npm run test
npm run typecheck
```
Expected: Toasts test passes; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add interfaces/dashboard/frontend/src/components/Toasts.vue interfaces/dashboard/frontend/src/components/Toasts.test.ts
git commit -m "feat(dashboard): toast stack"
```

---

### Task 10: StartRunModal

**Files:**
- Create: `interfaces/dashboard/frontend/src/components/StartRunModal.vue`
- Create: `interfaces/dashboard/frontend/src/components/StartRunModal.test.ts`

**Interfaces:**
- Consumes: `useUiStore` (`startOpen`, `startTitle`, `startRepo`, `startMode`, `closeStart`, `resetStartForm`, `toast`) and `useFleetStore` (`startRun`).
- Produces: a modal bound to `ui.startOpen` with title/repo inputs and a brownfield/greenfield mode toggle; `START` validates (title required → toast on empty), calls `fleet.startRun`, toasts `Run started — <id>`, resets the form, and closes. Backdrop click closes; inner click is stopped.

- [ ] **Step 1: Write the failing test**

`interfaces/dashboard/frontend/src/components/StartRunModal.test.ts`:
```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import StartRunModal from './StartRunModal.vue'
import { useUiStore } from '../stores/ui'
import { useFleetStore } from '../stores/fleet'

vi.mock('../api/client', () => ({
  api: {
    listRuns: vi.fn(async () => []),
    startRun: vi.fn(async (input: { title: string; repo: string; mode: string }) => ({
      id: 'feature-add-sso', title: input.title,
    })),
  },
}))

beforeEach(() => setActivePinia(createPinia()))

describe('StartRunModal', () => {
  it('renders nothing when the modal is closed', () => {
    const w = mount(StartRunModal)
    expect(w.find('[data-testid="modal-card"]').exists()).toBe(false)
  })

  it('requires a title before submitting', async () => {
    const ui = useUiStore()
    ui.openStart()
    const w = mount(StartRunModal)
    await w.find('[data-testid="submit"]').trigger('click')
    expect(ui.toasts.some((t) => t.msg.includes('Title required'))).toBe(true)
  })

  it('starts a run, toasts, and closes', async () => {
    const ui = useUiStore()
    const fleet = useFleetStore()
    ui.openStart()
    ui.startTitle = 'Add SSO'
    const w = mount(StartRunModal)
    await w.find('[data-testid="submit"]').trigger('click')
    await flushPromises()
    expect(ui.toasts.some((t) => t.msg.includes('feature-add-sso'))).toBe(true)
    expect(ui.startOpen).toBe(false)
    expect(fleet.runs.find((r) => r.id === 'feature-add-sso')).toBeTruthy()
  })

  it('backdrop click closes the modal', async () => {
    const ui = useUiStore()
    ui.openStart()
    const w = mount(StartRunModal)
    await w.find('[data-testid="backdrop"]').trigger('click')
    expect(ui.startOpen).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- StartRunModal`
Expected: FAIL — component does not exist.

- [ ] **Step 3: Implement StartRunModal**

`interfaces/dashboard/frontend/src/components/StartRunModal.vue`:
```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useUiStore } from '../stores/ui'
import { useFleetStore } from '../stores/fleet'
import type { ProjectMode } from '../api/types'

const ui = useUiStore()
const fleet = useFleetStore()

const isBrown = computed(() => ui.startMode === 'brownfield')
function setMode(m: ProjectMode) {
  ui.startMode = m
}
async function submit() {
  const title = ui.startTitle.trim()
  if (!title) {
    ui.toast('Title required', '#e0b050')
    return
  }
  await fleet.startRun({ title, repo: ui.startRepo, mode: ui.startMode })
  ui.toast('Run started', '#5b9dd9')
  ui.resetStartForm()
  ui.closeStart()
}
</script>

<template>
  <div
    v-if="ui.startOpen"
    data-testid="backdrop"
    class="backdrop"
    @click="ui.closeStart()"
  >
    <div data-testid="modal-card" class="card" @click.stop>
      <div class="title">START RUN</div>

      <label class="lbl">FEATURE TITLE</label>
      <input
        v-model="ui.startTitle"
        class="inp"
        placeholder="Add SSO to customer portal"
      />

      <label class="lbl">REPO URL</label>
      <input v-model="ui.startRepo" class="inp mono" placeholder="git@github.com:org/repo" />

      <label class="lbl">MODE</label>
      <div class="modes">
        <button class="mode" :class="{ on: isBrown }" @click="setMode('brownfield')">brownfield</button>
        <button class="mode" :class="{ on: !isBrown }" @click="setMode('greenfield')">greenfield</button>
      </div>

      <div class="actions">
        <button class="ghost" @click="ui.closeStart()">CANCEL</button>
        <button data-testid="submit" class="go" @click="submit">START</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(5, 7, 10, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.card {
  width: 480px;
  background: #10141b;
  border: 1px solid #2a3140;
  border-radius: 8px;
  padding: 22px 24px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.title {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
  letter-spacing: 0.08em;
  font-weight: 600;
  color: #e8edf5;
  margin-bottom: 18px;
}
.lbl {
  display: block;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.06em;
  color: #5d6675;
  margin-bottom: 6px;
}
.inp {
  width: 100%;
  background: #0d1016;
  border: 1px solid #2a3140;
  border-radius: 5px;
  color: #d9dfe9;
  font-size: 12.5px;
  padding: 9px 12px;
  margin-bottom: 14px;
  font-family: 'IBM Plex Sans', sans-serif;
}
.mono {
  font-family: 'IBM Plex Mono', monospace;
}
.modes {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}
.mode {
  cursor: pointer;
  flex: 1;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  padding: 8px 0;
  border-radius: 4px;
  background: #0d1016;
  color: #7d8697;
  border: 1px solid #2a3140;
}
.mode.on {
  background: #2a2310;
  color: #e0b050;
  border-color: #574a2c;
}
.actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
.ghost {
  cursor: pointer;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  padding: 8px 16px;
  background: none;
  color: #8a93a5;
  border: 1px solid #2a3140;
  border-radius: 4px;
}
.ghost:hover {
  color: #d9dfe9;
}
.go {
  cursor: pointer;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  font-weight: 600;
  padding: 8px 16px;
  background: #e0b050;
  color: #1a1405;
  border: none;
  border-radius: 4px;
}
.go:hover {
  background: #ecc06a;
}
</style>
```

- [ ] **Step 4: Run tests and typecheck**

Run:
```bash
npm run test
npm run typecheck
```
Expected: StartRunModal tests pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add interfaces/dashboard/frontend/src/components/StartRunModal.vue interfaces/dashboard/frontend/src/components/StartRunModal.test.ts
git commit -m "feat(dashboard): start-run modal"
```

---

### Task 11: Fleet view (table, row, stage dots)

**Files:**
- Create: `interfaces/dashboard/frontend/src/components/fleet/StageDots.vue`
- Create: `interfaces/dashboard/frontend/src/components/fleet/FleetRow.vue`
- Create: `interfaces/dashboard/frontend/src/components/fleet/FleetTable.vue`
- Create: `interfaces/dashboard/frontend/src/components/fleet/FleetTable.test.ts`
- Modify: `interfaces/dashboard/frontend/src/views/FleetView.vue` (replace placeholder with `<FleetTable>`)

**Interfaces:**
- Consumes: `useFleetStore` (`runs`), `statusMetaOf`, `stageStateOf`, `money`, `STAGES`.
- Produces: the fleet table (header + rows). Each row is a `RouterLink` to `#/runs/:id` (clickable) showing id, title+mode badge, 14 stage dots, status pill, blocker, cost, age.

- [ ] **Step 1: Write the failing test**

`interfaces/dashboard/frontend/src/components/fleet/FleetTable.test.ts`:
```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import FleetTable from './FleetTable.vue'
import { useFleetStore } from '../../stores/fleet'
import type { Run } from '../../api/types'

const RouterLinkStub = {
  props: ['to'],
  template: '<a data-testid="row-link"><slot /></a>',
}

const mkRun = (over: Partial<Run>): Run => ({
  id: 'feature-x', title: 'A feature', mode: 'brownfield', repo: 'r', stageIdx: 4,
  status: 'blocked', blocker: 'clarify gate', cost: 3.12, budget: 40, age: '2h', skipCtx: false,
  stageNote: '', decisions: [], ...over,
})

beforeEach(() => setActivePinia(createPinia()))

describe('FleetTable', () => {
  it('renders a header and one row per run', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun({ id: 'r1' }), mkRun({ id: 'r2', status: 'done' })]
    const w = mount(FleetTable, { global: { stubs: { RouterLink: RouterLinkStub } } })
    expect(w.findAll('[data-testid="fleet-row"]')).toHaveLength(2)
    expect(w.text()).toContain('RUN')
    expect(w.text()).toContain('STATUS')
  })

  it('renders 14 stage dots per row', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun()]
    const w = mount(FleetTable, { global: { stubs: { RouterLink: RouterLinkStub } } })
    expect(w.findAll('[data-testid="stage-dot"]')).toHaveLength(14)
  })

  it('formats cost and age', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun({ cost: 3.1, age: '2h 14m' })]
    const w = mount(FleetTable, { global: { stubs: { RouterLink: RouterLinkStub } } })
    expect(w.text()).toContain('$3.10')
    expect(w.text()).toContain('2h 14m')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- FleetTable`
Expected: FAIL — components do not exist.

- [ ] **Step 3: Implement StageDots**

`interfaces/dashboard/frontend/src/components/fleet/StageDots.vue`:
```vue
<script setup lang="ts">
import { computed } from 'vue'
import type { Run } from '../../api/types'
import { STAGES, STATUS_COLORS } from '../../constants'
import { stageStateOf } from '../../composables/stageState'

const props = defineProps<{ run: Run }>()

interface Dot {
  title: string
  bg: string
  anim: string
}

const dots = computed<Dot[]>(() =>
  STAGES.map((name, i) => {
    const st = stageStateOf(props.run, i)
    const c =
      st === 'done' ? STATUS_COLORS.done
      : st === 'active' ? STATUS_COLORS.running
      : st === 'blocked' ? STATUS_COLORS.blocked
      : st === 'failed' ? STATUS_COLORS.failed
      : st === 'skipped' ? STATUS_COLORS.skipped
      : STATUS_COLORS.pending
    return {
      title: `${i} ${name} · ${st}`,
      bg: c,
      anim: st === 'active' || st === 'blocked' ? 'fc-pulse 1.6s infinite' : 'none',
    }
  }),
)
</script>

<template>
  <span class="dots">
    <span
      v-for="(d, i) in dots"
      :key="i"
      data-testid="stage-dot"
      class="dot"
      :title="d.title"
      :style="{ background: d.bg, animation: d.anim }"
    />
  </span>
</template>

<style scoped>
.dots {
  display: flex;
  gap: 3px;
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 2px;
}
</style>
```

- [ ] **Step 4: Implement FleetRow**

`interfaces/dashboard/frontend/src/components/fleet/FleetRow.vue`:
```vue
<script setup lang="ts">
import type { Run } from '../../api/types'
import { statusMetaOf } from '../../composables/status'
import { money } from '../../composables/format'
import StageDots from './StageDots.vue'

const props = defineProps<{ run: Run }>()
const meta = () => statusMetaOf(props.run)
</script>

<template>
  <RouterLink :to="`/runs/${run.id}`" data-testid="fleet-row" class="row">
    <span class="id">{{ run.id }}</span>
    <span class="title">
      <span class="title-text">{{ run.title }}</span>
      <span class="mode">{{ run.mode }}</span>
    </span>
    <StageDots :run="run" />
    <span class="status" :style="{ color: meta().color }">
      <span class="pip" :style="{ background: meta().color, animation: meta().anim }" />
      {{ meta().label }}
    </span>
    <span class="blocker">{{ run.blocker || '—' }}</span>
    <span class="cost">{{ money(run.cost) }}</span>
    <span class="age">{{ run.age }}</span>
  </RouterLink>
</template>

<style scoped>
.row {
  display: grid;
  grid-template-columns: 170px minmax(140px, 1.4fr) 172px 126px minmax(90px, 1fr) 76px 60px;
  gap: 12px;
  align-items: center;
  padding: 11px 14px;
  border-bottom: 1px solid #171c25;
  cursor: pointer;
  text-decoration: none;
  color: inherit;
}
.row:hover {
  background: #151a23;
}
.id {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
  color: #9db4d8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #c8cfdb;
}
.mode {
  flex: none;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9.5px;
  padding: 2px 6px;
  border: 1px solid #2a3140;
  border-radius: 3px;
  color: #7d8697;
}
.status {
  display: flex;
  align-items: center;
  gap: 7px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
}
.pip {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.blocker {
  font-size: 11px;
  color: #8a93a5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cost {
  text-align: right;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  color: #c8cfdb;
}
.age {
  text-align: right;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  color: #5d6675;
}
</style>
```

- [ ] **Step 5: Implement FleetTable**

`interfaces/dashboard/frontend/src/components/fleet/FleetTable.vue`:
```vue
<script setup lang="ts">
import { useFleetStore } from '../../stores/fleet'
import FleetRow from './FleetRow.vue'

const fleet = useFleetStore()
</script>

<template>
  <div class="panel">
    <div class="head">
      <span>RUN</span><span>TITLE</span><span>STAGES</span><span>STATUS</span>
      <span>BLOCKER</span><span class="r">COST</span><span class="r">AGE</span>
    </div>
    <FleetRow v-for="r in fleet.runs" :key="r.id" :run="r" />
  </div>
</template>

<style scoped>
.panel {
  border: 1px solid #1e242f;
  border-radius: 6px;
  overflow: hidden;
  background: #10141b;
}
.head {
  display: grid;
  grid-template-columns: 170px minmax(140px, 1.4fr) 172px 126px minmax(90px, 1fr) 76px 60px;
  gap: 12px;
  align-items: center;
  padding: 8px 14px;
  background: #0d1016;
  border-bottom: 1px solid #1e242f;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.08em;
  color: #5d6675;
}
.r {
  text-align: right;
}
</style>
```

- [ ] **Step 6: Wire FleetView to the table**

`interfaces/dashboard/frontend/src/views/FleetView.vue`:
```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useFleetStore } from '../stores/fleet'
import FleetTable from '../components/fleet/FleetTable.vue'

const fleet = useFleetStore()
const summary = computed(() => `${fleet.runs.length} runs · ${fleet.blockedCount} blocked on humans`)
</script>

<template>
  <main data-testid="fleet-view" data-screen-label="Fleet" class="view">
    <div class="head-row">
      <h1 class="title">Fleet</h1>
      <span class="summary">{{ summary }}</span>
    </div>
    <FleetTable />
  </main>
</template>

<style scoped>
.view {
  flex: 1;
  overflow: auto;
  padding: 20px 20px 40px;
}
.head-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin: 0 0 14px;
}
.title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #e8edf5;
}
.summary {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  color: #5d6675;
}
</style>
```

- [ ] **Step 7: Run tests and typecheck**

Run:
```bash
npm run test
npm run typecheck
```
Expected: FleetTable tests pass; all suite green; typecheck clean.

- [ ] **Step 8: Commit**

```bash
git add interfaces/dashboard/frontend/src/components/fleet interfaces/dashboard/frontend/src/views/FleetView.vue
git commit -m "feat(dashboard): fleet view — table, rows, 14-stage dots"
```

---

### Task 12: README + final integration verification

**Files:**
- Create: `interfaces/dashboard/frontend/README.md`

- [ ] **Step 1: Write the README**

`interfaces/dashboard/frontend/README.md`:
````markdown
# SDLC Factory Console — frontend

Vue 3 SPA for the AI-SDLC pipeline's human-in-the-loop surface. See
`docs/superpowers/specs/2026-07-05-dashboard-vue3-frontend-design.md` for the
design and `design/Factory Console.dc.html` for the visual/behavioral
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
````

- [ ] **Step 2: Run the full verification suite**

Run (from `interfaces/dashboard/frontend`):
```bash
npm run typecheck
npm run test
npm run build
```
Expected: typecheck clean; all tests pass; `dist/` built. Then run the dev server once and load the app:
```bash
npm run dev
```
Manually confirm: header brand shows, FLEET tab shows 7 runs with stage dots and statuses, INBOX tab shows the stub, clicking a row navigates to the run stub at `#/runs/<id>`, `+ START RUN` opens the modal and a new row appears on submit, toasts appear bottom-right.

- [ ] **Step 3: Commit**

```bash
git add interfaces/dashboard/frontend/README.md
git commit -m "docs(dashboard): frontend README with run/test/API-swap guide"
```

---

## Plan 1 self-review

**Spec coverage (design doc sections):**
- §1 scope/boundaries — Tasks 1–12 deliver frontend-only; mock-only confirmed by Task 4/5.
- §2 tech & location — Task 1 pins Vite/Vue3/TS/Pinia/vue-router at `interfaces/dashboard/frontend/`.
- §3 architecture (components → stores → client → mock/http) — Tasks 5, 6, 7.
- §4 data contracts — Task 2 (`api/types.ts` matches spec §4 field-for-field).
- §5 API client surface — Task 5 (`DashboardApi`, `selectApi`).
- §6 mock provider — Task 4 (seed + all mutators + ticker, window-guarded).
- §7 stores — Task 6 (fleet incl. `startRun`/counts; inbox `refresh`/drafts; ui toasts/modal). **Deviation:** inbox decision *actions* (answer/decide/override/escalate with toasts) are deferred to Plan 2 alongside the cards — noted inline. This is consistent because the mutators exist in the mock (Task 4) and the store wrappers + UI land together in Plan 2.
- §8 components — Tasks 8–11 cover AppHeader/Toasts/StartRunModal/Fleet; inbox cards + run panels are explicitly Plan 2.
- §9 styling — Task 7 `theme.css` ports the prototype's global styles; component scoped CSS ports inline styles.
- §10 testing — Vitest + @vue/test-utils throughout; composables, mock flows, stores, and component smokes covered; no snapshot tests.
- §11 repo integration — Task 1 (`.gitignore`, `.nvmrc`, `package.json`) and Task 12 (README) document the `VITE_API` swap path; not wired into Python.
- §12 out of scope — respected (no backend, workflow, auth, SSE, Docker).

**Placeholder scan:** none. The earlier Task 7 draft contained a helper `createMemoryHistory_stub`/`mountApp` that would violate `noUnusedLocals`; the plan replaces the whole file with the minimal final form before Step 7's typecheck.

**Type consistency:** `Run`, `InboxItem` union, `DashboardApi`, `StartRunInput`, `ProjectMode`, `GateOutcome` are defined once in Task 2 and used unchanged in Tasks 4–11. `statusMetaOf` / `stageStateOf` signatures (defined Task 3) match call sites in Tasks 9-row, StageDots, and tests. Store method names (`refresh`, `getOrLoad`, `startRun`, `setDraft`, `toggleEdit`, `toast`, `openStart`, `closeStart`, `resetStartForm`) match across Task 6, AppHeader, StartRunModal, and tests.

**Scope check:** this plan yields a runnable app (fleet fully working, start-run working, toasts, routing). Inbox cards and run-detail panels are a cohesive follow-up (Plan 2). Acceptable split.
