import { defineProfiles } from '../../profile'
import SchemaForm from './SchemaForm.vue'

// A generic JSON Schema fixture in the shapes pydantic emits. Deliberately
// NOT a Kroker model: the recorded GraphNode schema is exercised in the
// dashboard tier (SCHEMA_FORM-3), which may import backend recordings.
const defs = {
  Level: { enum: ['low', 'medium', 'high'], title: 'Level', type: 'string' },
  Settings: {
    type: 'object',
    properties: {
      level: { $ref: '#/$defs/Level', default: 'low' },
      ratio: { type: 'number', minimum: 0, maximum: 1, default: 0.5, title: 'Ratio' },
      retries: { anyOf: [{ type: 'integer', exclusiveMinimum: 0 }, { type: 'null' }], default: null },
      enabled: { type: 'boolean', default: false },
      tags: { type: 'array', items: { type: 'string' } },
    },
  },
}

const schema = {
  $defs: defs,
  type: 'object',
  required: ['id'],
  properties: {
    id: { type: 'string', pattern: '^[a-z][a-z0-9_]*$' },
    kind: { type: 'string' },
    settings: { anyOf: [{ $ref: '#/$defs/Settings' }, { type: 'null' }], default: null },
    note: { anyOf: [{ type: 'string' }, { type: 'null' }], default: null },
  },
}

export default defineProfiles({
  component: 'schema_form',
  group: 'Graph',
  target: SchemaForm,
  profiles: [
    { name: 'object-with-defs', summary: 'A nested nullable $ref object with enum, bounds and arrays.', props: { schema, value: { id: 'alpha', kind: 'demo', settings: { level: 'high' } }, readonlyPaths: ['kind'] } },
    { name: 'absent-object', summary: 'A nullable object not yet set: placeholders show defaults, nothing is written.', props: { schema, value: { id: 'beta', kind: 'demo' } } },
    { name: 'with-errors', summary: 'Server shape errors beside their fields and at the top.', props: { schema, value: { id: 'Bad', kind: 'demo' }, errors: [{ path: 'id', msg: "String should match pattern '^[a-z][a-z0-9_]*$'" }, { path: '', msg: 'the graph changed — apply again' }] } },
    { name: 'unsupported-fallback', summary: 'A construct outside the subset renders a JSON snippet.', props: { schema: { type: 'object', properties: { matrix: { type: 'array', items: { type: 'array', items: { type: 'integer' } } } } }, value: { matrix: [[1, 2]] } } },
  ],
})
