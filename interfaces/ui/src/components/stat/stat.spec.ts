import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Stat from './Stat.vue'

describe('Stat', () => {
  it('renders label and value', () => {  // clause: STAT-1
    const w = mount(Stat, { props: { label: 'Events', value: 412 } })
    expect(w.find('.label').text()).toBe('Events')
    expect(w.find('[data-testid="stat-value"]').text()).toBe('412')
  })

  it('renders a pip only when given', () => {  // clause: STAT-2
    expect(mount(Stat, { props: { label: 'x', value: 1 } }).find('.cmp-status-pip').exists()).toBe(false)
    expect(mount(Stat, { props: { label: 'x', value: 1, pip: 'done' } }).find('.cmp-status-pip').classes()).toContain('cmp-status-pip-done')
  })

  it('dashes absent values, keeps zero', () => {  // clause: STAT-3
    expect(mount(Stat, { props: { label: 'x', value: null } }).find('[data-testid="stat-value"]').text()).toBe('—')
    expect(mount(Stat, { props: { label: 'x', value: 0 } }).find('[data-testid="stat-value"]').text()).toBe('0')
  })
})
