import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CommandPalette from './CommandPalette.vue'

// 018 T016 (RED): the ⌘K palette. Stable hooks the implementation (T017)
// must carry: data-testid palette-backdrop / palette-input / palette-command,
// and aria-selected="true" on the highlighted command.

const COMMANDS = [
  { id: 'review-r1', label: 'Review r1 pending gate', hint: 'waiting' },
  { id: 'open-inbox', label: 'Open Inbox', hint: '2 pending' },
  { id: 'open-fleet', label: 'Open Fleet', hint: '' },
]

const mountPalette = (props: Record<string, unknown> = {}) =>
  mount(CommandPalette, { props: { open: true, commands: COMMANDS, ...props } })

const commandEls = (w: ReturnType<typeof mountPalette>) =>
  w.findAll('[data-testid="palette-command"]')

const selected = (w: ReturnType<typeof mountPalette>) =>
  commandEls(w).map((el) => el.attributes('aria-selected') === 'true')

describe('CommandPalette', () => {
  it('renders nothing at all when open is false', () => {  // clause: COMMAND_PALETTE-1
    const w = mountPalette({ open: false })
    expect(w.find('[data-testid="palette-backdrop"]').exists()).toBe(false)
    expect(commandEls(w)).toHaveLength(0)
    expect(w.text()).toBe('')
  })

  it('renders each command with its label and hint', () => {  // clause: COMMAND_PALETTE-2
    const w = mountPalette()
    const items = commandEls(w)
    expect(items).toHaveLength(3)
    expect(items[1].text()).toContain('Open Inbox')
    expect(items[1].text()).toContain('2 pending')
  })

  it('filters commands by label, case-insensitively', async () => {  // clause: COMMAND_PALETTE-3
    const w = mountPalette()
    await w.find('[data-testid="palette-input"]').setValue('INBOX')
    const items = commandEls(w)
    expect(items).toHaveLength(1)
    expect(items[0].text()).toContain('Open Inbox')
  })

  it('ArrowDown and ArrowUp move the highlight; Enter runs the highlighted command', async () => {  // clause: COMMAND_PALETTE-4
    const w = mountPalette()
    const input = w.find('[data-testid="palette-input"]')
    expect(selected(w)).toEqual([true, false, false])

    await input.trigger('keydown', { key: 'ArrowDown' })
    expect(selected(w)).toEqual([false, true, false])
    await input.trigger('keydown', { key: 'ArrowDown' })
    expect(selected(w)).toEqual([false, false, true])
    await input.trigger('keydown', { key: 'ArrowUp' })
    expect(selected(w)).toEqual([false, true, false])

    await input.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('run')).toEqual([['open-inbox']])
  })

  it('Escape and a backdrop click each emit close', async () => {  // clause: COMMAND_PALETTE-5
    const w = mountPalette()
    await w.find('[data-testid="palette-input"]').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('close')).toHaveLength(1)
    await w.find('[data-testid="palette-backdrop"]').trigger('click')
    expect(w.emitted('close')).toHaveLength(2)
  })
})

describe('CommandPalette (chaos, 018 T016 RED)', () => {
  it('a filter that matches nothing renders no command and Enter runs nothing', async () => {  // clause: COMMAND_PALETTE-3
    const w = mountPalette()
    const input = w.find('[data-testid="palette-input"]')
    await input.setValue('zzz-no-such-command')
    expect(commandEls(w)).toHaveLength(0)
    await input.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('run') ?? []).toEqual([])
  })

  it('ArrowUp at the first command and ArrowDown at the last both clamp, no wrap', async () => {  // clause: COMMAND_PALETTE-4
    const w = mountPalette()
    const input = w.find('[data-testid="palette-input"]')
    await input.trigger('keydown', { key: 'ArrowUp' })
    expect(selected(w)).toEqual([true, false, false])

    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'ArrowDown' })
    expect(selected(w)).toEqual([false, false, true])
    await input.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('run')).toEqual([['open-fleet']])
  })

  it('typing a new filter resets the highlight to the first visible command', async () => {  // clause: COMMAND_PALETTE-4
    const w = mountPalette()
    const input = w.find('[data-testid="palette-input"]')
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.setValue('open')
    // 'open' matches Open Inbox and Open Fleet; the highlight restarts at the first match.
    expect(selected(w)).toEqual([true, false])
    await input.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('run')).toEqual([['open-inbox']])
  })

  it('a command with an empty hint renders without the string undefined', () => {  // clause: COMMAND_PALETTE-2
    const w = mountPalette()
    const fleet = commandEls(w)[2]
    expect(fleet.text()).toContain('Open Fleet')
    expect(fleet.text()).not.toContain('undefined')
  })
})
