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
      { title: 'Add payments', repo: 'git@github.com:org/repo', mode: 'brownfield' },
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
})
