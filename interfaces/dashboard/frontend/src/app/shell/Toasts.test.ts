import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Toasts from './Toasts.vue'
import { useUiStore } from '../ui.store'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('Toasts', () => {
  it('renders each toast from the ui store', () => {
    const ui = useUiStore()
    // 018 R-10: kinds, not colours — the theme maps them (raw-colour gate).
    ui.toasts.push({ id: 1, msg: 'saved', kind: 'done' })
    ui.toasts.push({ id: 2, msg: 'rejected', kind: 'failed' })
    const w = mount(Toasts)
    const items = w.findAll('[data-testid="toast"]')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('saved')
  })
})
