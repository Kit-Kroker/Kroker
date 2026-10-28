// v5 Design inspector (018 T062 RED, S15): edge max_traversals edit, node
// delete, and read-only PipelineConfig knobs. The schema-form node-field
// cases (E-76's corners) are DELETED with S15 — named in the RED report and
// in the commit body. The hint pin survives adapted.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import GraphInspector from './GraphInspector.vue'
import catalogJson from '../../api/__fixtures__/graph/catalog.json'
import preCode from '../../api/__fixtures__/graph/scenarios/pre_code.json'
import type { CatalogWire, GraphWire, ParseWire } from '../../api/graph-types'

const api = vi.hoisted(() => ({ parseGraph: vi.fn() }))
vi.mock('../../api/client', () => ({ api }))

import { useCatalogStore } from '../../shared/catalog.store'
import { useGraphEditorStore } from './graphEditor.store'

const CATALOG = catalogJson as unknown as CatalogWire
const PRE = (preCode.parse as { ok: true; graph: GraphWire; sha: string }).graph

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  useCatalogStore().catalog = CATALOG
})

const edgeKeyOf = (i: number) => {
  const e = PRE.edges[i]!
  return `${e.source}.${e.source_port}>${e.target}.${e.target_port}`
}

function withEdgeSelected(i = 0) {
  const editor = useGraphEditorStore()
  editor.working = PRE
  editor.selection = edgeKeyOf(i)
  return editor
}

function withGateNode(gate: Record<string, unknown>) {
  const editor = useGraphEditorStore()
  const working = JSON.parse(JSON.stringify(PRE)) as GraphWire
  const arch = working.nodes.find((n) => n.id === 'architecture')!
  ;(arch as Record<string, unknown>)['gate'] = gate
  editor.working = working
  editor.selection = 'architecture'
  return editor
}

describe('GraphInspector (v5, 018 T062 RED)', () => {
  it('shows the hint when nothing is selected', () => {
    useGraphEditorStore().working = PRE
    const w = mount(GraphInspector)
    expect(w.text()).toContain('select a node or an edge')
  })

  it('edits an edge max_traversals and round-trips through parse (S15)', async () => {
    const editor = withEdgeSelected(0)
    const edited = JSON.parse(JSON.stringify(PRE)) as GraphWire
    edited.edges[0]!.max_traversals = 4
    api.parseGraph.mockResolvedValueOnce({ ok: true, graph: edited, sha: 'sha-mt' } as ParseWire)
    const w = mount(GraphInspector)
    const input = w.find('[data-testid="inspector-max-traversals"]')
    expect(input.exists()).toBe(true)
    expect((input.element as HTMLInputElement).value).toBe('')  // unset on the PRE edge
    await input.setValue('4')
    await w.find('[data-testid="inspector-apply"]').trigger('click')
    await flushPromises()
    expect(api.parseGraph).toHaveBeenLastCalledWith({ graph: edited })
    expect(editor.working!.edges[0]!.max_traversals).toBe(4)
  })

  it('deletes the selected node through the store (S15)', async () => {
    const editor = withGateNode({ policy: 'soft' })
    const w = mount(GraphInspector)
    const del = w.find('[data-testid="inspector-delete"]')
    expect(del.exists()).toBe(true)
    await del.trigger('click')
    expect(editor.working!.nodes.some((n) => n.id === 'architecture')).toBe(false)
  })

  it('renders the node PipelineConfig knobs read-only with the configured values (S9)', () => {
    withGateNode({ policy: 'soft', threshold: 0.9 })
    const w = mount(GraphInspector)
    const knobs = w.findAll('[data-testid="inspector-knob"]')
    expect(knobs.length).toBeGreaterThan(0)
    for (const knob of knobs) {
      const control = knob.find('input, select, textarea')
      if (control.exists()) {
        const el = control.element as HTMLInputElement
        expect(el.disabled || el.readOnly, knob.text()).toBe(true)
      }
    }
    const byK = new Map(knobs.map((k) => [k.attributes('data-k'), k.text()]))
    expect(byK.get('policy')).toContain('soft')
    expect(byK.get('threshold')).toContain('0.9')
  })
})
