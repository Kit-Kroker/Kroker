import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import StartRunModal from './StartRunModal.vue'
import { useUiStore } from '../stores/ui'
import { useFleetStore } from '../stores/fleet'

vi.mock('../api/client', () => ({
  api: {
    listRuns: vi.fn(async () => [{ id: 'feature-add-sso', title: 'Add SSO' }]),
    startRun: vi.fn(async (input: { title: string; repo: string; mode: string }) => ({
      id: 'feature-add-sso', title: input.title,
    })),
  },
}))

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('StartRunModal', () => {
  it('renders nothing when the modal is closed', () => {
    const w = mount(StartRunModal)
    expect(w.find('[data-testid="modal-card"]').exists()).toBe(false)
  })

  it('requires a title before submitting', async () => {
    const ui = useUiStore()
    ui.openStart()
    const w = mount(StartRunModal)
    expect(w.find('[data-testid="submit"]').attributes('disabled')).toBeDefined()
  })

  it('starts a run, toasts, and closes', async () => {
    const ui = useUiStore()
    const fleet = useFleetStore()
    ui.openStart()
    ui.startTitle = 'Add SSO'
    const w = mount(StartRunModal)
    await w.find('[data-testid="submit"]').trigger('click')
    await flushPromises()
    expect(ui.toasts.some((t) => t.msg.includes('feature-add-sso'))).toBe(true)
    expect(ui.startOpen).toBe(false)
    expect(fleet.runs.find((r) => r.id === 'feature-add-sso')).toBeTruthy()
  })

  it('backdrop click closes the modal', async () => {
    const ui = useUiStore()
    ui.openStart()
    const w = mount(StartRunModal)
    await w.find('[data-testid="backdrop"]').trigger('click')
    expect(ui.startOpen).toBe(false)
  })
})
