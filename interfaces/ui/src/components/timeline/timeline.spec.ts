import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Timeline from './Timeline.vue'

const items = [
  { id: 2, from: 'failed', to: 'in_progress', at: 'b', detail: 'reset' },
  { id: 1, to: 'pending', at: 'a' },
]

describe('Timeline', () => {
  it('renders entries in supplied order', () => {  // clause: TIMELINE-1
    const w = mount(Timeline, { props: { items } })
    expect(w.findAll('[data-testid="timeline-entry"]').map((e) => e.find('.when').text())).toEqual(['b', 'a'])
  })

  it('marks with kind, falling back to to', () => {  // clause: TIMELINE-2
    const w = mount(Timeline, { props: { items: [{ id: 1, to: 'approved', kind: 'done', at: 'x' }, { id: 2, to: 'failed', at: 'y' }] } })
    const pips = w.findAll('.cmp-status-pip')
    expect(pips[0].classes()).toContain('cmp-status-pip-done')
    expect(pips[1].classes()).toContain('cmp-status-pip-failed')
  })

  it('renders from and detail only when supplied', () => {  // clause: TIMELINE-3
    const w = mount(Timeline, { props: { items } })
    const [first, second] = w.findAll('[data-testid="timeline-entry"]')
    expect(first.find('.from').exists()).toBe(true)
    expect(first.find('[data-testid="timeline-detail"]').text()).toBe('reset')
    expect(second.find('.from').exists()).toBe(false)
    expect(second.find('[data-testid="timeline-detail"]').exists()).toBe(false)
  })

  it('renders the empty slot with no items', () => {  // clause: TIMELINE-4
    const w = mount(Timeline, { props: { items: [] }, slots: { empty: 'Nothing' } })
    expect(w.find('ol').exists()).toBe(false)
    expect(w.text()).toBe('Nothing')
  })
})
