import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import ShellAppHeader from './AppHeader.vue'
import App from '../App.vue'
import { router } from '../router'
import { useInboxStore } from '../inbox.store'
import { useFleetStore } from '../../shared/fleet.store'
import { usePrefsStore } from '../prefs.store'
import { useUiStore } from '../ui.store'
import { navManifest } from '../nav'
import { api } from '../../api/client'

vi.mock('../../api/client', () => ({
  api: {
    listRuns: vi.fn(async () => []),
    listInbox: vi.fn(async () => []),
    getInboxState: vi.fn(async () => ({ items: [], unreadable: [] })),
    getShippedGraphs: vi.fn(async () => ({ graphs: [], checks: [], sections: [] })),
  },
  // board.api selects its transport through API_MODE at import time
  API_MODE: 'mock' as const,
}))

const RouterLinkStub = { template: '<a><slot /></a>' }

// The wrapper's U header, captured so tests can assert the props it gets.
// Unique stub names: the wrapper file is also named AppHeader.vue, so a
// stub called 'AppHeader' would make findComponent match the wrapper first.
const AppHeaderStub = defineComponent({
  name: 'UAppHeaderStub',
  props: {
    primary: { type: Array, default: () => [] },
    secondary: { type: Array, default: () => [] },
    badge: { type: Number, default: 0 },
    runSwitch: { type: Object, default: null },
  },
  template: '<div data-testid="app-header-stub" />',
})

// App.vue's footer (T012), captured for the honest-spend cases. The stub
// renders its props so tests can assert them via a DOM selector — VTU's
// definition-based findComponent crashes on null vnodes in the App tree.
const FooterBarStub = defineComponent({
  name: 'FooterBarStub',
  props: {
    left: { type: String, default: '' },
    right: { type: String, default: '' },
  },
  template: '<div data-testid="footer-bar-stub">{{ left }}|{{ right }}</div>',
})

const mountShell = () =>
  mount(ShellAppHeader, {
    global: { stubs: { AppHeader: AppHeaderStub, RouterLink: RouterLinkStub } },
  })

const runEntry = (w: ReturnType<typeof mountShell>) =>
  (w.findComponent(AppHeaderStub).props('primary') as Array<Record<string, unknown>>).find(
    (n) => n.id === 'run',
  )

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('shell AppHeader (v5 wiring, 018 T011 RED)', () => {
  it('passes inbox.items.length as the badge', () => {
    const inbox = useInboxStore()
    inbox.items = [
      { id: 'q1', type: 'clarify', runId: 'r', round: 1, age: '1m', title: 't', body: 'b', suggestion: 's' },
      { id: 'g1', type: 'gate', gate: 'merge', runId: 'r', round: 1, age: '1m', title: 't', body: 'b' },
    ] as any

    const w = mountShell()
    expect(w.findComponent(AppHeaderStub).props('badge')).toBe(2)
  })

  it('with zero fleet runs the run entry is disabled and reads No runs', () => {
    useFleetStore().runs = []
    const w = mountShell()
    const run = runEntry(w)
    expect(run).toBeDefined()
    expect(run!['available']).toBe(false)
    expect(run!['label']).toBe('No runs')
  })

  it('the run entry targets prefs.runInContext when one is set', () => {
    useFleetStore().runs = [
      { id: 'r-old', status: 'running' },
      { id: 'r-new', status: 'running' },
    ] as any
    usePrefsStore().runInContext = 'run-pinned'
    const w = mountShell()
    const run = runEntry(w)
    expect(run).toBeDefined()
    expect(run!['to']).toBe('/runs/run-pinned')
  })

  it('without a run in context the run entry targets the fleet', () => {
    // Run carries no timestamp, so recency is the fleet api's own order; a
    // single-run fleet pins the fallback without pinning that order here.
    useFleetStore().runs = [{ id: 'r-solo', status: 'running' }] as any
    usePrefsStore().runInContext = null
    const w = mountShell()
    const run = runEntry(w)
    expect(run).toBeDefined()
    expect(run!['to']).toBe('/runs/r-solo')
    expect(run!['available']).toBe(true)
  })

  it('keeps the Start-run button until T066 (R-1) and it opens the modal', async () => {
    const ui = useUiStore()
    const w = mountShell()
    expect(w.find('[data-testid="start-btn"]').exists()).toBe(true)
    await w.find('[data-testid="start-btn"]').trigger('click')
    expect(ui.startOpen).toBe(true)
  })
})

describe('shell AppHeader (chaos, 018 T011 RED)', () => {
  it('with no run in context the run entry targets the NEWEST run (listRuns is newest-first)', () => {
    // The fleet store keeps the api's own order and the mock api prepends
    // on startRun, so index 0 is the newest run.
    useFleetStore().runs = [
      { id: 'r-new', status: 'running' },
      { id: 'r-old', status: 'running' },
    ] as any
    usePrefsStore().runInContext = null
    const w = mountShell()
    expect(runEntry(w)!['to']).toBe('/runs/r-new')
    w.unmount()
  })

  it('runInContext overrides recency and resetting it to null returns to the newest run', () => {
    useFleetStore().runs = [
      { id: 'r-new', status: 'running' },
      { id: 'r-old', status: 'running' },
    ] as any
    usePrefsStore().runInContext = 'r-old'
    let w = mountShell()
    expect(runEntry(w)!['to']).toBe('/runs/r-old')
    w.unmount()

    usePrefsStore().runInContext = null
    w = mountShell()
    expect(runEntry(w)!['to']).toBe('/runs/r-new')
    w.unmount()
  })

  it('mounting never mutates the exported navManifest run entry', () => {
    // The wrapper must build its run entry fresh; handing out (and
    // mutating) the shared manifest would leak fleet state across mounts.
    useFleetStore().runs = [{ id: 'r-1', status: 'running' }] as any
    const before = JSON.stringify(navManifest.find((n) => n.id === 'run'))
    const w = mountShell()
    expect(JSON.stringify(navManifest.find((n) => n.id === 'run'))).toBe(before)
    w.unmount()
  })
})

// --- honest spend, restored from 011 T008 against the footer's left side ----
// The footer formats the fleet total from the store's totalCost { usd,
// excluded }: priced-only prints the sum; excluded runs are counted aloud;
// an all-unpriced fleet says "not priced"; an empty fleet says "—".

const role = (cost: number | null) =>
  ({
    role: 'dev',
    model: 'm',
    calls: 1,
    inputTokens: 10,
    outputTokens: 5,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
    cost,
  }) as any

const mountAppWithRuns = async (runs: any[]) => {
  // App's onMounted refresh calls listRuns; serve the seeded runs through
  // the mock so the refresh keeps them instead of clearing to [].
  vi.mocked(api.listRuns).mockImplementation(async () => runs)
  useFleetStore().runs = runs
  const w = mount(App, {
    global: {
      plugins: [router],
      // RouterView is stubbed: the footer reads the fleet store directly,
      // and the mounted screen subtree is what unmount chokes on.
      stubs: { RouterView: true, AppHeader: AppHeaderStub, FooterBar: FooterBarStub },
    },
  })
  await new Promise((r) => setTimeout(r, 0))
  return w
}

describe('footer fleet total (018 T011 RED, honest spend restored)', () => {
  it('all runs priced: prints the sum alone', async () => {
    const w = await mountAppWithRuns([
      { id: 'r1', status: 'running', cost: 2, roles: [] } as any,
      { id: 'r2', status: 'blocked', cost: 3.4, roles: [] } as any,
    ])
    const footer = w.find('[data-testid="footer-bar-stub"]')
    expect(footer.exists()).toBe(true)
    expect(footer.text()).toContain('$5.40')
    expect(footer.text()).not.toContain('not priced')
    expect(footer.text()).toContain('⌘K commands')
    w.unmount()
  })

  it('priced and unpriced mix: sum plus the excluded count', async () => {
    const w = await mountAppWithRuns([
      { id: 'r1', status: 'running', cost: 5, roles: [] } as any,
      { id: 'r2', status: 'running', cost: null, roles: [role(0)] } as any,
      { id: 'r3', status: 'running', cost: null, roles: [role(0)] } as any,
      { id: 'r4', status: 'blocked', cost: null, roles: [role(null)] } as any,
    ])
    const footer = w.find('[data-testid="footer-bar-stub"]')
    expect(footer.exists()).toBe(true)
    expect(footer.text()).toContain('$5.00 · 3 not priced')
    w.unmount()
  })

  it('runs exist but none is priced: "not priced", never $0.00', async () => {
    const w = await mountAppWithRuns([
      { id: 'r1', status: 'running', cost: null, roles: [role(0)] } as any,
      { id: 'r2', status: 'blocked', cost: null, roles: [role(null)] } as any,
    ])
    const footer = w.find('[data-testid="footer-bar-stub"]')
    expect(footer.exists()).toBe(true)
    expect(footer.text()).toContain('not priced')
    expect(footer.text()).not.toContain('$0.00')
    w.unmount()
  })

  it('no runs: the em dash placeholder', async () => {
    const w = await mountAppWithRuns([])
    const footer = w.find('[data-testid="footer-bar-stub"]')
    expect(footer.exists()).toBe(true)
    expect(footer.text()).toContain('—')
    w.unmount()
  })
})

describe('footer fleet total (chaos, 018 T011 RED)', () => {
  it('a present-but-free fleet prints $0.00, never the empty-fleet em dash', async () => {
    // '—' means NO runs; runs with cost 0 are priced and must show $0.00.
    const w = await mountAppWithRuns([{ id: 'r1', status: 'running', cost: 0, roles: [] } as any])
    const footer = w.find('[data-testid="footer-bar-stub"]')
    expect(footer.exists()).toBe(true)
    expect(footer.text()).toContain('$0.00')
    expect(footer.text()).not.toContain('—')
    w.unmount()
  })
})
