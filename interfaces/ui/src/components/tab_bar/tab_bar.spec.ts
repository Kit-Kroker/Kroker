import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TabBar from './TabBar.vue'

const tabs = [{ id: 'a', label: 'A' }, { id: 'b', label: 'B', count: 2 }, { id: 'c', label: 'C', count: 0, disabled: true }]

describe('TabBar', () => {
  it('marks the active tab', () => {  // clause: TAB_BAR-1
    const w = mount(TabBar, { props: { tabs, active: 'a' } })
    expect(w.find('[data-testid="tab-a"]').classes()).toContain('tab-active')
    expect(w.find('[data-testid="tab-a"]').attributes('aria-selected')).toBe('true')
    expect(w.find('[data-testid="tab-b"]').attributes('aria-selected')).toBe('false')
  })

  it('emits select for inactive enabled tabs only', async () => {  // clause: TAB_BAR-2
    const w = mount(TabBar, { props: { tabs, active: 'a' } })
    await w.find('[data-testid="tab-a"]').trigger('click')
    await w.find('[data-testid="tab-b"]').trigger('click')
    await w.find('[data-testid="tab-c"]').trigger('click')
    expect(w.emitted('select')).toEqual([['b']])
  })

  it('renders the badge only above zero', () => {  // clause: TAB_BAR-3
    const w = mount(TabBar, { props: { tabs, active: 'a' } })
    expect(w.find('[data-testid="tab-b"] [data-testid="tab-count"]').text()).toBe('2')
    expect(w.find('[data-testid="tab-c"] [data-testid="tab-count"]').exists()).toBe(false)
  })
})
