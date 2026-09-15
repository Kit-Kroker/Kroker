import { describe, it, expect } from 'vitest'
import { classify, fullySupported, getPath, resolveRef, setPath, type Schema } from './schema'

// Shapes pydantic v2 emits (verified against GraphNode.model_json_schema()).
const defs: Record<string, Schema> = {
  Policy: { enum: ['hard', 'soft', 'off'], type: 'string', title: 'Policy' },
  Cfg: {
    type: 'object',
    properties: {
      policy: { $ref: '#/$defs/Policy', default: 'hard' },
      threshold: { type: 'number', minimum: 0, maximum: 1, default: 0.8 },
      remind: { anyOf: [{ type: 'integer', exclusiveMinimum: 0 }, { type: 'null' }], default: null },
      kind: { enum: ['a', 'b'], type: 'string', default: 'a' },
      flag: { type: 'boolean' },
      args: { type: 'array', items: { type: 'string' } },
      harness: { anyOf: [{ $ref: '#/$defs/Policy' }, { type: 'null' }], default: null },
    },
  },
}

describe('classify', () => {
  it('resolves a $ref enum with its sibling default', () => {
    expect(classify({ $ref: '#/$defs/Policy', default: 'hard' }, defs)).toMatchObject({ kind: 'enum', values: ['hard', 'soft', 'off'], default: 'hard', nullable: false })
  })

  it('reads the nullable anyOf pattern, including a nullable $ref', () => {
    expect(classify({ anyOf: [{ type: 'integer', exclusiveMinimum: 0 }, { type: 'null' }] }, defs)).toMatchObject({ kind: 'integer', nullable: true, exclusiveMinimum: 0 })
    expect(classify({ anyOf: [{ $ref: '#/$defs/Policy' }, { type: 'null' }] }, defs)).toMatchObject({ kind: 'enum', nullable: true })
  })

  it('classifies a nested object and every supported leaf', () => {
    const f = classify({ anyOf: [{ $ref: '#/$defs/Cfg' }, { type: 'null' }] }, defs)
    expect(f.kind).toBe('object')
    expect(fullySupported(f)).toBe(true)
    if (f.kind === 'object') {
      expect(f.properties.map((p) => [p.name, p.field.kind])).toEqual([
        ['policy', 'enum'], ['threshold', 'number'], ['remind', 'integer'], ['kind', 'enum'],
        ['flag', 'boolean'], ['args', 'string-array'], ['harness', 'enum'],
      ])
    }
  })

  it('marks anything else unsupported', () => {
    expect(classify({ type: 'array', items: { type: 'integer' } }, defs).kind).toBe('unsupported')
    expect(classify({ anyOf: [{ type: 'string' }, { type: 'integer' }] }, defs).kind).toBe('unsupported')
    expect(classify({ $ref: '#/$defs/Missing' }, defs).kind).toBe('unsupported')
    expect(fullySupported(classify({ type: 'object', properties: { x: { oneOf: [] } } }, defs))).toBe(false)
  })

  it('does not loop on a recursive $ref', () => {
    const loop = { Node: { type: 'object', properties: { next: { $ref: '#/$defs/Node' } } } }
    expect(() => classify({ $ref: '#/$defs/Node' }, loop)).not.toThrow()
  })

  it('keeps sibling keys over the referenced schema', () => {
    expect(resolveRef({ $ref: '#/$defs/Policy', default: 'soft' }, defs)).toMatchObject({ enum: ['hard', 'soft', 'off'], default: 'soft' })
  })
})

describe('setPath', () => {
  it('writes only the touched path', () => {
    const base = { id: 'plan', gate: {} }
    expect(setPath(base, ['gate', 'policy'], 'soft', base)).toEqual({ id: 'plan', gate: { policy: 'soft' } })
    expect(setPath({ id: 'x' }, ['gate', 'policy'], 'soft', { id: 'x' })).toEqual({ id: 'x', gate: { policy: 'soft' } })
  })

  it('removes a cleared key and an object the user created, but keeps an authored empty object', () => {
    const created = setPath({ id: 'x' }, ['role', 'model'], 'm', { id: 'x' })
    expect(setPath(created, ['role', 'model'], undefined, { id: 'x' })).toEqual({ id: 'x' })
    const authored = { id: 'plan', gate: { policy: 'soft' } }
    expect(setPath(authored, ['gate', 'policy'], undefined, { id: 'plan', gate: {} })).toEqual({ id: 'plan', gate: {} })
  })

  it('never mutates its input', () => {
    const v = { id: 'x', gate: { policy: 'hard' } }
    setPath(v, ['gate', 'policy'], 'soft', v)
    expect(v.gate.policy).toBe('hard')
  })

  it('reads nested paths', () => {
    expect(getPath({ a: { b: [1, 2] } }, ['a', 'b', 1])).toBe(2)
    expect(getPath({ a: 1 }, ['a', 'b'])).toBeUndefined()
  })

  // --- chaos: contract corners the happy paths above leave open ----------

  it('prunes a whole chain of objects it created, but stops at an authored one', () => {  // SCHEMA_FORM-4
    const created = setPath({ id: 'x' }, ['a', 'b', 'c'], 1, { id: 'x' })
    expect(created).toEqual({ id: 'x', a: { b: { c: 1 } } })
    expect(setPath(created, ['a', 'b', 'c'], undefined, { id: 'x' })).toEqual({ id: 'x' })
    // an authored (base-supplied) object survives the same clear, even when emptied
    const base = { id: 'x', a: {} }
    const authored = setPath(base, ['a', 'b', 'c'], 1, base)
    expect(setPath(authored, ['a', 'b', 'c'], undefined, base)).toEqual({ id: 'x', a: {} })
  })

  it('falls back on hostile anyOf shapes, non-string enums, and deep unsupported', () => {  // SCHEMA_FORM-2
    // pydantic emits three-branch anyOf for Optional[Union[X, Y]]: not a native control
    expect(classify({ anyOf: [{ type: 'string' }, { type: 'null' }, { type: 'integer' }] }, defs).kind).toBe('unsupported')
    expect(classify({ enum: [1, 2] }, defs).kind).toBe('unsupported')
    const deep = { type: 'object', properties: { ok: { type: 'string' }, nested: { type: 'object', properties: { bad: { oneOf: [] } } } } }
    expect(fullySupported(classify(deep, defs))).toBe(false)
  })

  it('resolves a chain of $refs through $defs', () => {  // SCHEMA_FORM-3
    const chained = { A: { $ref: '#/$defs/B' }, B: { $ref: '#/$defs/C' }, C: { enum: ['x'], type: 'string' } }
    expect(classify({ $ref: '#/$defs/A' }, chained)).toMatchObject({ kind: 'enum', values: ['x'] })
  })
})
