import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Tag from './Tag.vue'

describe('Tag', () => {
  it('renders its slot with the tone class', () => {  // clause: TAG-1
    const w = mount(Tag, { slots: { default: 'Gate' } })
    expect(w.text()).toBe('Gate')
    expect(w.classes()).toContain('cmp-tag-neutral')
    expect(mount(Tag, { props: { tone: 'strong' } }).classes()).toContain('cmp-tag-strong')
  })

  it('mono adds is-mono', () => {  // clause: TAG-2
    expect(mount(Tag, { props: { mono: true } }).classes()).toContain('is-mono')
  })

  it('is a plain span', () => {  // clause: TAG-3
    const w = mount(Tag)
    expect(w.element.tagName).toBe('SPAN')
    expect(w.attributes('role')).toBeUndefined()
    expect(w.attributes('tabindex')).toBeUndefined()
  })
})
