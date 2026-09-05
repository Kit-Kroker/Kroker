import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StageDots from './StageDots.vue'

import type { StageDot } from './StageDots.vue'

const dots = (...states: string[]) =>
  states.map((state, i) => ({ stage: `s${i}`, state })) as unknown as StageDot[]

describe('StageDots', () => {
  it('renders one mark per stage in supplied order', () => {  // clause: STAGE_DOTS-1
    const w = mount(StageDots, { props: { dots: dots('done', 'active', 'pending') } })
    const marks = w.findAll('[data-testid="stage-dot"]')
    expect(marks).toHaveLength(3)
    expect(marks[0].classes()).toContain('cmp-stage-dot-done')
    expect(marks[2].classes()).toContain('cmp-stage-dot-pending')
  })

  it('renders nothing for an empty stage list', () => {  // clause: STAGE_DOTS-1.1
    const w = mount(StageDots, { props: { dots: [] } })
    expect(w.findAll('[data-testid="stage-dot"]')).toHaveLength(0)
  })

  it('fails rendering on an unknown state', () => {  // clause: STAGE_DOTS-1.2
    expect(() => mount(StageDots, { props: { dots: dots('sideways') } })).toThrow(/sideways/)
  })

  it('titles each mark with its stage and state', () => {  // clause: STAGE_DOTS-4
    const w = mount(StageDots, { props: { dots: [{ stage: 'qa', state: 'active' }] } })
    expect(w.find('[data-testid="stage-dot"]').attributes('title')).toBe('qa · active')
  })
})
