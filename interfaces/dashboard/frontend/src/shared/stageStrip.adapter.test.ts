import { describe, it, expect } from 'vitest'
import { toStageDots } from './stageStrip.adapter'
import type { Run } from '../api/types'
import catalogJson from '../api/__fixtures__/graph/catalog.json'

const CANONICAL: string[] = catalogJson.canonical_stages

const mkRun = (over: Partial<Run> = {}): Run => ({
  id: 'run-1',
  title: 'Test run',
  mode: 'brownfield',
  repo: 'org/repo',
  activeStages: ['requirements'],
  status: 'running',
  blocker: null,
  cost: null,
  budget: 50,
  age: '10m',
  decisions: [],
  ...over,
})

describe('stage strip adapter', () => {
  it('renders one dot per served canonical stage, keyed by name', () => {
    const dots = toStageDots(mkRun({ activeStages: ['clarify'], status: 'running' }), CANONICAL)
    expect(dots.map((d) => d.stage)).toEqual(CANONICAL)
    expect(dots).toHaveLength(18)
    expect(dots.find((d) => d.stage === 'research')!.state).toBe('done')
    expect(dots.find((d) => d.stage === 'clarify')!.state).toBe('active')
    expect(dots.find((d) => d.stage === 'architecture')!.state).toBe('pending')
  })

  it('regression: a run at clarify never lights architecture (the 14/18 index defect)', () => {
    const dots = toStageDots(mkRun({ activeStages: ['clarify'], status: 'blocked' }), CANONICAL)
    expect(dots.filter((d) => d.state === 'blocked').map((d) => d.stage)).toEqual(['clarify'])
  })

  it('renders the strip from stageMarks verbatim; canonical stages absent from the marks render skipped', () => {
    // E75-OQ-1 / E-75 §8: a graph run's marks are the strip's source of
    // truth (E76-OQ-3's skipped becomes visible), in the served canonical
    // order -- never inferred from activeStages.
    const marked = {
      ...mkRun({ activeStages: ['architecture'], status: 'blocked' }),
      stageMarks: { intake: 'done', context: 'skipped', clarify: 'done', architecture: 'blocked' },
    } as never
    const dots = toStageDots(marked, CANONICAL)
    expect(dots.find((d) => d.stage === 'intake')!.state).toBe('done')
    expect(dots.find((d) => d.stage === 'context')!.state).toBe('skipped')
    expect(dots.find((d) => d.stage === 'architecture')!.state).toBe('blocked')
    expect(dots.find((d) => d.stage === 'research')!.state).toBe('skipped') // absent from the marks
    expect(dots.find((d) => d.stage === 'retro')!.state).toBe('skipped') // absent from the marks
  })

  it('renders nothing before the catalog loads', () => {
    expect(toStageDots(mkRun(), [])).toEqual([])
  })
})
