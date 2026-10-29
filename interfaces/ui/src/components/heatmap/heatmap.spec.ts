import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Heatmap from './Heatmap.vue'

// 018 T069 (RED): Compare's "Rework by canonical_stage" heatmap (S10, FR-052).
// Props per data-model §4.2: columns: string[], rows: { name, cells:
// { state: 'value' | 'low_n' | 'blank', value: number | null, n: number }[] }[].
// Stable hooks the implementation (T070) must carry: heat-column (header),
// heat-row, heat-cell. Colour comes from a token scale — a stable class or a
// var() background — never a literal (TOKENS-2's rule for this component).

const COLUMNS = ['intake', 'clarify', 'code', 'merge']

const ROW = {
  name: 'opencode × zai-coding-plan/glm-5.3',
  cells: [
    { state: 'value' as const, value: 0.42, n: 12 },
    { state: 'low_n' as const, value: 0.9, n: 3 },
    { state: 'blank' as const, value: null, n: 0 },
    { state: 'value' as const, value: 0.0, n: 8 },
  ],
}

const mountHeatmap = (over: Record<string, unknown> = {}) =>
  mount(Heatmap, { props: { columns: COLUMNS, rows: [ROW], ...over } })

describe('Heatmap', () => {
  it('renders one column header per column, in wire order', () => {  // clause: HEATMAP-1
    const w = mountHeatmap()
    const headers = w.findAll('[data-testid="heat-column"]').map((h) => h.text())
    expect(headers).toEqual(COLUMNS)
  })

  it('renders one row per entry with its name and one cell per column', () => {  // clause: HEATMAP-2
    const w = mountHeatmap()
    const rows = w.findAll('[data-testid="heat-row"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('opencode × zai-coding-plan/glm-5.3')
    expect(w.findAll('[data-testid="heat-cell"]')).toHaveLength(4)
  })

  it('a value cell shows its value; a blank cell renders empty with no number', () => {  // clause: HEATMAP-3
    const w = mountHeatmap()
    const cells = w.findAll('[data-testid="heat-cell"]')
    expect(cells[0].text()).toContain('0.42')
    expect(cells[0].text()).not.toContain('low n')
    // Blank is blank: no number, no zero, no placeholder text.
    expect(cells[2].text().trim()).toBe('')
    expect(cells[2].text()).not.toContain('0')
  })

  it('a low_n cell carries its muted treatment as a stable class', () => {  // clause: HEATMAP-4
    const w = mountHeatmap()
    const cells = w.findAll('[data-testid="heat-cell"]')
    expect(cells[1].classes().join(' ')).toContain('low-n')
    expect(cells[0].classes().join(' ')).not.toContain('low-n')
  })

  it('colour comes from a token scale: a var-based background or scale class, never a literal', () => {  // clause: HEATMAP-5
    const w = mountHeatmap()
    const value = w.findAll('[data-testid="heat-cell"]')[0]
    const style = (value.element as HTMLElement).getAttribute('style') ?? ''
    const classes = value.classes().join(' ')
    // The positive rule: the intensity rides a token variable or a scale
    // class. (No literal-colour patterns are written here - the raw-colour
    // scanner reads this file too.)
    const tokenScaled = style.includes('var(--') || /heat-(scale|intensity)/.test(classes)
    expect(tokenScaled).toBe(true)
  })

  it('an empty columns and rows array renders no header, row or cell, without throwing', () => {  // clause: HEATMAP-1
    const w = mountHeatmap({ columns: [], rows: [] })
    expect(w.findAll('[data-testid="heat-column"]')).toHaveLength(0)
    expect(w.findAll('[data-testid="heat-cell"]')).toHaveLength(0)
  })
})
