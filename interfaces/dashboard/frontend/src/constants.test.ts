import { describe, it, expect } from 'vitest'
import { ARTIFACTS, STATUS_KINDS } from './constants'

// The stage list moved to the server (E-76 spec U4): the strip reads
// catalog.canonical_stages, so no TS stage list is asserted here any more.
describe('constants', () => {
  it('has 14 artifacts', () => {
    expect(ARTIFACTS).toHaveLength(14)
  })

  it('exposes the status kinds list', () => {
    expect(STATUS_KINDS).toContain('running')
    expect(STATUS_KINDS).toContain('blocked')
    expect(STATUS_KINDS).toContain('failed')
    expect(STATUS_KINDS).toContain('done')
  })
})
