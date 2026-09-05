import { describe, it, expect } from 'vitest'
import { defineProfiles, profileId } from './profile'

const Stub = { template: '<i />' }

describe('profiles', () => {
  it('builds the showcase id every consumer agrees on', () => {
    expect(profileId('stage_dots', 'all-done')).toBe('showcase-stage_dots-all-done')
  })

  it('rejects a duplicate profile name', () => {
    expect(() =>
      defineProfiles({
        component: 'x', group: 'G', target: Stub,
        profiles: [
          { name: 'a', summary: 's', props: {} },
          { name: 'a', summary: 's', props: {} },
        ],
      }),
    ).toThrow('duplicate profile')
  })

  it('rejects a component with no profile', () => {
    expect(() =>
      defineProfiles({ component: 'x', group: 'G', target: Stub, profiles: [] }),
    ).toThrow('at least one profile')
  })
})
