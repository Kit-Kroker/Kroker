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
  it('marks future stages pending', () => {
    expect(stageStateOf(run({ stageIdx: 5 }), 9)).toBe('pending')
  })
})
