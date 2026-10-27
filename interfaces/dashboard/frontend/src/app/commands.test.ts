import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { commandsOf } from './commands'
import type { PaletteCommand } from '@kroker/ui'

// 018 T018 (RED): commandsOf maps app state to v5's command list (S11), filtered
// by navManifest availability and designAvailable (data-model §5). Tier A, C and
// D use the real './nav'. Tier B swaps it for an all-available manifest through
// vi.doMock and a fresh module graph, because the top-level import pins the real one.

const STATE = {
  run: {
    id: 'run-7',
    pending: [
      { id: 'gate-1', title: 'Merge gate' },
      { id: 'gate-2', title: 'Plan gate' },
    ],
  },
  inboxCount: 3,
  mode: 'observe' as const,
  graphs: ['ingest', 'enrich'],
}

describe('commandsOf with the real nav (designAvailable false, compare and interfaces unavailable)', () => {
  it('returns exactly the available commands in S11 order', () => {
    const expected: PaletteCommand[] = [
      { id: 'review-gate-1', label: 'Review Merge gate', hint: 'waiting' },
      { id: 'review-gate-2', label: 'Review Plan gate', hint: 'waiting' },
      { id: 'open-inbox', label: 'Open Inbox', hint: '3 pending' },
      { id: 'open-fleet', label: 'Open Fleet' },
      { id: 'open-run-board', label: 'Open run board', hint: 'run-7' },
      { id: 'fit-graph', label: 'Fit graph to view' },
    ]
    expect(commandsOf(STATE)).toEqual(expected)
  })

  it('with no run in context, drops every review command and the run board command, keeping Open Inbox', () => {
    const ids = commandsOf({ ...STATE, run: null }).map((c) => c.id)
    expect(ids.some((id) => id.startsWith('review-'))).toBe(false)
    expect(ids).not.toContain('open-run-board')
    expect(ids).toContain('open-inbox')
  })

  it('an empty inbox reads "0 pending", it is not omitted', () => {
    const inbox = commandsOf({ ...STATE, inboxCount: 0 }).find((c) => c.id === 'open-inbox')
    expect(inbox).toEqual({ id: 'open-inbox', label: 'Open Inbox', hint: '0 pending' })
  })
})

describe('commandsOf with every command available (design mode)', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.doMock('./nav', () => ({
      navManifest: [
        { id: 'fleet', label: 'Fleet', to: '/', available: true },
        { id: 'inbox', label: 'Inbox', to: '/inbox', available: true },
        { id: 'run', label: 'Run', to: '/runs/run-7', available: true },
        { id: 'graphs', label: 'Graphs', to: '/graphs', available: true },
        { id: 'compare', label: 'Compare', to: '/compare', available: true },
        { id: 'interfaces', label: 'Interfaces', to: '/interfaces', available: true },
      ],
      designAvailable: true,
    }))
  })

  afterEach(() => {
    vi.doUnmock('./nav')
    vi.resetModules()
  })

  it('lists the Observe switch, the Design commands, Validate, Compare and Interfaces in S11 order', async () => {
    const { commandsOf: commandsOfAll } = await import('./commands')
    const expected: PaletteCommand[] = [
      { id: 'review-gate-1', label: 'Review Merge gate', hint: 'waiting' },
      { id: 'review-gate-2', label: 'Review Plan gate', hint: 'waiting' },
      { id: 'open-inbox', label: 'Open Inbox', hint: '3 pending' },
      { id: 'open-fleet', label: 'Open Fleet' },
      { id: 'open-run-board', label: 'Open run board', hint: 'run-7' },
      { id: 'switch-mode', label: 'Switch to Observe' },
      { id: 'design-ingest', label: 'Design ingest' },
      { id: 'design-enrich', label: 'Design enrich' },
      { id: 'validate-graph', label: 'Validate graph' },
      { id: 'fit-graph', label: 'Fit graph to view' },
      { id: 'compare', label: 'Compare arms × graphs' },
      { id: 'interfaces', label: 'Harness interfaces' },
    ]
    expect(commandsOfAll({ ...STATE, mode: 'design' })).toEqual(expected)
  })
})

describe('commandsOf (chaos, real nav)', () => {
  it('two pending items sharing an id yield two review commands in given order, ids repeated as given', () => {
    const cmds = commandsOf({
      ...STATE,
      run: {
        ...STATE.run,
        pending: [
          { id: 'gate-1', title: 'A' },
          { id: 'gate-1', title: 'B' },
        ],
      },
    })
    const reviews = cmds.filter((c) => c.id.startsWith('review-'))
    expect(reviews.map((c) => c.id)).toEqual(['review-gate-1', 'review-gate-1'])
    expect(reviews.map((c) => c.label)).toEqual(['Review A', 'Review B'])
  })

  it('an empty pending list yields no review commands and keeps the run board', () => {
    const cmds = commandsOf({ ...STATE, run: { ...STATE.run, pending: [] } })
    expect(cmds.some((c) => c.id.startsWith('review-'))).toBe(false)
    expect(cmds.map((c) => c.id)).toContain('open-run-board')
  })

  it('a pending item with an empty title reads exactly "Review " with no undefined or null', () => {
    const cmds = commandsOf({
      ...STATE,
      run: { ...STATE.run, pending: [{ id: 'gate-x', title: '' }] },
    })
    const review = cmds.find((c) => c.id.startsWith('review-'))
    expect(review?.label).toBe('Review ')
  })
})

describe('commandsOf (chaos, every command available)', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.doMock('./nav', () => ({
      navManifest: [
        { id: 'fleet', label: 'Fleet', to: '/', available: true },
        { id: 'inbox', label: 'Inbox', to: '/inbox', available: true },
        { id: 'run', label: 'Run', to: '/runs/run-7', available: true },
        { id: 'graphs', label: 'Graphs', to: '/graphs', available: true },
        { id: 'compare', label: 'Compare', to: '/compare', available: true },
        { id: 'interfaces', label: 'Interfaces', to: '/interfaces', available: true },
      ],
      designAvailable: true,
    }))
  })

  afterEach(() => {
    vi.doUnmock('./nav')
    vi.resetModules()
  })

  it('an empty graphs list adds no design commands and keeps switch, validate, compare and interfaces in order', async () => {
    const { commandsOf: commandsOfAll } = await import('./commands')
    const ids = commandsOfAll({ ...STATE, mode: 'design', graphs: [] }).map((c) => c.id)
    expect(ids.some((id) => id.startsWith('design-'))).toBe(false)
    const kept = ids.filter((id) => ['switch-mode', 'validate-graph', 'compare', 'interfaces'].includes(id))
    expect(kept).toEqual(['switch-mode', 'validate-graph', 'compare', 'interfaces'])
  })

  it('graph ids with special characters become design labels verbatim, unescaped and untruncated', async () => {
    const { commandsOf: commandsOfAll } = await import('./commands')
    const labels = commandsOfAll({ ...STATE, mode: 'design', graphs: ['ingest-v2', 'enrich:raw'] })
      .map((c) => c.label)
      .filter((label) => label.startsWith('Design '))
    expect(labels).toEqual(['Design ingest-v2', 'Design enrich:raw'])
  })

  it('every command object carries only id and label, with hint as the one optional key', async () => {
    const { commandsOf: commandsOfAll } = await import('./commands')
    const cmds = commandsOfAll({ ...STATE, mode: 'design' })
    expect(cmds.length).toBeGreaterThan(0)
    const allowed = [
      ['id', 'label'],
      ['hint', 'id', 'label'],
    ]
    for (const c of cmds) {
      expect(allowed).toContainEqual(Object.keys(c).sort())
    }
  })
})
