import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SchemaForm from '@kroker/ui/components/schema_form/SchemaForm.vue'
import { classify, fullySupported } from '@kroker/ui/components/schema_form/schema'
import catalogJson from '../../api/__fixtures__/graph/catalog.json'
import type { CatalogWire } from '../../api/graph-types'

// SCHEMA_FORM-3 against the backend's RECORDED schema: the dashboard is the
// tier allowed to import recordings (the ui package never names a Kroker
// model). Python mirrors this in tests/test_dashboard_graph_wire.py.
const catalog = catalogJson as unknown as CatalogWire

describe('schema_form over the recorded GraphNode / GraphEdge schemas', () => {
  it.each(['GraphNode', 'GraphEdge'] as const)('classifies every %s property as supported', (name) => {  // clause: SCHEMA_FORM-3
    const schema = catalog.schemas[name] as Record<string, unknown>
    const field = classify(schema, (schema.$defs ?? {}) as Record<string, Record<string, unknown>>)
    expect(fullySupported(field)).toBe(true)
  })

  it('renders no fallback for a node carrying a role and a gate', () => {  // clause: SCHEMA_FORM-3
    const w = mount(SchemaForm, {
      props: {
        schema: catalog.schemas.GraphNode,
        value: { id: 'architect', type: 'architect', role: { kind: 'proposer', model: 'm' }, gate: { policy: 'soft' } },
      },
    })
    expect(w.findAll('[data-testid="schema-field"]').length).toBeGreaterThan(15)
    expect(w.find('[data-testid="schema-fallback"]').exists()).toBe(false)
  })
})

// --- chaos: the edge schema gets the same no-fallback guarantee ------------

it('renders no fallback for an edge carrying a traversal cap', () => {  // clause: SCHEMA_FORM-3
  const w = mount(SchemaForm, {
    props: {
      schema: catalog.schemas.GraphEdge,
      value: { source: 'a', source_port: 'ok', target: 'b', target_port: 'in', max_traversals: 3 },
    },
  })
  expect(w.find('[data-testid="schema-fallback"]').exists()).toBe(false)
  expect(w.findAll('[data-testid="schema-field"]').length).toBeGreaterThan(3)
})
