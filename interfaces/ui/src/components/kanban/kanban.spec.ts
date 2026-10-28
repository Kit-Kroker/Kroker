import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Kanban from './Kanban.vue'

// 018 T051 (RED): the v5 run board kanban (S7, V7). Stable hooks the
// implementation (T052) must carry: kanban-column per column, kanban-card
// per card, kanban-link for the optional footer link. Props per data-model
// §4.2: columns { id, title, status, count, cards: { id, title?, tag,
// tagKind, meta }[] }[], link?: { label, to }.

const RouterLinkStub = { props: ['to'], template: '<a data-testid="stub-link"><slot /></a>' }

const card = (over: Record<string, unknown> = {}) => ({
  id: 'task:T07#1',
  title: 'Fix the retry loop',
  tag: 'T07',
  tagKind: 'in_progress',
  meta: 'fix attempts: 3',
  ...over,
})

const COLUMNS = [
  {
    id: 'in_progress',
    title: 'In progress',
    status: 'in_progress',
    count: 2,
    cards: [
      card(),
      card({ id: 'task:T09#1', title: undefined, tag: 'T09', tagKind: 'in_progress', meta: 'fix attempts: 1' }),
    ],
  },
  {
    id: 'blocked',
    title: 'Blocked',
    status: 'blocked',
    count: 1,
    cards: [card({ id: 'task:T12#1', title: 'Rate limit', tag: 'T12', tagKind: 'blocked', meta: 'r2' })],
  },
  {
    id: 'done',
    title: 'Done',
    status: 'done',
    count: 0,
    cards: [],
  },
]

const mountKanban = (props: Record<string, unknown> = {}) =>
  mount(Kanban, {
    props: { columns: COLUMNS, ...props },
    global: { stubs: { RouterLink: RouterLinkStub } },
  })

describe('Kanban', () => {
  it('renders one column per entry with its title and count', () => {  // clause: KANBAN-1
    const w = mountKanban()
    const columns = w.findAll('[data-testid="kanban-column"]')
    expect(columns).toHaveLength(3)
    expect(columns[0].text()).toContain('In progress')
    expect(columns[0].text()).toContain('2')
    expect(columns[1].text()).toContain('Blocked')
    expect(columns[1].text()).toContain('1')
    expect(columns[2].text()).toContain('Done')
    expect(columns[2].text()).toContain('0')
  })

  it('renders each card of its column with id, title, tag and meta', () => {  // clause: KANBAN-2
    const w = mountKanban()
    const cards = w.findAll('[data-testid="kanban-card"]')
    expect(cards).toHaveLength(3)
    const first = cards[0]
    expect(first.text()).toContain('task:T07#1')
    expect(first.text()).toContain('Fix the retry loop')
    expect(first.text()).toContain('T07')
    expect(first.text()).toContain('fix attempts: 3')
    // The tag carries its kind as a stable class (the wire status vocabulary).
    expect(first.find('[data-testid="kanban-tag"]').classes().join(' ')).toContain('in_progress')
  })

  it('a card without a title renders its id, tag and meta and never the string undefined', () => {  // clause: KANBAN-2
    const w = mountKanban()
    const bare = w.findAll('[data-testid="kanban-card"]')[1]
    expect(bare.text()).toContain('task:T09#1')
    expect(bare.text()).toContain('T09')
    expect(bare.text()).not.toContain('undefined')
  })

  it('renders the link only when one is given', () => {  // clause: KANBAN-3
    const without = mountKanban()
    expect(without.find('[data-testid="kanban-link"]').exists()).toBe(false)

    const withLink = mountKanban({ link: { label: 'Open full Agent Board →', to: '/runs/r1/board' } })
    const link = withLink.find('[data-testid="kanban-link"]')
    expect(link.exists()).toBe(true)
    expect(link.text()).toBe('Open full Agent Board →')
    expect(withLink.findComponent(RouterLinkStub).props('to')).toBe('/runs/r1/board')
  })

  it('an empty columns array renders no column and no card, without throwing', () => {  // clause: KANBAN-1
    const w = mountKanban({ columns: [] })
    expect(w.findAll('[data-testid="kanban-column"]')).toHaveLength(0)
    expect(w.findAll('[data-testid="kanban-card"]')).toHaveLength(0)
  })
})
