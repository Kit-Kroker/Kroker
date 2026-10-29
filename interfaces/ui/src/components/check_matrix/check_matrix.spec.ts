import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CheckMatrix from './CheckMatrix.vue'
import type { CellState } from './CheckMatrix.vue'

// 018 T076 (RED): the Interfaces screen's matrix (S12, FR-050/FR-051). Props
// per data-model §2.3: columns {key,name,ref}[], rows {harness,sub,planned,
// cells:{state,text}[]}[], facts {who,severity,text}[]. Stable hooks the
// implementation (T077) must carry: matrix-column / matrix-row / matrix-cell
// (data-state) / matrix-fact (data-severity).

const COLUMNS = [
  { key: 'layers', name: 'Layers', ref: 'ADR-15' },
  { key: 'strict', name: 'Strict', ref: 'policy/containment.yaml' },
  { key: 'family', name: 'Family', ref: 'registry dev' },
]

const row = (harness: string, states: CellState[], planned = false, sub = '') => ({
  harness,
  sub,
  planned,
  cells: states.map((state) => ({ state, text: state === 'not_measured' ? 'not measured' : state })),
})

const ROWS = [
  row('claude_code', ['yes', 'yes', 'not_measured']),
  row('opencode', ['yes', 'partial', 'yes']),
  row('cursor', ['no', 'no', 'not_measured']),
  row('pyai', ['planned', 'planned', 'planned'], true, 'planned adapter'),
]

const FACTS = [
  { who: 'opencode', severity: 'warn' as const, text: 'no hook layer: observability rules report nothing' },
  { who: 'cursor', severity: 'error' as const, text: 'fails closed on unreadable policy' },
]

const mountMatrix = (over: Record<string, unknown> = {}) =>
  mount(CheckMatrix, { props: { columns: COLUMNS, rows: ROWS, facts: FACTS, ...over } })

describe('CheckMatrix', () => {
  it('renders one header per column with its name and ref', () => {  // clause: CHECK_MATRIX-1
    const w = mountMatrix()
    const headers = w.findAll('[data-testid="matrix-column"]')
    expect(headers).toHaveLength(3)
    expect(headers[0].text()).toContain('Layers')
    expect(headers[0].text()).toContain('ADR-15')
    expect(headers[1].text()).toContain('Strict')
    expect(headers[1].text()).toContain('policy/containment.yaml')
  })

  it('renders one row per harness and one cell per column', () => {  // clause: CHECK_MATRIX-2
    const w = mountMatrix()
    const rows = w.findAll('[data-testid="matrix-row"]')
    expect(rows.map((r) => r.text())).toHaveLength(4)
    expect(rows[0].text()).toContain('claude_code')
    expect(w.findAll('[data-testid="matrix-cell"]')).toHaveLength(12)
  })

  it('each cell carries its state as a stable mark, with its text where it has one', () => {  // clause: CHECK_MATRIX-3
    const w = mountMatrix()
    const first = w.findAll('[data-testid="matrix-row"]')[0].findAll('[data-testid="matrix-cell"]')
    expect(first[0].attributes('data-state')).toBe('yes')
    expect(first[2].attributes('data-state')).toBe('not_measured')
    expect(first[2].text()).toContain('not measured')
    const cursor = w.findAll('[data-testid="matrix-row"]')[2].findAll('[data-testid="matrix-cell"]')
    expect(cursor[0].attributes('data-state')).toBe('no')
    const opencode = w.findAll('[data-testid="matrix-row"]')[1].findAll('[data-testid="matrix-cell"]')
    expect(opencode[1].attributes('data-state')).toBe('partial')
  })

  it('the planned row carries the dimmed treatment', () => {  // clause: CHECK_MATRIX-4
    const w = mountMatrix()
    const rows = w.findAll('[data-testid="matrix-row"]')
    const planned = rows[3]
    expect(planned.classes().join(' ')).toContain('planned')
    expect(planned.text()).toContain('pyai')
    // Only the planned row is dimmed.
    for (const row of rows.slice(0, 3)) {
      expect(row.classes().join(' ')).not.toContain('planned')
    }
  })

  it('each fact renders with its severity distinguishable, its who and its text', () => {  // clause: CHECK_MATRIX-5
    const w = mountMatrix()
    const facts = w.findAll('[data-testid="matrix-fact"]')
    expect(facts).toHaveLength(2)
    expect(facts[0].attributes('data-severity')).toBe('warn')
    expect(facts[0].text()).toContain('opencode')
    expect(facts[0].text()).toContain('no hook layer')
    expect(facts[1].attributes('data-severity')).toBe('error')
    expect(facts[1].text()).toContain('cursor')
    expect(facts[1].text()).toContain('fails closed')
  })

  it('an empty matrix (no rows, no facts) renders its headers and nothing else, without throwing', () => {  // clause: CHECK_MATRIX-1
    const w = mountMatrix({ rows: [], facts: [] })
    expect(w.findAll('[data-testid="matrix-column"]')).toHaveLength(3)
    expect(w.findAll('[data-testid="matrix-row"]')).toHaveLength(0)
    expect(w.findAll('[data-testid="matrix-fact"]')).toHaveLength(0)
  })
})
