import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Toasts from './Toasts.vue'
import { useUiStore } from '../stores/ui'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('Toasts', () => {
  it('renders each toast from the ui store', () => {
    const ui = useUiStore()
    ui.toasts.push({ id: 1, msg: 'saved', color: '#4fae7f' })
    ui.toasts.push({ id: 2, msg: 'rejected', color: '#e06c55' })
    const w = mount(Toasts)
    const items = w.findAll('[data-testid="toast"]')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('saved')
  })
})
