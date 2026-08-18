import { describe, it, expect } from 'vitest'
import snapshot from './__fixtures__/fleet-snapshot.json'
import { mapSnapshot } from './http'

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

  it('derives stageIdx from current_stage', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    // CANONICAL_STAGES: intake, constitution, context, requirements,
    // research, clarify, architecture -> index 6
    expect(runs.find((r) => r.id === 'feature-add-sso')!.stageIdx).toBe(6)
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
})
