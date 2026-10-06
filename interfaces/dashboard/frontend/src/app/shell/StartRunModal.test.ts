import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import StartRunModal from './StartRunModal.vue'
import { useUiStore } from '../ui.store'
import { useFleetStore } from '../../shared/fleet.store'

// The mocked startRun records its input (011 T014: the budget must reach
// fleet.startRun) and serves a mutable return so a test can hand back a run
// carrying a budgetNotice.
const h = vi.hoisted(() => ({
  startRunCalls: [] as { title: string; repo: string; mode: string; budget?: number | null }[],
  startRunReturn: null as Record<string, unknown> | null,
}))

vi.mock('../../api/client', () => ({
  api: {
    listRuns: vi.fn(async () => [{ id: 'feature-add-sso', title: 'Add SSO' }]),
    startRun: vi.fn(
      async (input: { title: string; repo: string; mode: string; budget?: number | null }) => {
        h.startRunCalls.push(input)
        return h.startRunReturn ?? { id: 'feature-add-sso', title: input.title }
      },
    ),
  },
}))

beforeEach(() => {
  setActivePinia(createPinia())
  h.startRunCalls.length = 0
  h.startRunReturn = null
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
    // 011 T014: no budget in the form -> startRun is told "no budget" (null),
    // never an empty string.
    expect(h.startRunCalls[0].budget).toBeNull()
  })

  it('a budget payload converts and reaches startRun', async () => {
    // The library payload emits budget as a string; the SHELL converts.
    const ui = useUiStore()
    ui.openStart()
    ui.startTitle = 'Add SSO'
    ui.startBudget = '5'
    const w = mount(StartRunModal)
    await w.find('[data-testid="submit"]').trigger('click')
    await flushPromises()
    expect(h.startRunCalls).toHaveLength(1)
    expect(h.startRunCalls[0].budget).toBe(5) // a number, not '5'
  })

  it('a budget notice on the returned run toasts', async () => {
    const notice =
      'Budget $5.00 counts priced planning-agent spend only. ' +
      'Coding-harness, crew and research-stage spend is not counted.'
    h.startRunReturn = { id: 'feature-budgeted', title: 'Add SSO', budgetNotice: notice }
    const ui = useUiStore()
    ui.openStart()
    ui.startTitle = 'Add SSO'
    ui.startBudget = '5'
    const w = mount(StartRunModal)
    await w.find('[data-testid="submit"]').trigger('click')
    await flushPromises()
    expect(ui.toasts.some((t) => t.msg.includes('Budget $5.00 counts priced planning-agent spend only'))).toBe(
      true,
    )
  })

  it('backdrop click closes the modal', async () => {
    const ui = useUiStore()
    ui.openStart()
    const w = mount(StartRunModal)
    await w.find('[data-testid="backdrop"]').trigger('click')
    expect(ui.startOpen).toBe(false)
  })
})
