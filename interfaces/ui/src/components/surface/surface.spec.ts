import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Surface from './Surface.vue'

describe('Surface', () => {
  it('carries its elevation class, flat by default', () => {  // clause: SURFACE-1
    expect(mount(Surface).classes()).toContain('cmp-surface-flat')
    expect(mount(Surface, { props: { elevation: 'overlay' } }).classes()).toContain('cmp-surface-overlay')
  })

  it('renders as the requested element', () => {  // clause: SURFACE-2
    expect(mount(Surface).element.tagName).toBe('DIV')
    expect(mount(Surface, { props: { as: 'ul' } }).element.tagName).toBe('UL')
  })

  it('carries its padding step', () => {  // clause: SURFACE-3
    expect(mount(Surface).classes()).toContain('cmp-surface-pad-md')
    expect(mount(Surface, { props: { padding: 'sm' } }).classes()).toContain('cmp-surface-pad-sm')
  })
})
