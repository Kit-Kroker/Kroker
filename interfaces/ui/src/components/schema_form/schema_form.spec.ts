import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SchemaForm from './SchemaForm.vue'
import profiles from './schema_form.profiles'

const byName = (name: string) => profiles.profiles.find((p) => p.name === name)!.props as Record<string, unknown>
const lastUpdate = (w: ReturnType<typeof mount>) => { const all = w.emitted('update')!; return all[all.length - 1] }
const kinds = (w: ReturnType<typeof mount>) =>
  Object.fromEntries(w.findAll('[data-testid="schema-field"]').map((f) => [f.attributes('data-path'), f.attributes('data-kind')]))

describe('SchemaForm', () => {
  it('renders one control per property, recursing into objects', () => {  // clause: SCHEMA_FORM-1
    const w = mount(SchemaForm, { props: byName('object-with-defs') as never })
    expect(Object.keys(kinds(w))).toEqual(['id', 'kind', 'settings.level', 'settings.ratio', 'settings.retries', 'settings.enabled', 'settings.tags', 'note'])
    expect(w.find('fieldset[data-path="settings"]').exists()).toBe(true)
  })

  it('renders every supported construct natively and the rest as a JSON snippet', async () => {  // clause: SCHEMA_FORM-2
    const w = mount(SchemaForm, { props: byName('object-with-defs') as never })
    expect(kinds(w)).toMatchObject({ id: 'string', 'settings.level': 'enum', 'settings.ratio': 'number', 'settings.retries': 'integer', 'settings.enabled': 'boolean', 'settings.tags': 'string-array', note: 'string' })
    const fb = mount(SchemaForm, { props: byName('unsupported-fallback') as never })
    const snippet = fb.find('[data-testid="schema-fallback"]')
    expect(snippet.exists()).toBe(true)
    await snippet.setValue('{not json')
    await snippet.trigger('blur')
    expect(fb.emitted('update')).toBeUndefined()
    await snippet.setValue('[[3]]')
    await snippet.trigger('blur')
    expect(fb.emitted('update')).toEqual([[{ matrix: [[3]] }]])
  })

  it('renders a nullable anyOf and a $ref enum natively', () => {  // clause: SCHEMA_FORM-3
    const w = mount(SchemaForm, { props: byName('object-with-defs') as never })
    expect(w.find('[data-path="settings.retries"]').attributes('data-kind')).toBe('integer')
    expect(w.find('[data-path="settings.level"] select').exists()).toBe(true)
  })

  it('writes only touched fields and prunes an object it created', async () => {  // clause: SCHEMA_FORM-4
    const w = mount(SchemaForm, { props: byName('absent-object') as never })
    expect(w.emitted('update')).toBeUndefined()
    await w.find('[data-path="settings.level"] select').setValue('high')
    expect(lastUpdate(w)).toEqual([{ id: 'beta', kind: 'demo', settings: { level: 'high' } }])
    await w.find('[data-path="settings.level"] select').setValue('')
    expect(lastUpdate(w)).toEqual([{ id: 'beta', kind: 'demo' }])
  })

  it('shows errors by path and at the top, and honours read-only paths', async () => {  // clause: SCHEMA_FORM-5
    const w = mount(SchemaForm, { props: byName('with-errors') as never })
    expect(w.find('[data-testid="form-error"]').text()).toContain('apply again')
    expect(w.find('[data-path="id"] [data-testid="field-error"]').text()).toContain('pattern')
    const ro = mount(SchemaForm, { props: byName('object-with-defs') as never })
    await ro.find('[data-path="kind"] textarea').setValue('changed')
    expect(ro.emitted('update')).toBeUndefined()
  })

  // --- chaos: contract corners the happy paths above leave open ----------

  it('a whole-form readonly silences every control kind, and stale errors stay inert', async () => {  // clause: SCHEMA_FORM-5
    const w = mount(SchemaForm, {
      props: { ...byName('object-with-defs'), readonly: true, errors: [{ path: 'zzz.gone', msg: 'stale' }] } as never,
    })
    await w.find('[data-path="id"] textarea').setValue('x')
    await w.find('[data-path="settings.level"] select').setValue('low')
    await w.find('[data-path="settings.ratio"] input').setValue('0.1')
    await w.find('[data-path="settings.enabled"] input').setValue(true)
    expect(w.emitted('update')).toBeUndefined()
    expect(w.findAll('[data-testid="field-error"]')).toHaveLength(0)  // an unknown path renders nowhere, no crash
  })

  it('a non-numeric number edit never writes NaN -- the key stays absent', async () => {  // clause: SCHEMA_FORM-4
    const w = mount(SchemaForm, { props: byName('absent-object') as never })
    await w.find('[data-path="settings.ratio"] input').setValue('not a number')
    expect(lastUpdate(w)).toEqual([{ id: 'beta', kind: 'demo' }])  // no settings:{ratio:NaN}, no crash
  })

  it('booleans always write true or false, never clear their key', async () => {  // clause: SCHEMA_FORM-4
    const w = mount(SchemaForm, { props: byName('absent-object') as never })
    await w.find('[data-path="settings.enabled"] input').setValue(true)
    expect(lastUpdate(w)).toEqual([{ id: 'beta', kind: 'demo', settings: { enabled: true } }])
    await w.find('[data-path="settings.enabled"] input').setValue(false)
    expect(lastUpdate(w)).toEqual([{ id: 'beta', kind: 'demo', settings: { enabled: false } }])  // false is a value, not a removal
  })

  it('string-array drops blank lines; clearing every line removes the key', async () => {  // clause: SCHEMA_FORM-4
    const w = mount(SchemaForm, { props: byName('absent-object') as never })
    const box = w.find('[data-path="settings.tags"] textarea')
    await box.setValue('alpha\n\nbeta')
    expect(lastUpdate(w)).toEqual([{ id: 'beta', kind: 'demo', settings: { tags: ['alpha', 'beta'] } }])
    await box.setValue('')
    expect(lastUpdate(w)).toEqual([{ id: 'beta', kind: 'demo' }])
  })

  it('blanking the JSON fallback removes the key; invalid JSON stays local', async () => {  // clause: SCHEMA_FORM-2
    const w = mount(SchemaForm, { props: byName('unsupported-fallback') as never })
    const snippet = w.find('[data-testid="schema-fallback"]')
    await snippet.setValue('')
    await snippet.trigger('blur')
    expect(lastUpdate(w)).toEqual([{}])
    await snippet.setValue('{nope')
    await snippet.trigger('blur')
    expect(lastUpdate(w)).toEqual([{}])  // still the last good value: nothing emitted
  })

  it('a new value prop resets the draft; edits build on the new value', async () => {  // clause: SCHEMA_FORM-4
    const w = mount(SchemaForm, { props: byName('object-with-defs') as never })
    await w.setProps({ value: { id: 'gamma', kind: 'demo', note: 'fresh' } as never })
    expect(w.emitted('update')).toBeUndefined()
    await w.find('[data-path="id"] textarea').setValue('delta')
    expect(lastUpdate(w)).toEqual([{ id: 'delta', kind: 'demo', note: 'fresh' }])
  })
})
