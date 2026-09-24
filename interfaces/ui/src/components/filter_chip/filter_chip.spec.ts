import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FilterChip from './FilterChip.vue'

describe('FilterChip', () => {
  it('reflects selection in class and aria-pressed', () => {  // clause: FILTER_CHIP-1
    const on = mount(FilterChip, { props: { label: 'All', selected: true } })
    expect(on.classes()).toContain('is-selected')
    expect(on.attributes('aria-pressed')).toBe('true')
    expect(mount(FilterChip, { props: { label: 'All' } }).attributes('aria-pressed')).toBe('false')
  })

  it('emits select when pressed, selected or not; never when disabled', async () => {  // clause: FILTER_CHIP-2
    const a = mount(FilterChip, { props: { label: 'A', selected: true } })
    await a.trigger('click')
    expect(a.emitted('select')).toHaveLength(1)
    const d = mount(FilterChip, { props: { label: 'D', disabled: true } })
    await d.trigger('click')
    expect(d.emitted('select')).toBeUndefined()
  })

  it('renders zero and omits undefined counts', () => {  // clause: FILTER_CHIP-3
    expect(mount(FilterChip, { props: { label: 'Q', count: 0 } }).find('.count').text()).toBe('0')
    expect(mount(FilterChip, { props: { label: 'Q' } }).find('.count').exists()).toBe(false)
  })
})
