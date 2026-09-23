// Chaos and edge cases for the inspector (E-76 Task 16), unit tier. The
// plan pins only the happy apply (CONSOLE-9, browser); this file pins the
// error-mapping and dirty-lifecycle corners against the real stores.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import GraphInspector from './GraphInspector.vue'
import catalogJson from '../../api/__fixtures__/graph/catalog.json'
import preCode from '../../api/__fixtures__/graph/scenarios/pre_code.json'
import soft from '../../api/__fixtures__/graph/objects/pre_code_architecture_soft.json'
import type { CatalogWire, GraphWire, ParseWire } from '../../api/graph-types'

const api = vi.hoisted(() => ({ parseGraph: vi.fn() }))
vi.mock('../../api/client', () => ({ api }))

import { useCatalogStore } from '../../shared/catalog.store'
import { useGraphEditorStore } from '../../stores/graphEditor'

const catalog = catalogJson as unknown as CatalogWire
const PRE = (preCode.parse as { ok: true; graph: GraphWire }).graph

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  useCatalogStore().catalog = catalog
})

// The recorded graph's nodes are alphabetically sorted: architect is nodes[0].
function withSelection(key: 'architect' | 'plan') {
  const editor = useGraphEditorStore()
  editor.working = PRE
  editor.selection = key
  return editor
}

describe('GraphInspector', () => {
  it('shows the hint and no form when nothing is selected', () => {
    const w = mount(GraphInspector)
    expect(w.text()).toContain('select a node or an edge')
    expect(w.find('[data-testid="schema-field"]').exists()).toBe(false)
  })

  it('apply stays disabled until the draft is edited, over the served schema', async () => {
    withSelection('architect')
    const w = mount(GraphInspector)
    expect(w.find('[data-testid="inspector-apply"]').attributes('disabled')).toBeDefined()
    await w.find('[data-path="id"] textarea').setValue('designer')
    expect(w.find('[data-testid="inspector-apply"]').attributes('disabled')).toBeUndefined()
  })

  it('a failed apply keeps the draft dirty, maps the error onto its field, and commits nothing', async () => {
    const editor = withSelection('architect')
    const before = editor.working
    api.parseGraph.mockResolvedValueOnce({
      ok: false,
      shape_errors: [{ loc: ['nodes', 0, 'gate', 'policy'], msg: 'bad enum', line: null, column: null }],
    } as ParseWire)
    const w = mount(GraphInspector)
    await w.find('[data-path="id"] textarea').setValue('designer')
    await w.find('[data-testid="inspector-apply"]').trigger('click')
    await flushPromises()  // the apply chain resolves over several microtasks
    expect(w.find('[data-path="gate.policy"] [data-testid="field-error"]').text()).toContain('bad enum')
    expect(w.find('[data-testid="inspector-apply"]').attributes('disabled')).toBeUndefined()  // still dirty
    expect(editor.working).toBe(before)  // no commit on a failed apply
  })

  it('a successful apply clears dirty, commits, and re-disables the button', async () => {
    const editor = withSelection('architect')
    api.parseGraph.mockResolvedValueOnce(soft.parse as ParseWire)
    const w = mount(GraphInspector)
    await w.find('[data-path="id"] textarea').setValue('designer')
    await w.find('[data-testid="inspector-apply"]').trigger('click')
    expect(api.parseGraph).toHaveBeenLastCalledWith({ graph: expect.any(Object) })
    expect(editor.sha).toBe((soft.parse as { sha: string }).sha)
    expect(w.find('[data-testid="inspector-apply"]').attributes('disabled')).toBeDefined()
  })

  it('the node type is read-only; switching selection resets the draft and the errors', async () => {
    const editor = withSelection('architect')
    const w = mount(GraphInspector)
    expect(w.find('[data-path="type"] textarea').attributes('readonly')).toBeDefined()
    await w.find('[data-path="id"] textarea').setValue('designer')  // dirty
    editor.selection = 'plan'
    await flushPromises()  // let the draft reset watch flush before editing again
    await w.find('[data-path="id"] textarea').setValue('plan_x')  // edit the NEW draft
    expect(api.parseGraph).not.toHaveBeenCalled()  // still unapplied
    api.parseGraph.mockResolvedValueOnce(soft.parse as ParseWire)
    await w.find('[data-testid="inspector-apply"]').trigger('click')
    await flushPromises()
    const sent = (api.parseGraph.mock.calls.at(-1)![0] as { graph: GraphWire }).graph
    expect(sent.nodes.find((n) => n.id === 'plan_x')).toMatchObject({ id: 'plan_x', type: 'gate.plan' })
  })
})
