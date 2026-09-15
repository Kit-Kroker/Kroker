import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GateDecision from './GateDecision.vue'

describe('GateDecision', () => {
  it('emits the pressed outcome with the trimmed comment', async () => {  // clause: GATE_DECISION-1
    const w = mount(GateDecision, { props: { title: 'arch' } })
    await w.find('[data-testid="gate-comment"]').setValue('  looks good ')
    await w.find('[data-testid="gate-approve"]').trigger('click')
    await w.find('[data-testid="gate-reject"]').trigger('click')
    expect(w.emitted('decide')).toEqual([
      [{ outcome: 'approve', comment: 'looks good' }],
      [{ outcome: 'reject', comment: 'looks good' }],
    ])
  })

  it('disables revise until the comment is non-blank', async () => {  // clause: GATE_DECISION-2
    const w = mount(GateDecision, { props: { title: 'arch' } })
    const revise = w.find('[data-testid="gate-revise"]')
    expect(revise.attributes('disabled')).toBeDefined()
    expect(w.find('[data-testid="gate-approve"]').attributes('disabled')).toBeUndefined()
    await w.find('[data-testid="gate-comment"]').setValue('   ')
    expect(revise.attributes('disabled')).toBeDefined()
    await w.find('[data-testid="gate-comment"]').setValue('split auth')
    expect(revise.attributes('disabled')).toBeUndefined()
    await revise.trigger('click')
    expect(w.emitted('decide')).toEqual([[{ outcome: 'revise', comment: 'split auth' }]])
  })

  it('emits nothing while busy', async () => {  // clause: GATE_DECISION-3
    const w = mount(GateDecision, { props: { title: 'arch', busy: true } })
    for (const id of ['gate-approve', 'gate-revise', 'gate-reject']) {
      expect(w.find(`[data-testid="${id}"]`).attributes('disabled')).toBeDefined()
    }
    await w.find('[data-testid="gate-approve"]').trigger('click')
    await w.find('[data-testid="gate-reject"]').trigger('click')
    expect(w.emitted('decide')).toBeUndefined()
  })

  // --- chaos: contract corners the happy paths above leave open ----------

  it('the disabled prop alone locks every control and emits nothing', async () => {  // clause: GATE_DECISION-3
    const w = mount(GateDecision, { props: { title: 'arch', disabled: true } })
    for (const id of ['gate-approve', 'gate-revise', 'gate-reject']) {
      expect(w.find(`[data-testid="${id}"]`).attributes('disabled')).toBeDefined()
    }
    await w.find('[data-testid="gate-comment"]').setValue('a comment')
    for (const id of ['gate-approve', 'gate-revise', 'gate-reject']) {
      await w.find(`[data-testid="${id}"]`).trigger('click')
    }
    expect(w.emitted('decide')).toBeUndefined()
  })

  it('busy beats a typed comment: revise stays locked and no control emits', async () => {  // clause: GATE_DECISION-3
    const w = mount(GateDecision, { props: { title: 'arch', busy: true } })
    await w.find('[data-testid="gate-comment"]').setValue('a comment')
    for (const id of ['gate-approve', 'gate-revise', 'gate-reject']) {
      expect(w.find(`[data-testid="${id}"]`).attributes('disabled')).toBeDefined()
      await w.find(`[data-testid="${id}"]`).trigger('click')
    }
    expect(w.emitted('decide')).toBeUndefined()
  })

  it('approve and reject never need a comment and always trim it', async () => {  // clause: GATE_DECISION-1
    const w = mount(GateDecision, { props: { title: 'arch' } })
    await w.find('[data-testid="gate-approve"]').trigger('click')
    await w.find('[data-testid="gate-comment"]').setValue('   ')
    await w.find('[data-testid="gate-reject"]').trigger('click')
    await w.find('[data-testid="gate-comment"]').setValue('  a  b ')
    await w.find('[data-testid="gate-approve"]').trigger('click')
    expect(w.emitted('decide')).toEqual([
      [{ outcome: 'approve', comment: '' }],
      [{ outcome: 'reject', comment: '' }],
      [{ outcome: 'approve', comment: 'a  b' }],  // outer trim only: inner spacing survives
    ])
  })

  it('clearing the comment re-disables revise and silences it', async () => {  // clause: GATE_DECISION-2
    const w = mount(GateDecision, { props: { title: 'arch' } })
    const revise = w.find('[data-testid="gate-revise"]')
    await w.find('[data-testid="gate-comment"]').setValue('split auth')
    expect(revise.attributes('disabled')).toBeUndefined()
    await w.find('[data-testid="gate-comment"]').setValue('')
    expect(revise.attributes('disabled')).toBeDefined()
    await revise.trigger('click')
    expect(w.emitted('decide')).toBeUndefined()
  })

  it('busy flips with props: locks mid-flight, unlocks when the caller clears it', async () => {  // clause: GATE_DECISION-3
    const w = mount(GateDecision, { props: { title: 'arch' } })
    await w.find('[data-testid="gate-comment"]').setValue('split auth')
    await w.setProps({ busy: true })
    for (const id of ['gate-approve', 'gate-revise', 'gate-reject']) {
      expect(w.find(`[data-testid="${id}"]`).attributes('disabled')).toBeDefined()
      await w.find(`[data-testid="${id}"]`).trigger('click')
    }
    expect(w.emitted('decide')).toBeUndefined()
    await w.setProps({ busy: false })  // the component never clears busy; the caller does
    expect(w.find('[data-testid="gate-approve"]').attributes('disabled')).toBeUndefined()
    await w.find('[data-testid="gate-approve"]').trigger('click')
    expect(w.emitted('decide')).toEqual([[{ outcome: 'approve', comment: 'split auth' }]])
  })
})
