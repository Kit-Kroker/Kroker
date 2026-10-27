import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AppHeader from './AppHeader.vue'
import { useInboxStore } from '../inbox.store'
import { useUiStore } from '../ui.store'

const RouterLinkStub = { template: '<a><slot /></a>' }

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('AppHeader', () => {
  it('shows the inbox badge count from the store', () => {
    const inbox = useInboxStore()
    inbox.items = [
      { id: 'q1', type: 'clarify', runId: 'r', round: 1, age: '1m', title: 't', body: 'b', suggestion: 's' },
      { id: 'g1', type: 'gate', gate: 'merge', runId: 'r', round: 1, age: '1m', title: 't', body: 'b' },
    ] as any

    const w = mount(AppHeader, { global: { stubs: { RouterLink: RouterLinkStub } } })
    // 018 T010: v5 header — sentence-case labels, badge only, no stats.
    expect(w.text()).toContain('Inbox')
    expect(w.find('[data-testid="inbox-count"]').text()).toBe('2')
  })

  it('START button opens the modal', async () => {
    const ui = useUiStore()
    const w = mount(AppHeader, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await w.find('[data-testid="start-btn"]').trigger('click')
    expect(ui.startOpen).toBe(true)
  })
})

// 018 T010 deleted the four 'honest spend' unit cases here: the v5 header
// carries no stats (S4); the fleet total moves to the footer's left side in
// T012, where the cases return against the footer wiring.
