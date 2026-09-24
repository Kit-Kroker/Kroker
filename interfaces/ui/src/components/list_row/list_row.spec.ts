import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ListRow from './ListRow.vue'

describe('ListRow', () => {
  it('reflects selection', () => {  // clause: LIST_ROW-1
    const on = mount(ListRow, { props: { selected: true } })
    expect(on.classes()).toContain('is-selected')
    expect(on.attributes('aria-current')).toBe('true')
    expect(mount(ListRow).attributes('aria-current')).toBeUndefined()
  })

  it('emits select unless disabled', async () => {  // clause: LIST_ROW-2
    const w = mount(ListRow)
    await w.trigger('click')
    expect(w.emitted('select')).toHaveLength(1)
    const d = mount(ListRow, { props: { disabled: true } })
    await d.trigger('click')
    expect(d.emitted('select')).toBeUndefined()
  })

  it('is a native button', () => {  // clause: LIST_ROW-3
    const w = mount(ListRow)
    expect(w.element.tagName).toBe('BUTTON')
    expect(w.attributes('type')).toBe('button')
  })

  it('renders leading and meta only when supplied', () => {  // clause: LIST_ROW-4
    expect(mount(ListRow, { slots: { default: 'x' } }).find('.meta').exists()).toBe(false)
    const w = mount(ListRow, { slots: { default: 'x', leading: 'L', meta: 'M' } })
    expect(w.find('.leading').text()).toBe('L')
    expect(w.find('.meta').text()).toBe('M')
  })
})
