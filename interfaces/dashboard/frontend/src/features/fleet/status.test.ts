import { describe, it, expect } from 'vitest'
import { statusMetaOf } from './status'
import type { Run } from '../../api/types'

const run = (over: Partial<Run>): Run => ({
  id: 'x',
  title: 't',
  mode: 'brownfield',
  repo: 'r',
  activeStages: ['clarify'],
  stageMarks: null,
  status: 'running',
  blocker: '',
  cost: 1,
  budget: 10,
  age: '1m',
  decisions: [],
  ...over,
})

describe('statusMetaOf', () => {
  it('maps each status to color/label/anim', () => {
    expect(statusMetaOf(run({ status: 'running' })).label).toBe('running')
    expect(statusMetaOf(run({ status: 'blocked' })).label).toBe('awaiting human')
    expect(statusMetaOf(run({ status: 'failed' })).anim).toBe('none')
    expect(statusMetaOf(run({ status: 'done' })).color).toBe('var(--status-done)')
  })
})
