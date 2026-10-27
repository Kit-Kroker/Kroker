import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ToggleMenu from './ToggleMenu.vue'

// 018 T016 (RED): the ⋯ display menu. Stable hooks the implementation (T017)
// must carry: data-testid toggle-item on each row and toggle-check on a row
// that is on.

const ITEMS = [
  { id: 'payloads', label: 'Payloads', desc: 'show edge payloads on the canvas', on: true },
  { id: 'grid', label: 'Grid', desc: 'show the dot grid behind the canvas', on: false },
]

const mountMenu = (items = ITEMS) => mount(ToggleMenu, { props: { items } })

const rows = (w: ReturnType<typeof mountMenu>) => w.findAll('[data-testid="toggle-item"]')

describe('ToggleMenu', () => {
  it('renders each item with its label and description', () => {  // clause: TOGGLE_MENU-1
    const w = mountMenu()
    const items = rows(w)
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('Payloads')
    expect(items[0].text()).toContain('show edge payloads on the canvas')
    expect(items[1].text()).toContain('Grid')
    expect(items[1].text()).toContain('show the dot grid behind the canvas')
  })

  it('shows a check only on items that are on', () => {  // clause: TOGGLE_MENU-2
    const w = mountMenu()
    const items = rows(w)
    expect(items[0].find('[data-testid="toggle-check"]').exists()).toBe(true)
    expect(items[1].find('[data-testid="toggle-check"]').exists()).toBe(false)
  })

  it('clicking an item emits toggle with that item id', async () => {  // clause: TOGGLE_MENU-3
    const w = mountMenu()
    await rows(w)[1].trigger('click')
    expect(w.emitted('toggle')).toEqual([['grid']])
  })
})

describe('ToggleMenu (chaos, 018 T016 RED)', () => {
  it('an all-off menu renders zero toggle-check elements anywhere', () => {  // clause: TOGGLE_MENU-2
    const w = mountMenu(ITEMS.map((item) => ({ ...item, on: false })))
    expect(rows(w)).toHaveLength(2)
    expect(w.findAll('[data-testid="toggle-check"]')).toHaveLength(0)
  })

  it('clicking several rows emits toggle once per click, in click order', async () => {  // clause: TOGGLE_MENU-3
    const w = mountMenu()
    await rows(w)[1].trigger('click')
    await rows(w)[0].trigger('click')
    await rows(w)[1].trigger('click')
    expect(w.emitted('toggle')).toEqual([['grid'], ['payloads'], ['grid']])
  })

  it('an item with an empty desc renders without the string undefined', () => {  // clause: TOGGLE_MENU-1
    const w = mountMenu([{ id: 'bare', label: 'Bare', desc: '', on: false }])
    const items = rows(w)
    expect(items).toHaveLength(1)
    expect(items[0].text()).toContain('Bare')
    expect(items[0].text()).not.toContain('undefined')
  })
})
