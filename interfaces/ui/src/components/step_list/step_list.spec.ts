import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StepList from './StepList.vue'
import type { CanvasStatus } from '../graph_canvas/types'

// 018 T023 (RED): the inner-loop step list — one read-only row per step.
// Stable hooks the implementation (T024) must carry: step-row and step-pip,
// the pip's class list carrying the step's status string.

const STEPS: Array<{ name: string; ref: string; status: CanvasStatus; meta: string }> = [
  { name: 'analyze', ref: 'a1', status: 'done', meta: '0m 12s' },
  { name: 'plan', ref: 'p2', status: 'running', meta: 'r2' },
  { name: 'code', ref: 'c3', status: 'idle', meta: '' },
]

describe('StepList', () => {
  it('renders one read-only row per step with name, ref and a status pip', () => {  // clause: STEP_LIST-1
    const w = mount(StepList, { props: { steps: STEPS } })
    const rows = w.findAll('[data-testid="step-row"]')
    expect(rows).toHaveLength(3)
    expect(rows[0].text()).toContain('analyze')
    expect(rows[0].text()).toContain('a1')
    expect(rows[1].text()).toContain('plan')
    expect(rows[1].text()).toContain('p2')
    expect(rows[2].text()).toContain('code')
    expect(rows[2].text()).toContain('c3')
    const pips = rows.map((r) => r.find('[data-testid="step-pip"]'))
    expect(pips.map((p) => p.classes().join(' '))).toEqual(
      expect.arrayContaining(['done', 'running', 'idle'].map((s) => expect.stringContaining(s))),
    )
  })

  it('carries no interactive control, and an empty list renders nothing', () => {  // clause: STEP_LIST-2
    const w = mount(StepList, { props: { steps: STEPS } })
    expect(w.findAll('button')).toHaveLength(0)
    expect(w.find('a').exists()).toBe(false)

    const empty = mount(StepList, { props: { steps: [] } })
    expect(empty.findAll('[data-testid="step-row"]')).toHaveLength(0)
  })
})

describe('StepList (chaos, 018 T023 RED)', () => {
  it('a step with empty meta renders its row with name and ref and no undefined or null text', () => {  // clause: STEP_LIST-1
    const w = mount(StepList, {
      props: { steps: [{ name: 'verify', ref: 'v9', status: 'done' as CanvasStatus, meta: '' }] },
    })
    const rows = w.findAll('[data-testid="step-row"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('verify')
    expect(rows[0].text()).toContain('v9')
    expect(rows[0].text()).not.toContain('undefined')
    expect(rows[0].text()).not.toContain('null')
  })

  it('renders one row per every CanvasStatus value, each pip carrying its status string', () => {  // clause: STEP_LIST-1
    const statuses = [
      'idle',
      'running',
      'blocked',
      'done',
      'failed',
      'stale',
      'skipped',
      'cancelled',
    ] as const
    const w = mount(StepList, {
      props: {
        steps: statuses.map((s, i) => ({
          name: `step-${s}`,
          ref: `r${i}`,
          status: s as CanvasStatus,
          meta: '',
        })),
      },
    })
    const rows = w.findAll('[data-testid="step-row"]')
    expect(rows).toHaveLength(8)
    rows.forEach((row, i) => {
      expect(row.find('[data-testid="step-pip"]').classes().join(' ')).toContain(statuses[i])
    })
  })

  it('renders no input, select or textarea anywhere', () => {  // clause: STEP_LIST-2
    const w = mount(StepList, { props: { steps: STEPS } })
    expect(w.findAll('input')).toHaveLength(0)
    expect(w.findAll('select')).toHaveLength(0)
    expect(w.findAll('textarea')).toHaveLength(0)
  })
})
