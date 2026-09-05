import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusPip from './StatusPip.vue'

describe('StatusPip', () => {
  it('renders a mark carrying its kind as a stable class', () => {  // clause: STATUS_PIP-1
    const w = mount(StatusPip, { props: { kind: 'running' } })
    expect(w.classes()).toContain('cmp-status-pip')
    expect(w.classes()).toContain('cmp-status-pip-running')
  })

  it('adds is-pulsing class when pulsing is true', () => {  // clause: STATUS_PIP-2
    const w = mount(StatusPip, { props: { kind: 'blocked', pulsing: true } })
    expect(w.classes()).toContain('is-pulsing')
  })

  it('omits is-pulsing class when pulsing is false or omitted', () => {  // clause: STATUS_PIP-2
    const w1 = mount(StatusPip, { props: { kind: 'done' } })
    expect(w1.classes()).not.toContain('is-pulsing')

    const w2 = mount(StatusPip, { props: { kind: 'done', pulsing: false } })
    expect(w2.classes()).not.toContain('is-pulsing')
  })
})
