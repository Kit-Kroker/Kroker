import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FooterBar from './FooterBar.vue'

describe('FooterBar', () => {
  it('renders the left and right texts', () => {  // clause: FOOTER_BAR-1
    const w = mount(FooterBar, {
      props: { left: '5 priced runs, 2 left out', right: '⌘K commands' },
    })
    expect(w.text()).toContain('5 priced runs, 2 left out')
    expect(w.text()).toContain('⌘K commands')
  })
})

describe('FooterBar (chaos, 018 T009 RED)', () => {
  it('renders nothing in a slot given an empty string, without throwing', () => {  // clause: FOOTER_BAR-1
    const w = mount(FooterBar, { props: { left: '', right: '' } })
    expect(w.text()).not.toContain('undefined')
    expect(w.text().trim()).toBe('')
  })
})
