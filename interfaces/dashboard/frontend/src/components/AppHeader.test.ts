import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AppHeader from './AppHeader.vue'
import { useFleetStore } from '../stores/fleet'
import { useInboxStore } from '../stores/inbox'
import { useUiStore } from '../stores/ui'

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
    const fleet = useFleetStore()
    fleet.runs = [{ id: 'r1', status: 'running', cost: 2 } as any, { id: 'r2', status: 'blocked', cost: 3 } as any]

    const w = mount(AppHeader, { global: { stubs: { RouterLink: RouterLinkStub } } })
    expect(w.text()).toContain('INBOX')
    expect(w.find('[data-testid="inbox-count"]').text()).toBe('2')
    expect(w.text()).toContain('$5.00')
  })

  it('START button opens the modal', async () => {
    const ui = useUiStore()
    const w = mount(AppHeader, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await w.find('[data-testid="start-btn"]').trigger('click')
    expect(ui.startOpen).toBe(true)
  })
})
