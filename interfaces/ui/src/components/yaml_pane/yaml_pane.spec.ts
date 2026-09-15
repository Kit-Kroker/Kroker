import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import YamlPane from './YamlPane.vue'

describe('YamlPane', () => {
  it('emits update:text on edit and apply only when dirty and not busy', async () => {  // clause: YAML_PANE-1
    const w = mount(YamlPane, { props: { text: 'a' } })
    await w.find('[data-testid="yaml-text"]').setValue('b')
    expect(w.emitted('update:text')).toEqual([['b']])
    await w.find('[data-testid="yaml-apply"]').trigger('click')
    expect(w.emitted('apply')).toBeUndefined()
    await w.setProps({ dirty: true })
    await w.find('[data-testid="yaml-apply"]').trigger('click')
    expect(w.emitted('apply')).toHaveLength(1)
    await w.setProps({ busy: true })
    await w.find('[data-testid="yaml-apply"]').trigger('click')
    expect(w.emitted('apply')).toHaveLength(1)
  })

  it('renders error rows with line, path and message', () => {  // clause: YAML_PANE-2
    const w = mount(YamlPane, {
      props: {
        text: 'x',
        errors: [
          { path: '', message: 'bad yaml', line: 3, column: 1 },
          { path: 'nodes[0].id', message: 'bad id', line: null, column: null },
        ],
      },
    })
    const rows = w.findAll('[data-testid="yaml-error"]')
    expect(rows.map((r) => r.text())).toEqual(['line 3:1bad yaml', 'nodes[0].idbad id'])
    expect(mount(YamlPane, { props: { text: 'x' } }).find('[data-testid="yaml-errors"]').exists()).toBe(false)
  })

  it('states that the text is canonical', () => {  // clause: YAML_PANE-3
    expect(mount(YamlPane, { props: { text: '' } }).text()).toContain('comments, key order and default values are not kept')
  })

  it('counts UTF-8 bytes against the cap', async () => {  // clause: YAML_PANE-4
    const w = mount(YamlPane, { props: { text: 'éé', dirty: true, maxBytes: 3 } })
    expect(w.find('[data-testid="yaml-too-large"]').text()).toContain('4 bytes exceeds 3')
    await w.find('[data-testid="yaml-apply"]').trigger('click')
    expect(w.emitted('apply')).toBeUndefined()
    await w.setProps({ maxBytes: 4 })
    expect(w.find('[data-testid="yaml-too-large"]').exists()).toBe(false)
  })

  // --- chaos: contract corners the happy paths above leave open ----------

  it('every edit emits update:text with the exact latest text', async () => {  // clause: YAML_PANE-1
    const w = mount(YamlPane, { props: { text: 'a' } })
    await w.find('[data-testid="yaml-text"]').setValue('b')
    await w.find('[data-testid="yaml-text"]').setValue('cde')
    expect(w.emitted('update:text')).toEqual([['b'], ['cde']])
  })

  it('apply needs the whole conjunction, and over-cap text stays editable', async () => {  // clause: YAML_PANE-1
    const w = mount(YamlPane, { props: { text: 'a longer yaml draft', maxBytes: 5 } })
    expect(w.find('[data-testid="yaml-too-large"]').exists()).toBe(true)  // shown before any dirty flag
    await w.find('[data-testid="yaml-apply"]').trigger('click')           // not dirty
    expect(w.emitted('apply')).toBeUndefined()
    await w.setProps({ dirty: true })
    await w.find('[data-testid="yaml-apply"]').trigger('click')           // dirty but over cap
    expect(w.emitted('apply')).toBeUndefined()
    await w.find('[data-testid="yaml-text"]').setValue('even longer now') // over cap: typing still lives
    expect(w.emitted('update:text')).toEqual([['even longer now']])
    await w.setProps({ busy: true })
    await w.find('[data-testid="yaml-apply"]').trigger('click')           // dirty + in cap? no: still over cap AND busy
    expect(w.emitted('apply')).toBeUndefined()
    await w.setProps({ busy: false, maxBytes: null })                     // default: no cap, no gate
    expect(w.find('[data-testid="yaml-too-large"]').exists()).toBe(false)
    await w.find('[data-testid="yaml-apply"]').trigger('click')
    expect(w.emitted('apply')).toHaveLength(1)
  })

  it('the cap counts UTF-8 bytes, not JS string length', async () => {  // clause: YAML_PANE-4
    // 'a🚀é' is 7 UTF-8 bytes (1+4+2) but .length is 4 -- a length-based cap passes this wrongly.
    const w = mount(YamlPane, { props: { text: 'a🚀é', dirty: true, maxBytes: 6 } })
    expect(w.find('[data-testid="yaml-too-large"]').text()).toContain('7 bytes exceeds 6')
    await w.find('[data-testid="yaml-apply"]').trigger('click')
    expect(w.emitted('apply')).toBeUndefined()
    await w.setProps({ maxBytes: 7 })
    expect(w.find('[data-testid="yaml-too-large"]').exists()).toBe(false)
    await w.find('[data-testid="yaml-apply"]').trigger('click')
    expect(w.emitted('apply')).toHaveLength(1)
  })

  it('error rows render line-without-column and follow prop changes', async () => {  // clause: YAML_PANE-2
    const w = mount(YamlPane, {
      props: { text: 'x', errors: [{ path: '', message: 'm', line: 5, column: null }] },
    })
    expect(w.find('[data-testid="yaml-error"]').text()).toBe('line 5m')
    await w.setProps({ errors: [] })
    expect(w.find('[data-testid="yaml-errors"]').exists()).toBe(false)
    await w.setProps({ errors: [{ path: 'nodes[0]', message: 'm2', line: null, column: null }] })
    expect(w.find('[data-testid="yaml-error"]').text()).toBe('nodes[0]m2')
  })
})
