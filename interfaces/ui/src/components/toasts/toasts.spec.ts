import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Toasts from './Toasts.vue'

describe('Toasts', () => {
  it('renders every supplied toast in order', () => {  // clause: TOASTS-1
    const toasts = [
      { id: '1', msg: 'First toast' },
      { id: '2', msg: 'Second toast' },
    ]
    const w = mount(Toasts, { props: { toasts } })
    const items = w.findAll('[data-testid="toast"]')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toBe('First toast')
    expect(items[1].text()).toBe('Second toast')
  })

  it('renders nothing at all when toasts list is empty', () => {  // clause: TOASTS-1.1
    const w = mount(Toasts, { props: { toasts: [] } })
    expect(w.findAll('[data-testid="toast"]')).toHaveLength(0)
    expect(w.find('.cmp-toasts').exists()).toBe(false)
  })
})
