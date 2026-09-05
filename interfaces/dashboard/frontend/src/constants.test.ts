import { describe, it, expect } from 'vitest'
import { STAGES, ARTIFACTS, STATUS_KINDS } from './constants'

describe('constants', () => {
  it('has 14 stages aligned with 14 artifacts', () => {
    expect(STAGES).toHaveLength(14)
    expect(ARTIFACTS).toHaveLength(14)
  })

  it('matches the DAG indices used elsewhere', () => {
    expect(STAGES[0]).toBe('intake')
    expect(STAGES[2]).toBe('context')
    expect(STAGES[5]).toBe('architecture')
    expect(STAGES[11]).toBe('quality_gate')
    expect(STAGES[13]).toBe('retro')
  })

  it('exposes the status kinds list', () => {
    expect(STATUS_KINDS).toContain('running')
    expect(STATUS_KINDS).toContain('blocked')
    expect(STATUS_KINDS).toContain('failed')
    expect(STATUS_KINDS).toContain('done')
  })
})
