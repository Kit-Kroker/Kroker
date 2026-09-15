// The edit-mode state machine (E-76 spec §8). Canvas operations mutate the
// working copy locally and never round-trip (D11); only text and inspector
// APPLY go through the server parse. Every async response carries the epoch
// it was dispatched at and is discarded if the working copy moved since.
import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import { api } from '../api/client'
import type { EdgeWire, GraphWire, NodeWire, ShapeError, ValidationWire } from '../api/graph-types'
import { useCatalogStore } from './catalog'
import {
  addNode as addNodeOp, connect as connectOp, edgeEditCandidate, moveNode, nodeEditCandidate, removeElement,
  withoutEmptyLabel, type EditResult,
} from './graphEdits'
import { edgeKeys, locWithin, nodeKeys } from '../adapters/graph'

export type EditorState = 'empty' | 'text_broken' | 'graph_loaded'
export interface FieldError { path: string; msg: string }

const VALIDATE_DEBOUNCE_MS = 400

export const useGraphEditorStore = defineStore('graphEditor', () => {
  const catalog = useCatalogStore()

  const state = ref<EditorState>('empty')
  const working = shallowRef<GraphWire | null>(null)
  const sha = ref<string | null>(null)          // sha of the working copy, when known
  const savedSha = ref<string | null>(null)
  const epoch = ref(0)
  const applying = ref(false)
  const selection = ref<string | null>(null)
  const notice = ref<string | null>(null)

  const yamlText = ref('')
  const yamlDirty = ref(false)
  const yamlErrors = ref<ShapeError[]>([])
  const validation = shallowRef<ValidationWire | null>(null)
  const inspectorErrors = ref<FieldError[]>([])
  const tidyRequest = ref(0)

  let validateTimer: ReturnType<typeof setTimeout> | null = null

  const canvasLocked = computed(() => applying.value || state.value !== 'graph_loaded')
  const errorCount = computed(() => validation.value?.issues.filter((i) => i.severity === 'error').length ?? 0)
  const runnable = computed(() => validation.value !== null && errorCount.value === 0)

  function commit(graph: GraphWire, opts: { sha?: string | null } = {}) {
    working.value = graph
    sha.value = opts.sha ?? null
    epoch.value += 1
    state.value = 'graph_loaded'
    scheduleValidate()
  }

  function scheduleValidate() {
    if (!catalog.can('validate') || !working.value) return
    if (validateTimer) clearTimeout(validateTimer)
    validateTimer = setTimeout(async () => {
      const at = epoch.value
      const graph = working.value
      if (!graph) return
      try {
        const result = await api.validateGraph(graph)
        if (at === epoch.value) validation.value = result   // stale results are discarded
      } catch (e) {
        if (at === epoch.value) notice.value = `validation failed: ${String(e)}`
      }
    }, VALIDATE_DEBOUNCE_MS)
  }

  function applyEdit(result: EditResult) {
    if (!result.ok || !working.value) return
    if (result.graph !== working.value) commit(result.graph)
    if (result.select !== undefined) selection.value = result.select
    if (result.notice) notice.value = result.notice
  }

  // --- loading -------------------------------------------------------------------

  const tooLarge = (body: unknown) =>
    catalog.catalog !== null && new TextEncoder().encode(JSON.stringify(body)).length > catalog.catalog.max_graph_bytes

  async function applyText() {
    if (applying.value) return
    const body = { yaml: yamlText.value }
    if (tooLarge(body)) {
      yamlErrors.value = [{ loc: [], msg: `graph text exceeds ${catalog.catalog?.max_graph_bytes} bytes`, line: null, column: null }]
      return
    }
    applying.value = true
    const at = epoch.value
    try {
      const result = await api.parseGraph(body)
      if (at !== epoch.value) return
      if (result.ok) {
        yamlErrors.value = []
        yamlDirty.value = false
        validation.value = null
        commit(result.graph, { sha: result.sha })
      } else {
        // U5: the canvas stays disabled until the text parses, even when a
        // graph was loaded before; the last good working copy is kept, and a
        // successful apply replaces it.
        yamlErrors.value = result.shape_errors
        state.value = 'text_broken'
      }
    } finally {
      applying.value = false
    }
  }

  function loadText(text: string) {
    yamlText.value = text
    yamlDirty.value = true
    return applyText()
  }

  function setYamlText(text: string) {
    yamlText.value = text
    yamlDirty.value = true
  }

  async function openYaml() {
    if (!working.value || yamlDirty.value) return
    const at = epoch.value
    try {
      const result = await api.serializeGraph(working.value)
      if (at !== epoch.value) return
      if (result.ok) {
        yamlText.value = result.yaml
        yamlErrors.value = []
      } else {
        yamlErrors.value = result.shape_errors
      }
    } catch (e) {
      if (at === epoch.value) notice.value = `serialize failed: ${String(e)}`
    }
  }

  function loadGraph(graph: GraphWire, graphSha: string | null) {
    validation.value = null
    selection.value = null
    yamlDirty.value = false
    commit(graph, { sha: graphSha })
    void openYaml()
  }

  function newGraph() {
    loadGraph({ schema_version: 1, nodes: [], edges: [] }, null)
  }

  async function loadSha(graphSha: string) {
    const result = await api.loadGraph(graphSha)
    if (result.ok) loadGraph(result.graph, result.sha)
    else notice.value = `no saved graph ${graphSha}`
  }

  async function openRunCopy(runId: string) {
    const result = await api.getRunGraph(runId)
    if (result.kind === 'graph') loadGraph(result.graph, null)   // a copy: no sha association
    else notice.value = 'this run predates graph execution'
  }

  // --- canvas operations (D11: local, never a round trip) ----------------------------

  function addNode(type: string, x: number, y: number) {
    const spec = catalog.typeOf(type)
    if (canvasLocked.value || !working.value || !spec) return
    applyEdit(addNodeOp(working.value, type, spec.default_id, x, y))
  }
  function connect(fromKey: string, fromPort: string, toKey: string, toPort: string) {
    if (canvasLocked.value || !working.value) return
    applyEdit(connectOp(working.value, fromKey, fromPort, toKey, toPort))
  }
  function move(key: string, x: number, y: number) {
    if (canvasLocked.value || !working.value) return
    applyEdit(moveNode(working.value, key, x, y))
  }
  function remove(kind: 'node' | 'edge', key: string) {
    if (canvasLocked.value || !working.value) return
    applyEdit(removeElement(working.value, kind, key))
  }
  function select(key: string | null) {
    selection.value = key
    inspectorErrors.value = []
  }
  function tidy() {
    if (!canvasLocked.value) tidyRequest.value += 1
  }

  // --- inspector apply (the only canvas-side round trip) ------------------------------

  const selectedNode = computed<{ index: number; node: NodeWire } | null>(() => {
    if (!working.value || !selection.value) return null
    const index = nodeKeys(working.value).indexOf(selection.value)
    return index < 0 ? null : { index, node: working.value.nodes[index] }
  })
  const selectedEdge = computed<{ index: number; edge: EdgeWire } | null>(() => {
    if (!working.value || !selection.value) return null
    const index = edgeKeys(working.value).indexOf(selection.value)
    return index < 0 ? null : { index, edge: working.value.edges[index] }
  })

  async function applyInspector(next: NodeWire | EdgeWire) {
    if (!working.value || !selection.value || applying.value) return
    const isNode = selectedNode.value !== null
    const index = isNode ? selectedNode.value!.index : selectedEdge.value?.index
    if (index === undefined) return
    const candidate = isNode
      ? nodeEditCandidate(working.value, selection.value, withoutEmptyLabel(next as NodeWire))
      : edgeEditCandidate(working.value, selection.value, withoutEmptyLabel(next as EdgeWire))
    if (!candidate.ok) {
      inspectorErrors.value = [{ path: candidate.field, msg: candidate.message }]
      return
    }
    applying.value = true
    const at = epoch.value
    try {
      const result = await api.parseGraph({ graph: candidate.graph })
      if (at !== epoch.value) {
        inspectorErrors.value = [{ path: '', msg: 'the graph changed — apply again' }]
        return
      }
      if (result.ok) {
        inspectorErrors.value = []
        commit(result.graph, { sha: result.sha })
        if (candidate.select !== undefined) selection.value = candidate.select
        if (candidate.notice) notice.value = candidate.notice
      } else {
        const collection = isNode ? 'nodes' : 'edges'
        const mine = result.shape_errors
          .map((err) => ({ path: locWithin(err.loc, collection, index), msg: err.msg }))
          .filter((err): err is FieldError => err.path !== null)
        const elsewhere = result.shape_errors.length - mine.length
        inspectorErrors.value = elsewhere > 0 ? [...mine, { path: '', msg: `${elsewhere} shape error(s) elsewhere in the graph` }] : mine
      }
    } finally {
      applying.value = false
    }
  }

  // --- save ------------------------------------------------------------------------

  async function save() {
    if (!working.value || !catalog.can('save') || applying.value) return
    const at = epoch.value
    const result = await api.saveGraph(working.value)
    if (at !== epoch.value) return
    if (result.ok) {
      savedSha.value = result.sha
      sha.value = result.sha
      if (result.validation) validation.value = result.validation
    } else {
      notice.value = `save refused: ${result.shape_errors.length} shape error(s)`
    }
  }

  return {
    state, working, sha, savedSha, epoch, applying, selection, notice, yamlText, yamlDirty, yamlErrors,
    validation, inspectorErrors, tidyRequest, canvasLocked, errorCount, runnable, selectedNode, selectedEdge,
    loadText, applyText, setYamlText, openYaml, loadGraph, newGraph, loadSha, openRunCopy,
    addNode, connect, move, remove, select, tidy, applyInspector, save,
  }
})
