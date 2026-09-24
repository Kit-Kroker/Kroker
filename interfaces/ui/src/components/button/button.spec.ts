import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Button from './Button.vue'

describe('Button', () => {
  it('carries variant and size classes, secondary/md by default', () => {  // clause: BUTTON-1
    expect(mount(Button).classes()).toEqual(expect.arrayContaining(['cmp-button', 'cmp-button-secondary', 'cmp-button-md']))
    expect(mount(Button, { props: { variant: 'danger', size: 'sm' } }).classes()).toEqual(expect.arrayContaining(['cmp-button-danger', 'cmp-button-sm']))
  })

  it('emits click when enabled', async () => {  // clause: BUTTON-2
    const w = mount(Button)
    await w.trigger('click')
    expect(w.emitted('click')).toHaveLength(1)
  })

  it('disabled and busy lock the button and emit nothing', async () => {  // clause: BUTTON-2
    // Widened loop type: VTU's mount props reject the literal union the
    // un-run prototype draft inferred (R-7 conformance; assertions unchanged).
    const locks: { disabled?: boolean; busy?: boolean }[] = [{ disabled: true }, { busy: true }]
    for (const props of locks) {
      const w = mount(Button, { props })
      expect(w.attributes('disabled')).toBeDefined()
      await w.trigger('click')
      expect(w.emitted('click')).toBeUndefined()
    }
    expect(mount(Button, { props: { busy: true } }).attributes('aria-busy')).toBe('true')
    expect(mount(Button).attributes('aria-busy')).toBeUndefined()
  })

  it('defaults to type=button', () => {  // clause: BUTTON-3
    expect(mount(Button).attributes('type')).toBe('button')
    expect(mount(Button, { props: { type: 'submit' } }).attributes('type')).toBe('submit')
  })
})
