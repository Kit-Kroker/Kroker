import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusTag from './StatusTag.vue'

describe('StatusTag', () => {
  it('renders a pip of the same kind and the kind class', () => {  // clause: STATUS_TAG-1
    const w = mount(StatusTag, { props: { kind: 'failed' } })
    expect(w.classes()).toContain('cmp-status-tag-failed')
    expect(w.find('.cmp-status-pip').classes()).toContain('cmp-status-pip-failed')
  })

  it('derives the label from the kind unless given one', () => {  // clause: STATUS_TAG-2
    expect(mount(StatusTag, { props: { kind: 'in_progress' } }).find('.label').text()).toBe('In progress')
    expect(mount(StatusTag, { props: { kind: 'done', label: 'Merged' } }).find('.label').text()).toBe('Merged')
  })

  it('mono adds is-mono', () => {  // clause: STATUS_TAG-3
    expect(mount(StatusTag, { props: { kind: 'waiting', mono: true } }).classes()).toContain('is-mono')
    expect(mount(StatusTag, { props: { kind: 'waiting' } }).classes()).not.toContain('is-mono')
  })
})
