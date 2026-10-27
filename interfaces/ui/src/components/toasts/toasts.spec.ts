import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Toasts from './Toasts.vue'
import type { ToastItem } from './Toasts.vue'

describe('Toasts', () => {
  it('renders every supplied toast in order', () => {  // clause: TOASTS-1
    const toasts = [
      { id: '1', msg: 'First toast' },
      { id: '2', msg: 'Second toast' },
    ]
    const w = mount(Toasts, { props: { toasts } })
    const items = w.findAll('[data-testid="toast"]')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toBe('First toast')
    expect(items[1].text()).toBe('Second toast')
  })

  it('renders nothing at all when toasts list is empty', () => {  // clause: TOASTS-1.1
    const w = mount(Toasts, { props: { toasts: [] } })
    expect(w.findAll('[data-testid="toast"]')).toHaveLength(0)
    expect(w.find('.cmp-toasts').exists()).toBe(false)
  })

  it('renders the stack bottom-centre', () => {  // clause: TOASTS-2
    const w = mount(Toasts, { props: { toasts: [{ id: '1', msg: 'One' }] } })
    expect(w.find('.cmp-toasts').classes()).toContain('cmp-toasts--bottom-centre')
  })

  it('takes its colour from kind, not a colour prop', () => {  // clause: TOASTS-3
    const failed = mount(Toasts, { props: { toasts: [{ id: '1', msg: 'Failed', kind: 'failed' }] } })
    expect(failed.find('[data-testid="toast"]').classes()).toContain('cmp-toast-failed')

    // The deprecated colour prop is gone in v5: kind wins, no inline border
    // colour (the cast proves a legacy caller's stray field is inert).
    const done = mount(Toasts, {
      props: {
        toasts: [{ id: '2', msg: 'Done', kind: 'done', color: 'red' } as ToastItem],
      },
    })
    const el = done.find('[data-testid="toast"]')
    expect(el.classes()).toContain('cmp-toast-done')
    expect((el.element as HTMLElement).style.borderLeftColor).toBe('')
  })
})

describe('Toasts (chaos, 018 T013 RED)', () => {
  it('maps each kind to its own cmp-toast-<kind> class and no other kind class', () => {  // clause: TOASTS-3
    const kinds = ['done', 'running', 'waiting', 'failed', 'idle'] as const
    const toasts = kinds.map((kind, i) => ({ id: String(i), msg: kind, kind }))
    const w = mount(Toasts, { props: { toasts } })
    const items = w.findAll('[data-testid="toast"]')
    expect(items).toHaveLength(5)
    items.forEach((el, i) => {
      expect(el.classes().filter((c) => c.startsWith('cmp-toast-'))).toEqual([`cmp-toast-${kinds[i]}`])
    })
  })

  it('a toast without a kind gets no cmp-toast-* class and never the string undefined', () => {  // clause: TOASTS-3
    const w = mount(Toasts, { props: { toasts: [{ id: '1', msg: 'Plain' }] } })
    const el = w.find('[data-testid="toast"]')
    expect(el.classes().filter((c) => c.startsWith('cmp-toast-'))).toEqual([])
    expect(el.classes()).not.toContain('undefined')
  })

  it('a legacy colour prop with no kind contributes no inline border colour', () => {  // clause: TOASTS-3
    const w = mount(Toasts, {
      props: { toasts: [{ id: '1', msg: 'Legacy', color: 'red' } as ToastItem] },
    })
    const el = w.find('[data-testid="toast"]')
    expect((el.element as HTMLElement).style.borderLeftColor).toBe('')
  })
})
