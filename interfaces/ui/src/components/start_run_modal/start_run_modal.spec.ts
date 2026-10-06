import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StartRunModal from './StartRunModal.vue'

describe('StartRunModal', () => {
  it('emits submit with the supplied shape when valid', async () => {  // clause: START_RUN_MODAL-1
    const w = mount(StartRunModal, {
      props: {
        open: true,
        initialTitle: 'Add payments',
        initialRepo: 'git@github.com:org/repo',
        initialMode: 'brownfield',
      },
    })
    await w.find('[data-testid="submit"]').trigger('click')
    expect(w.emitted('submit')).toHaveLength(1)
    expect(w.emitted('submit')![0]).toEqual([
      { title: 'Add payments', repo: 'git@github.com:org/repo', mode: 'brownfield', budget: '' },
    ])
  })

  it('disables submit when title is empty', async () => {  // clause: START_RUN_MODAL-1.1
    const w = mount(StartRunModal, {
      props: {
        open: true,
        initialTitle: '   ',
      },
    })
    const submitBtn = w.find('[data-testid="submit"]')
    expect(submitBtn.attributes('disabled')).toBeDefined()
    await submitBtn.trigger('click')
    expect(w.emitted('submit')).toBeUndefined()
  })

  it('leaves open state to caller and emits close on cancel or backdrop click', async () => {  // clause: START_RUN_MODAL-2
    const w = mount(StartRunModal, {
      props: { open: true },
    })
    // Backdrop click emits close
    await w.find('[data-testid="backdrop"]').trigger('click')
    expect(w.emitted('close')).toHaveLength(1)

    // Cancel button emits close
    await w.find('.ghost').trigger('click')
    expect(w.emitted('close')).toHaveLength(2)

    // Still in DOM because open prop is controlled by parent
    expect(w.find('[data-testid="modal-card"]').exists()).toBe(true)
  })

  it('a budget that is not a number greater than 0 blocks the submit with a message', async () => {  // clause: START_RUN_MODAL-3
    // 011 T014 (RED): the two server messages, reused inline — zero is its
    // own case (omit the field), everything else non-numeric/non-positive
    // shares the greater-than message.
    const cases: Array<[string, string]> = [
      ['0', 'budget must be greater than 0; omit it to run without a budget'],
      ['-1', 'budget must be a number greater than 0'],
      ['abc', 'budget must be a number greater than 0'],
    ]
    for (const [value, message] of cases) {
      const w = mount(StartRunModal, {
        props: { open: true, initialTitle: 'Add payments' },
      })
      await w.find('[data-testid="start-budget-input"]').setValue(value)
      const error = w.find('[data-testid="start-budget-error"]')
      expect(error.exists(), `error shown for ${value}`).toBe(true)
      expect(error.text()).toContain(message)
      const submitBtn = w.find('[data-testid="submit"]')
      expect(submitBtn.attributes('disabled')).toBeDefined()
      await submitBtn.trigger('click')
      expect(w.emitted('submit'), `no submit for ${value}`).toBeUndefined()
    }
  })

  it('a valid budget rides the payload and shows no error', async () => {  // clause: START_RUN_MODAL-3
    const w = mount(StartRunModal, {
      props: { open: true, initialTitle: 'Add payments', initialBudget: '5' },
    })
    await w.find('[data-testid="submit"]').trigger('click')
    expect(w.find('[data-testid="start-budget-error"]').exists()).toBe(false)
    expect(w.emitted('submit')![0]).toEqual([
      { title: 'Add payments', repo: '', mode: 'brownfield', budget: '5' },
    ])
  })
})
