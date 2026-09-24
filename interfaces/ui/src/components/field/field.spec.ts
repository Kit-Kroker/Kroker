import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Field from './Field.vue'

describe('Field', () => {
  it('binds the label to the control', () => {  // clause: FIELD-1
    const w = mount(Field, { props: { label: 'Comment', modelValue: '' } })
    const id = w.find('[data-testid="field-control"]').attributes('id')
    expect(id).toBeTruthy()
    expect(w.find('label').attributes('for')).toBe(id)
  })

  it('marks an error invalid, alerting and described', () => {  // clause: FIELD-2
    const w = mount(Field, { props: { label: 'J', modelValue: '', error: 'Required' } })
    const control = w.find('[data-testid="field-control"]')
    const err = w.find('[data-testid="field-error"]')
    expect(w.classes()).toContain('is-invalid')
    expect(control.attributes('aria-invalid')).toBe('true')
    expect(err.attributes('role')).toBe('alert')
    expect(control.attributes('aria-describedby')).toBe(err.attributes('id'))
  })

  it('shows the hint only without an error', () => {  // clause: FIELD-3
    const hinted = mount(Field, { props: { label: 'C', modelValue: '', hint: 'h' } })
    expect(hinted.find('[data-testid="field-hint"]').exists()).toBe(true)
    const both = mount(Field, { props: { label: 'C', modelValue: '', hint: 'h', error: 'e' } })
    expect(both.find('[data-testid="field-hint"]').exists()).toBe(false)
    expect(both.find('[data-testid="field-error"]').text()).toBe('e')
  })

  it('emits the raw value untrimmed', async () => {  // clause: FIELD-4
    const w = mount(Field, { props: { label: 'C', modelValue: '' } })
    await w.find('[data-testid="field-control"]').setValue('  split auth ')
    expect(w.emitted('update:modelValue')).toEqual([['  split auth ']])
  })
})
