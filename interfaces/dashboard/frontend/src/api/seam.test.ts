import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusPip from '@kroker/ui/components/status_pip/StatusPip.vue'

describe('the @kroker/ui seam', () => {
  it('resolves a component from the ui package by package name', () => {
    const w = mount(StatusPip, { props: { kind: 'running' } })
    expect(w.find('.cmp-status-pip-running').exists()).toBe(true)
  })
})
