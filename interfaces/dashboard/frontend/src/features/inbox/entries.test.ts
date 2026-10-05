// 010 T008 (RED): the entry frame of contracts/inbox-screen.md §3.2, written
// before InboxEntry.vue exists (that unresolved import is the RED cause).
// Field names per data-model §1.1; kind labels and the RouterLink target per
// data-model §2.6 and §3.2. Mount pattern: RunView.test.ts's RouterLink stub.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import InboxEntry from './InboxEntry.vue'
import type {
  ClarifyItem,
  GateItem,
  OverrideItem,
  EscalationItem,
} from '../../api/types'

const RouterLinkStub = { props: ['to'], template: '<a data-testid="stub-link"><slot /></a>' }

// Full literals, field names per data-model §1.1.
const gateItem = (): GateItem => ({
  id: 'architecture#1',
  runId: 'feature-add-sso',
  round: 2,
  age: '3h 15m',
  type: 'gate',
  gate: 'architecture',
  title: 'Architecture needs a decision',
  body: 'The architecture gate is waiting for review.',
})

const clarifyItem = (): ClarifyItem => ({
  id: 'q1',
  runId: 'feature-add-sso',
  round: 1,
  age: '2h 00m',
  type: 'clarify',
  title: 'Clarification needed',
  body: 'The proposer needs one more answer.',
  suggestion: 'Use OIDC.',
})

const overrideItem = (): OverrideItem => ({
  id: 'm1',
  runId: 'feature-billing-webhooks',
  round: 1,
  age: '45m',
  type: 'override',
  gate: 'merge',
  title: 'Merge override requested',
  body: 'A check failed; the proposer asks for an override.',
  verdict: '2 of 6 checks failed.',
  checks: [{ name: 'ci', kind: 'ABSOLUTE', ok: false, detail: 'tests red' }],
})

const escalationItem = (): EscalationItem => ({
  id: 'e1',
  runId: 'fix-rate-limit-retry',
  round: 3,
  age: '6h 30m',
  type: 'escalation',
  title: 'Task escalated',
  body: 'The fix attempts ran out.',
  analysis: 'The retry loop could not reproduce the failure locally.',
})

const mountInboxEntry = (
  item: ClarifyItem | GateItem | OverrideItem | EscalationItem,
  extra: { notice?: string; slot?: string } = {},
) =>
  mount(InboxEntry, {
    props: { item, ...(extra.notice !== undefined ? { notice: extra.notice } : {}) },
    slots: extra.slot ? { default: extra.slot } : {},
    global: { stubs: { RouterLink: RouterLinkStub } },
  })

describe('InboxEntry', () => {
  it('the root carries the entry test id and the run/key/type attributes', () => {
    const wrapper = mountInboxEntry(gateItem())
    const root = wrapper.get('[data-testid="inbox-entry"]')
    expect(root.attributes('data-run-id')).toBe('feature-add-sso')
    expect(root.attributes('data-key')).toBe('architecture#1')
    expect(root.attributes('data-type')).toBe('gate')
  })

  it('kind label, age, title and body render under their test ids', () => {
    const wrapper = mountInboxEntry(gateItem())
    expect(wrapper.get('[data-testid="inbox-entry-kind"]').text()).toContain('architecture')
    expect(wrapper.get('[data-testid="inbox-entry-age"]').text()).toBe('3h 15m')
    expect(wrapper.get('[data-testid="inbox-entry-title"]').text()).toBe(
      'Architecture needs a decision',
    )
    expect(wrapper.get('[data-testid="inbox-entry-body"]').text()).toBe(
      'The architecture gate is waiting for review.',
    )
  })

  it('the kind label is the fixed string of data-model 2.6 for each of the four types', () => {
    const cases: [ReturnType<typeof clarifyItem> | GateItem | OverrideItem | EscalationItem, string][] = [
      [clarifyItem(), 'question'],
      [gateItem(), 'gate · architecture'],
      [overrideItem(), 'merge override'],
      [escalationItem(), 'escalation'],
    ]
    for (const [item, label] of cases) {
      const wrapper = mountInboxEntry(item)
      expect(wrapper.get('[data-testid="inbox-entry-kind"]').text()).toBe(label)
    }
  })

  it('the run link shows the run id and links to the run route', () => {
    const wrapper = mountInboxEntry(gateItem())
    const link = wrapper.get('[data-testid="inbox-entry-run"]')
    expect(link.text()).toBe('feature-add-sso')
    const linkComponent = wrapper.findComponent(RouterLinkStub)
    expect(linkComponent.props('to')).toEqual({ name: 'run', params: { id: 'feature-add-sso' } })
  })

  it('an empty body renders no body block (EC7)', () => {
    const item = { ...gateItem(), body: '' }
    const wrapper = mountInboxEntry(item)
    expect(wrapper.find('[data-testid="inbox-entry-body"]').exists()).toBe(false)
  })

  it('the notice renders only when the notice prop is given', () => {
    const without = mountInboxEntry(gateItem())
    expect(without.find('[data-testid="inbox-notice"]').exists()).toBe(false)
    const withNotice = mountInboxEntry(gateItem(), { notice: 'already decided elsewhere' })
    expect(withNotice.get('[data-testid="inbox-notice"]').text()).toBe('already decided elsewhere')
  })

  it('the body block carries the inbox-longtext class (EC8)', () => {
    const wrapper = mountInboxEntry(gateItem())
    expect(wrapper.get('[data-testid="inbox-entry-body"]').classes()).toContain('inbox-longtext')
  })

  it('slot content renders after the notice', () => {
    const wrapper = mountInboxEntry(gateItem(), {
      notice: 'failed: boom',
      slot: '<span data-testid="slot-marker">entry actions</span>',
    })
    const notice = wrapper.get('[data-testid="inbox-notice"]').element
    const slot = wrapper.get('[data-testid="slot-marker"]').element
    expect(notice.compareDocumentPosition(slot) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
