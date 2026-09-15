import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import IssueList from './IssueList.vue'

const items = [
  { key: 'a', severity: 'error' as const, message: 'bad edge', targetLabel: 'x → y', focusKey: 'e1' },
  { key: 'b', severity: 'warning' as const, message: 'unreachable', targetLabel: 'graph', focusKey: null },
]

describe('IssueList', () => {
  it('renders rows in order with severity classes', () => {  // clause: ISSUE_LIST-1
    const w = mount(IssueList, { props: { items } })
    const rows = w.findAll('[data-testid="issue"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].classes()).toContain('cmp-issue-error')
    expect(rows[1].classes()).toContain('cmp-issue-warning')
    expect(mount(IssueList, { props: { items: [] } }).find('[data-testid="issues-none"]').exists()).toBe(true)
  })

  it('emits focus for an element issue and offers no control for a graph issue', async () => {  // clause: ISSUE_LIST-2
    const w = mount(IssueList, { props: { items } })
    const rows = w.findAll('[data-testid="issue"]')
    await rows[0].find('button').trigger('click')
    expect(w.emitted('focus')).toEqual([['e1']])
    expect(rows[1].find('button').exists()).toBe(false)
  })

  // --- chaos: contract corners the happy paths above leave open ----------

  it('supplied order is kept even when severities interleave, messages verbatim', () => {  // clause: ISSUE_LIST-1
    const interleaved = [
      { key: 'w0', severity: 'warning' as const, message: 'first warning', targetLabel: 'graph', focusKey: null },
      { key: 'e0', severity: 'error' as const, message: 'the error', targetLabel: 'n', focusKey: 'n0' },
      { key: 'w1', severity: 'warning' as const, message: 'second warning', targetLabel: 'graph', focusKey: null },
    ]
    const w = mount(IssueList, { props: { items: interleaved } })
    const rows = w.findAll('[data-testid="issue"]')
    expect(rows.map((r) => r.classes())).toEqual([
      expect.arrayContaining(['cmp-issue-warning']),
      expect.arrayContaining(['cmp-issue-error']),
      expect.arrayContaining(['cmp-issue-warning']),
    ])
    expect(rows[0].text()).toContain('first warning')
    expect(rows[1].text()).toContain('the error')
    expect(rows[2].text()).toContain('second warning')
  })

  it('each element issue emits its own focus key', async () => {  // clause: ISSUE_LIST-2
    const w = mount(IssueList, {
      props: {
        items: [
          { key: 'a', severity: 'error' as const, message: 'm0', targetLabel: 'e0', focusKey: 'f0' },
          { key: 'b', severity: 'warning' as const, message: 'm1', targetLabel: 'graph', focusKey: null },
          { key: 'c', severity: 'error' as const, message: 'm2', targetLabel: 'e2', focusKey: 'f2' },
        ],
      },
    })
    const rows = w.findAll('[data-testid="issue"]')
    await rows[0].find('button').trigger('click')
    await rows[2].find('button').trigger('click')
    expect(w.emitted('focus')).toEqual([['f0'], ['f2']])
    expect(rows[1].find('button').exists()).toBe(false)
  })

  it('an empty list has no rows and shows the empty state', () => {  // clause: ISSUE_LIST-1
    const w = mount(IssueList, { props: { items: [] } })
    expect(w.findAll('[data-testid="issue"]')).toHaveLength(0)
    expect(w.find('[data-testid="issues-none"]').exists()).toBe(true)
  })
})
