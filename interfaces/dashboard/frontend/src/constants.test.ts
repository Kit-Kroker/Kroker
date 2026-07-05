import { describe, it, expect } from 'vitest'
import { STAGES, ARTIFACTS, STATUS_COLORS } from './constants'

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

  it('exposes the status color palette', () => {
    expect(STATUS_COLORS.running).toBe('#5b9dd9')
    expect(STATUS_COLORS.blocked).toBe('#e0b050')
    expect(STATUS_COLORS.failed).toBe('#e06c55')
    expect(STATUS_COLORS.done).toBe('#4fae7f')
  })
})
