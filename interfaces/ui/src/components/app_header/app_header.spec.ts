import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AppHeader from './AppHeader.vue'

const RouterLinkStub = {
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

// v5 nav API (018 data-model §4.2): the header takes lists, not counters.
interface NavItem {
  id: string
  label: string
  to: string
  badge?: number
  available: boolean
}

const nav = (overrides: Partial<NavItem>): NavItem => ({
  id: 'x',
  label: 'X',
  to: '/x',
  available: true,
  ...overrides,
})

const PRIMARY: NavItem[] = [
  nav({ id: 'fleet', label: 'Fleet', to: '/' }),
  nav({ id: 'inbox', label: 'Inbox', to: '/inbox' }),
]
const SECONDARY: NavItem[] = [
  nav({ id: 'graphs', label: 'Graphs', to: '/graphs' }),
  nav({ id: 'compare', label: 'Compare', to: '/compare' }),
  nav({ id: 'interfaces', label: 'Interfaces', to: '/interfaces' }),
]

const RUN_SWITCH = {
  tabs: [
    { label: 'run feature-1', to: '/runs/feature-1', active: true },
    { label: 'run feature-2', to: '/runs/feature-2' },
  ],
  active: 'feature-1',
}

const mountHeader = (props: Record<string, unknown> = {}) =>
  mount(AppHeader, {
    props: { primary: PRIMARY, secondary: SECONDARY, badge: 2, ...props },
    global: { stubs: { RouterLink: RouterLinkStub } },
  })

describe('AppHeader (v5 rebuild, 018 T009 RED)', () => {
  it('renders primary then secondary items in order with their labels', () => {  // clause: APP_HEADER-1
    const w = mountHeader()
    const labels = w.findAll('[data-testid="nav-item"]').map((a) => a.text())
    expect(labels).toEqual(['Fleet', 'Inbox', 'Graphs', 'Compare', 'Interfaces'])
  })

  it('does not render items marked available: false', () => {  // clause: APP_HEADER-1
    const w = mountHeader({
      secondary: [
        nav({ id: 'graphs', label: 'Graphs', to: '/graphs' }),
        nav({ id: 'compare', label: 'Compare', to: '/compare', available: false }),
      ],
    })
    const labels = w.findAll('[data-testid="nav-item"]').map((a) => a.text())
    expect(labels).toEqual(['Fleet', 'Inbox', 'Graphs'])
    expect(w.text()).not.toContain('Compare')
  })

  it('renders the badge only when it is greater than zero, never a 0', () => {  // clause: APP_HEADER-1.1
    const withBadge = mountHeader({ badge: 2 })
    expect(withBadge.find('[data-testid="inbox-count"]').exists()).toBe(true)
    expect(withBadge.find('[data-testid="inbox-count"]').text()).toBe('2')

    const zero = mountHeader({ badge: 0 })
    expect(zero.find('[data-testid="inbox-count"]').exists()).toBe(false)
  })

  it('renders the run switch only when given, with the Observe and Design segment only when mode is set', () => {  // clause: APP_HEADER-3
    const without = mountHeader({ runSwitch: undefined })
    expect(without.find('[data-testid="run-switch"]').exists()).toBe(false)

    // A run switch without a mode shows run tabs only — no theme segments.
    const tabsOnly = mountHeader({
      runSwitch: { tabs: RUN_SWITCH.tabs, active: RUN_SWITCH.active },
    })
    expect(tabsOnly.find('[data-testid="run-switch"]').exists()).toBe(true)
    expect(tabsOnly.text()).not.toContain('Observe')
    expect(tabsOnly.text()).not.toContain('Design')

    const withMode = mountHeader({ runSwitch: { ...RUN_SWITCH, mode: 'observe' } })
    expect(withMode.find('[data-testid="run-switch"]').exists()).toBe(true)
    expect(withMode.text()).toContain('Observe')
    expect(withMode.text()).toContain('Design')
  })

  it('emits search and menu from the Search and the ⋯ buttons', async () => {  // clause: APP_HEADER-3
    const w = mountHeader()
    await w.find('[data-testid="header-search"]').trigger('click')
    expect(w.emitted('search')).toHaveLength(1)
    await w.find('[data-testid="header-menu"]').trigger('click')
    expect(w.emitted('menu')).toHaveLength(1)
  })

  it('has no stats element and no Start button', () => {  // clause: APP_HEADER-1
    const w = mountHeader()
    expect(w.find('.stats').exists()).toBe(false)
    expect(w.find('[data-testid="stats"]').exists()).toBe(false)
    expect(w.find('[data-testid="start-btn"]').exists()).toBe(false)
  })

  it('marks the active run-switch tab with the stable tab-active class', () => {  // clause: APP_HEADER-2
    const w = mountHeader({ runSwitch: { ...RUN_SWITCH, mode: 'observe' } })
    const active = w.findAll('[data-testid="run-switch"] .tab-active')
    expect(active).toHaveLength(1)
    expect(active[0].text()).toBe('run feature-1')
  })
})

describe('AppHeader (chaos, 018 T009 RED)', () => {
  it('renders a NavItem own badge next to its label and omits 0/undefined badges', () => {  // clause: APP_HEADER-1.1
    const w = mountHeader({
      primary: [
        nav({ id: 'fleet', label: 'Fleet', to: '/', badge: 3 }),
        nav({ id: 'inbox', label: 'Inbox', to: '/inbox', badge: 0 }),
      ],
      secondary: [],
    })
    const texts = w.findAll('[data-testid="nav-item"]').map((a) => a.text())
    // Fleet's own badge shows; a badge of 0 and an absent badge show nothing.
    expect(texts.some((t) => t.includes('Fleet') && t.includes('3'))).toBe(true)
    expect(texts.some((t) => t.includes('0'))).toBe(false)
    expect(texts.some((t) => t.includes('Inbox') && /\d/.test(t))).toBe(false)
  })

  it('renders zero .tab-active elements when no run-switch tab is active', () => {  // clause: APP_HEADER-2
    const tabs = RUN_SWITCH.tabs.map(({ active: _active, ...rest }) => rest)
    const w = mountHeader({ runSwitch: { tabs, active: 'no-such-run' } })
    // The switch itself must exist — otherwise the zero-count is vacuous.
    expect(w.find('[data-testid="run-switch"]').exists()).toBe(true)
    expect(w.findAll('[data-testid="run-switch"] .tab-active')).toHaveLength(0)
  })

  it('keeps the header skeleton (search/menu buttons) when every list is empty', () => {  // clause: APP_HEADER-3
    const w = mountHeader({ primary: [], secondary: [], badge: 0 })
    expect(w.find('[data-testid="header-search"]').exists()).toBe(true)
    expect(w.find('[data-testid="header-menu"]').exists()).toBe(true)
  })
})
