import { describe, it, expect, vi } from 'vitest'
import { money, budgetPct, budgetColor } from './format'
import { statusMetaOf } from './status'
import { stageStates } from './stageState'
import type { Run } from '../api/types'

const run = (over: Partial<Run>): Run => ({
  id: 'x',
  title: 't',
  mode: 'brownfield',
  repo: 'r',
  activeStages: ['clarify'],
  status: 'running',
  blocker: '',
  cost: 1,
  budget: 10,
  age: '1m',
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
    expect(statusMetaOf(run({ status: 'done' })).color).toBe('var(--status-done)')
  })
})

const STRIP = ['intake', 'research', 'clarify', 'architecture', 'planning']

describe('stageStates', () => {
  it('marks stages before the lowest active stage done and later ones pending', () => {
    expect(stageStates(run({ activeStages: ['clarify'] }), STRIP)).toEqual(
      ['done', 'done', 'active', 'pending', 'pending'],
    )
  })
  it('marks the active stage blocked, failed or done from the run status', () => {
    expect(stageStates(run({ status: 'blocked' }), STRIP)[2]).toBe('blocked')
    expect(stageStates(run({ status: 'failed' }), STRIP)[2]).toBe('failed')
    expect(stageStates(run({ status: 'done' }), STRIP)[2]).toBe('done')
  })
  it('marks every active stage of a fanned-out run', () => {
    expect(stageStates(run({ activeStages: ['research', 'architecture'] }), STRIP)).toEqual(
      ['done', 'active', 'pending', 'active', 'pending'],
    )
  })
  it.each(['running', 'blocked', 'failed', 'done'] as const)(
    'renders every mark pending when no stage is active (status %s)',
    (status) => {
      expect(stageStates(run({ activeStages: [], status }), STRIP)).toEqual(STRIP.map(() => 'pending'))
    },
  )
  it('ignores a stage name that is not canonical and reports it once', () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(stageStates(run({ activeStages: ['bogus'] }), STRIP)).toEqual(STRIP.map(() => 'pending'))
    stageStates(run({ activeStages: ['bogus'] }), STRIP)
    expect(err).toHaveBeenCalledTimes(1)
    expect(err).toHaveBeenCalledWith(expect.stringContaining('bogus'))
    err.mockRestore()
  })

  // --- canvas run-mode wiring (E75-OQ-1, bug canvas-run-mode): served
  // stage_marks become the strip's source (E-75 §8; E76-OQ-3).

  it('renders stageMarks verbatim in canonical order; absent stages render skipped', () => {
    const marked = {
      ...run({ activeStages: ['clarify'], status: 'running' }),
      stageMarks: { intake: 'done', clarify: 'active', planning: 'pending' },
    } as never
    expect(stageStates(marked, STRIP)).toEqual(['done', 'skipped', 'active', 'skipped', 'pending'])
  })

  it('keeps the linear inference exactly when stageMarks is null', () => {
    const legacy = {
      ...run({ activeStages: ['clarify'], status: 'running' }),
      stageMarks: null,
    } as never
    expect(stageStates(legacy, STRIP)).toEqual(['done', 'done', 'active', 'pending', 'pending'])
  })

  // --- chaos: marks edge cases the verbatim/null pins leave open ----------

  it('marks present but EMPTY renders every canonical stage skipped, never the linear fallback', () => {
    const marked = {
      ...run({ activeStages: ['clarify'], status: 'running' }),
      stageMarks: {},
    } as never
    expect(stageStates(marked, STRIP)).toEqual(STRIP.map(() => 'skipped'))
  })

  it('a non-canonical marks key renders nothing and is not an activeStages product fault', () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const marked = {
      ...run({ activeStages: [], status: 'running' }),
      stageMarks: { unknown: 'done' },
    } as never
    // the unknown key added no dot: exactly one state per canonical stage,
    // all absent from the marks -> skipped; and the rule-3 fault path
    // (console.error) governs activeStages names only, never marks keys
    expect(stageStates(marked, STRIP)).toEqual(STRIP.map(() => 'skipped'))
    expect(err).not.toHaveBeenCalled()
    err.mockRestore()
  })
})
