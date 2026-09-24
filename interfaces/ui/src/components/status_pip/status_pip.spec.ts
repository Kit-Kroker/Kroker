import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusPip from './StatusPip.vue'

describe('StatusPip', () => {
  it('renders a mark carrying its kind as a stable class', () => {  // clause: STATUS_PIP-1
    const w = mount(StatusPip, { props: { kind: 'running' } })
    expect(w.classes()).toContain('cmp-status-pip')
    expect(w.classes()).toContain('cmp-status-pip-running')
  })

  it('accepts board task kinds verbatim', () => {  // clause: STATUS_PIP-1
    for (const kind of ['in_progress', 'pending', 'quarantined']) {
      expect(mount(StatusPip, { props: { kind } }).classes()).toContain(`cmp-status-pip-${kind}`)
    }
  })

  it('adds is-pulsing class when pulsing is true', () => {  // clause: STATUS_PIP-2
    const w = mount(StatusPip, { props: { kind: 'blocked', pulsing: true } })
    expect(w.classes()).toContain('is-pulsing')
  })

  it('omits is-pulsing class when pulsing is false or omitted', () => {  // clause: STATUS_PIP-2
    expect(mount(StatusPip, { props: { kind: 'done' } }).classes()).not.toContain('is-pulsing')
    expect(mount(StatusPip, { props: { kind: 'done', pulsing: false } }).classes()).not.toContain('is-pulsing')
  })
})
