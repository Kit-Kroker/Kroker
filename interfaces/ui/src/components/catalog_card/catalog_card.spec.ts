import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CatalogCard from './CatalogCard.vue'

// 018 T058 (RED): the Graphs catalog card (S8, FR-044). Stable hooks the
// implementation (T059) must carry: catalog-kicker / catalog-name /
// catalog-sha / catalog-description / catalog-when / catalog-count (per chip)
// / catalog-action. Props per data-model §4.2: kicker, name, sha,
// description, when, counts: {label,n}[], action: {label}.

const PROPS = {
  kicker: 'shipped graph',
  name: 'default',
  sha: 'a021c25b8f7e012faaf9f4de9664d8cc5b11a977c1b878e20d50cfec78b23c38',
  description: 'The pre-code pipeline as shipped.',
  when: '2026-09-20',
  counts: [
    { label: 'nodes', n: 12 },
    { label: 'gates', n: 5 },
    { label: 'edges', n: 14 },
  ],
  action: { label: 'Open in Design' },
}

const mountCard = (over: Record<string, unknown> = {}) =>
  mount(CatalogCard, { props: { ...PROPS, ...over } })

describe('CatalogCard', () => {
  it('renders kicker, name, the sha in mono, description and when', () => {  // clause: CATALOG_CARD-1
    const w = mountCard()
    expect(w.find('[data-testid="catalog-kicker"]').text()).toBe('shipped graph')
    expect(w.find('[data-testid="catalog-name"]').text()).toBe('default')
    const sha = w.find('[data-testid="catalog-sha"]')
    expect(sha.text()).toContain('a021c25b')
    expect(sha.classes().join(' ')).toContain('mono')
    expect(w.find('[data-testid="catalog-description"]').text()).toBe('The pre-code pipeline as shipped.')
    expect(w.find('[data-testid="catalog-when"]').text()).toBe('2026-09-20')
  })

  it('a null description or when renders not measured, never the string null', () => {  // clause: CATALOG_CARD-1
    const w = mountCard({ description: null, when: null })
    expect(w.find('[data-testid="catalog-description"]').text()).toBe('not measured')
    expect(w.find('[data-testid="catalog-when"]').text()).toBe('not measured')
    expect(w.text()).not.toContain('null')
    expect(w.text()).not.toContain('undefined')
  })

  it('renders one count chip per entry with its label and number', () => {  // clause: CATALOG_CARD-2
    const w = mountCard()
    const chips = w.findAll('[data-testid="catalog-count"]')
    expect(chips).toHaveLength(3)
    expect(chips[0].text()).toContain('nodes')
    expect(chips[0].text()).toContain('12')
    expect(chips[1].text()).toContain('gates')
    expect(chips[1].text()).toContain('5')
    expect(chips[2].text()).toContain('edges')
    expect(chips[2].text()).toContain('14')
    // Zero renders as 0 — a real count, never hidden.
    const zeroed = mountCard({ counts: [{ label: 'gates', n: 0 }] })
    expect(zeroed.findAll('[data-testid="catalog-count"]')).toHaveLength(1)
    expect(zeroed.find('[data-testid="catalog-count"]').text()).toContain('0')
  })

  it('the action button emits act on click', async () => {  // clause: CATALOG_CARD-3
    const w = mountCard()
    const button = w.find('[data-testid="catalog-action"]')
    expect(button.text()).toBe('Open in Design')
    await button.trigger('click')
    expect(w.emitted('act')).toHaveLength(1)
  })
})
