import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CheckRow from './CheckRow.vue'

describe('CheckRow', () => {
  it('carries result and kind classes', () => {  // clause: CHECK_ROW-1
    const w = mount(CheckRow, { props: { name: 'x', kind: 'ABSOLUTE', ok: false } })
    expect(w.classes()).toEqual(expect.arrayContaining(['is-failing', 'cmp-check-row-absolute']))
    const p = mount(CheckRow, { props: { name: 'x', kind: 'ADVISORY', ok: true } })
    expect(p.classes()).toEqual(expect.arrayContaining(['is-ok', 'cmp-check-row-advisory']))
  })

  it('labels the mark by result', () => {  // clause: CHECK_ROW-3
    expect(mount(CheckRow, { props: { name: 'x', kind: 'ADVISORY', ok: true } }).find('.mark').attributes('aria-label')).toBe('passed')
    expect(mount(CheckRow, { props: { name: 'x', kind: 'ADVISORY', ok: false } }).find('.mark').attributes('aria-label')).toBe('failed')
  })
})
