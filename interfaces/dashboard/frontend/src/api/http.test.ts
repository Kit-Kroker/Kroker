import { describe, it, expect } from 'vitest'
import snapshot from './__fixtures__/fleet-snapshot.json'
import { mapInboxState, mapSnapshot } from './http'

const NOW = new Date('2026-08-18T11:00:00Z')

describe('mapSnapshot', () => {
  it('maps a live run onto the view model', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    const sso = runs.find((r) => r.id === 'feature-add-sso')!
    expect(sso.title).toBe('Add SSO to customer portal')
    expect(sso.mode).toBe('brownfield')
    expect(sso.repo).toBe('git@github.com:acme/portal')
    expect(sso.cost).toBe(3.12)
    expect(sso.budget).toBe(40)
  })

  it('maps an awaiting status to blocked', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-add-sso')!.status).toBe('blocked')
  })

  it('maps a running status to running', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-unpriced')!.status).toBe('running')
  })

  it('keeps an unpriced run null rather than zero', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-unpriced')!.cost).toBeNull()
  })

  it('carries current_stage as a stage name, never an index', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-add-sso')!.activeStages).toEqual(['architecture'])
  })

  it('formats age from started_at', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-add-sso')!.age).toBe('2h 00m')
  })

  it('renders a closed run as done', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    const closed = runs.find((r) => r.id === 'feature-dark-mode')!
    expect(closed.status).toBe('done')
    expect(closed.title).toBe('Dark mode for settings pages')
  })

  it('renders a rolled-back closed run as failed, not done', () => {
    // deployed: is the only success prefix; rolled-back: must not render
    // green (E-10 review F2).
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'fix-payment-retry')!.status).toBe('failed')
    expect(runs.find((r) => r.id === 'feature-dark-mode')!.status).toBe('done')
  })

  it('renders a merged-not-deployed closed run as done, not failed', () => {
    // Success family per tidyup.py: merged-not-deployed passed the absolute
    // merge gate; deploy was disabled/unapproved. It must not render red.
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-flag-cleanup')!.status).toBe('done')
    expect(runs.find((r) => r.id === 'fix-payment-retry')!.status).toBe('failed')
    expect(runs.find((r) => r.id === 'feature-dark-mode')!.status).toBe('done')
  })

  it('maps each pending variant to its inbox item type', () => {
    const { inbox } = mapSnapshot(snapshot as never, NOW)
    expect(inbox.map((i) => i.type)).toEqual([
      'clarify', 'gate', 'override', 'escalation',
    ])
  })

  it('carries the merge gate check table onto the override item', () => {
    const { inbox } = mapSnapshot(snapshot as never, NOW)
    const override = inbox.find((i) => i.type === 'override')!
    expect(override.checks).toEqual([
      { name: 'lint', kind: 'ABSOLUTE', ok: true, detail: 'clean' },
      { name: 'diff coverage', kind: 'ADVISORY', ok: false, detail: '0.68 - target 0.80' },
    ])
  })

  it('uses the pending key as the inbox item id', () => {
    const { inbox } = mapSnapshot(snapshot as never, NOW)
    expect(inbox.map((i) => i.id)).toEqual([
      'Q1', 'architecture#1', 'merge#1', 'task:T07#1',
    ])
  })

  it('computes inbox age from opened_at', () => {
    const { inbox } = mapSnapshot(snapshot as never, NOW)
    expect(inbox[0].age).toBe('2h 00m')
  })

  // --- canvas run-mode wiring (E75-OQ-1, bug canvas-run-mode): the served
  // marks become the strip's source of truth (E-75 §8; E76-OQ-3 closes).

  it('carries an open graph run stage_marks verbatim as stageMarks', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    const row = runs.find((r) => r.id === 'graph-run-live')!
    const marks = (snapshot as { runs: { run_id: string; stage_marks?: Record<string, string> }[] })
      .runs.find((r) => r.run_id === 'graph-run-live')!.stage_marks!
    expect((row as { stageMarks?: unknown }).stageMarks).toEqual(marks)
  })

  it('maps a closed graph run from closed_marks and leaves unmarked rows null', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    const closed = runs.find((r) => r.id === 'graph-run-closed')!
    const marks = (snapshot as { closed_marks: Record<string, Record<string, string>> })
      .closed_marks['graph-run-closed']
    expect((closed as { stageMarks?: unknown }).stageMarks).toEqual(marks)
    // FeatureWorkflow rows keep the linear fallback contract: null, not
    // undefined, not inferred marks.
    const sso = runs.find((r) => r.id === 'feature-add-sso')!
    expect((sso as { stageMarks?: unknown }).stageMarks).toBeNull()
  })
})

// --- 002 T027 (RED): project_key on the run wire (FR-020a, G4/R-1). The
// fixture rows carry no project_key until T028's hand-edit, so the set
// cases inject it onto a clone; the fixture IS the absent case.

describe('project_key mapping', () => {
  it("maps project_key onto an open row's projectKey", () => {
    const s = structuredClone(snapshot)
    ;(s as { runs: Record<string, unknown>[] }).runs
      .find((r) => r.run_id === 'feature-add-sso')!.project_key = 'kroker'
    const { runs } = mapSnapshot(s as never, NOW)
    const sso = runs.find((r) => r.id === 'feature-add-sso')!
    expect((sso as { projectKey?: unknown }).projectKey).toBe('kroker')
  })

  it("maps project_key onto a closed row's projectKey", () => {
    const s = structuredClone(snapshot)
    ;(s as { closed: Record<string, unknown>[] }).closed
      .find((r) => r.run_id === 'feature-dark-mode')!.project_key = 'kroker'
    const { runs } = mapSnapshot(s as never, NOW)
    const dark = runs.find((r) => r.id === 'feature-dark-mode')!
    expect((dark as { projectKey?: unknown }).projectKey).toBe('kroker')
  })

  it('maps an absent key and an explicit null to null, never "default"', () => {
    // FR-020a: an unavailable project key is an explicit absent value the
    // Board tab banners off -- the mapper must not guess the backend's
    // "default" bucket name for it.
    const absent = mapSnapshot(snapshot as never, NOW)
    // T028's hand-edit sets feature-add-sso and leaves feature-unpriced
    // key-absent -- that row is the fixture's genuine absent case.
    expect((absent.runs.find((r) => r.id === 'feature-unpriced')! as { projectKey?: unknown }).projectKey).toBeNull()

    const s = structuredClone(snapshot)
    ;(s as { runs: Record<string, unknown>[] }).runs
      .find((r) => r.run_id === 'feature-add-sso')!.project_key = null
    const nulled = mapSnapshot(s as never, NOW)
    expect((nulled.runs.find((r) => r.id === 'feature-add-sso')! as { projectKey?: unknown }).projectKey).toBeNull()
  })
})

// --- 010 T004 (RED): mapInboxState carries the inbox items and the
// unreadable runs out of one snapshot (contract inbox-screen.md §1). The
// items must be exactly what mapSnapshot already produces; unreadable is
// open_errors mapped to camelCase, absent when the key is absent, and a
// closed run's failure in `errors` is not an unreadable run.
describe('mapInboxState', () => {
  it('items deep-equal mapSnapshot inbox and the fixture has no unreadable runs', () => {
    const state = mapInboxState(snapshot as never, NOW)
    expect(state.items).toEqual(mapSnapshot(snapshot as never, NOW).inbox)
    expect(state.unreadable).toEqual([])
  })

  it('maps open_errors entries to { runId, error }', () => {
    const s = structuredClone(snapshot)
    ;(s as { open_errors: Record<string, unknown>[] }).open_errors = [
      { run_id: 'r9', error: 'boom' },
    ]
    expect(mapInboxState(s as never, NOW).unreadable).toEqual([
      { runId: 'r9', error: 'boom' },
    ])
  })

  it('a payload with no open_errors gives an empty unreadable list', () => {
    const s = structuredClone(snapshot)
    delete (s as { open_errors?: unknown }).open_errors
    expect(mapInboxState(s as never, NOW).unreadable).toEqual([])
  })

  it('a closed-run failure in errors is not an unreadable run', () => {
    const s = structuredClone(snapshot)
    ;(s as { errors: Record<string, unknown>[] }).errors.push({
      run_id: 'rc', error: 'summary failed',
    })
    expect(mapInboxState(s as never, NOW).unreadable).toEqual([])
  })
})

// --- 011 T006 (RED): budget and roles mapping (data-model §2.4). The wire
// gains roles, budget_threshold_usd, budget_counted_usd and
// budget_crossings; the mapper must carry them onto the view model in
// camelCase, with absent keys mapped to their honest defaults (absent
// crossings = 0, absent budget = null, absent roles = []). A zero total
// with tokens is a not-priced run, never 0.

type RoleRow = {
  role: string
  inputTokens: number
  cacheReadTokens: number
  cost: number | null
}

type WithBudget = {
  roles?: RoleRow[]
  budgetThreshold?: number | null
  budgetCounted?: number | null
  budgetCrossings?: number
  budgetNotice?: string | null
}

describe('011 budget and roles mapping', () => {
  it("maps an open run's roles in wire order, camelCase, with the budget fields", () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    const sso = runs.find((r) => r.id === 'feature-add-sso')! as typeof sso & WithBudget
    const [architect, dev, planner] = sso.roles!
    expect(architect).toMatchObject({ role: 'architect', inputTokens: 4200, cacheReadTokens: 15000, cost: 3.12 })
    expect(dev).toMatchObject({ role: 'dev', inputTokens: 12000, cost: 0 })
    expect(planner).toMatchObject({ role: 'planner', cost: null })
    expect(sso.budgetThreshold).toBe(40)
    expect(sso.budgetCounted).toBe(3.12)
    expect(sso.budgetCrossings).toBe(1)
    expect(sso.budgetNotice).toBeNull()
  })

  it('a closed run keeps no live threshold but keeps its counted total', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    const closed = runs.find((r) => r.id === 'graph-run-closed')! as typeof closed & WithBudget
    expect(closed.budgetThreshold).toBeNull()
    expect(closed.budgetCounted).toBe(4.4)
  })

  it('a closed run with no roles key maps roles to [] and keeps the wire total', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    const dark = runs.find((r) => r.id === 'feature-dark-mode')! as typeof dark & WithBudget
    expect(dark.roles).toEqual([])
    expect(dark.cost).toBe(7.88)
  })

  it('maps every absent budget and roles key to its honest default', () => {
    const s = structuredClone(snapshot)
    const row = (s as { runs: Record<string, unknown>[] }).runs.find(
      (r) => r.run_id === 'feature-add-sso',
    )!
    delete row.budget_crossings
    delete row.budget_threshold_usd
    delete row.budget_counted_usd
    delete row.roles
    const sso = mapSnapshot(s as never, NOW).runs.find(
      (r) => r.id === 'feature-add-sso',
    )! as typeof sso & WithBudget
    expect(sso.budgetCrossings).toBe(0)
    expect(sso.budgetThreshold).toBeNull()
    expect(sso.budgetCounted).toBeNull()
    expect(sso.roles).toEqual([])
  })

  it('a zero total with tokens stays null, never 0 and never $0.00', () => {
    const s = structuredClone(snapshot)
    const unpriced = (s as { runs: Record<string, unknown>[] }).runs.find(
      (r) => r.run_id === 'feature-unpriced',
    )!
    unpriced.roles = [
      {
        role: 'dev',
        model: 'm',
        calls: 1,
        input_tokens: 12000,
        output_tokens: 3400,
        cache_read_tokens: 0,
        cache_write_tokens: 0,
        cost_usd: 0.0,
      },
    ]
    unpriced.cost_usd_total = 0.0
    const row = mapSnapshot(s as never, NOW).runs.find((r) => r.id === 'feature-unpriced')!
    expect(row.cost).toBeNull()
  })
})
