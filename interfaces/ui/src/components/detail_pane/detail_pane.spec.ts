import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DetailPane from './DetailPane.vue'
import DetailSection from './DetailSection.vue'

describe('DetailPane', () => {
  it('renders fields in order, mono by default', () => {  // clause: DETAIL_PANE-1
    const w = mount(DetailPane, { props: { title: 't', fields: [{ k: 'A', v: '1' }, { k: 'B', v: 'two', mono: false }] } })
    expect(w.findAll('dt').map((d) => d.text())).toEqual(['A', 'B'])
    const vals = w.findAll('[data-testid="detail-value"]')
    expect(vals[0].classes()).toContain('is-mono')
    expect(vals[1].classes()).not.toContain('is-mono')
  })

  it('renders an em dash for absent values', () => {  // clause: DETAIL_PANE-2
    const w = mount(DetailPane, { props: { title: 't', fields: [{ k: 'A', v: null }, { k: 'B', v: '' }, { k: 'C', v: 0 }] } })
    expect(w.findAll('[data-testid="detail-value"]').map((d) => d.text())).toEqual(['—', '—', '0'])
  })

  it('title is h2, section label is h3', () => {  // clause: DETAIL_PANE-3
    expect(mount(DetailPane, { props: { title: 'Task' } }).find('h2').text()).toBe('Task')
    expect(mount(DetailSection, { props: { label: 'Evidence' } }).find('h3').text()).toBe('Evidence')
  })

  it('omits the grid with no fields', () => {  // clause: DETAIL_PANE-4
    expect(mount(DetailPane, { props: { title: 't' } }).find('dl').exists()).toBe(false)
  })
})
