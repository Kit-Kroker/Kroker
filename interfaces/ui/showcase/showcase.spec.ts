import { describe, it, expect } from 'vitest'
import { REGISTRY } from './registry'

// Vitest tier on purpose: the vacuity guard reads REGISTRY, whose profile
// sets import their .vue targets -- a chain Playwright's spec transform
// cannot parse (SFCs). Playwright specs drive the showcase DOM instead.
// SHOWCASE-1 must not pass vacuously forever: if no registered profile
// declared slots, the rendering test would rot into an unfailing locator.
describe('showcase slots', () => {
  it('at least one registered profile declares text slots (no vacuous slot support)', () => {  // clause: SHOWCASE-1
    expect(
      REGISTRY.some((set) => set.profiles.some((p) => p.slots && Object.keys(p.slots).length > 0)),
    ).toBe(true)
  })
})
