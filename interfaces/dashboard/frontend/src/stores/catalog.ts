import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import { api } from '../api/client'
import type { Capability, CatalogWire, NodeTypeWire } from '../api/graph-types'

// The node-type catalog, canonical stages and capabilities, served by
// GET /graphs/catalog (E-76 spec §5.2, §7.3). Loaded once per session.
export const useCatalogStore = defineStore('catalog', () => {
  const catalog = shallowRef<CatalogWire | null>(null)
  const error = ref<string | null>(null)
  let inflight: Promise<void> | null = null

  function load(): Promise<void> {
    // Promise.resolve() first: a provider that throws synchronously still
    // lands in the error branch, never as an unhandled rejection at mount.
    inflight ??= Promise.resolve().then(() => api.getCatalog()).then(
      (c) => { catalog.value = c; error.value = null },
      (e: unknown) => { inflight = null; error.value = String(e) },
    )
    return inflight
  }

  const canonicalStages = computed<readonly string[]>(() => catalog.value?.canonical_stages ?? [])
  const nodeTypes = computed<readonly NodeTypeWire[]>(() => catalog.value?.node_types ?? [])
  const typeOf = (type: string): NodeTypeWire | undefined =>
    catalog.value?.node_types.find((t) => t.type === type)
  const can = (cap: Capability): boolean => catalog.value?.capabilities[cap] ?? false

  // The ONLY check TS runs while dragging (spec §8.2, GRAPH_CANVAS-6): a
  // membership test over Python's ports_compatible, served as data.
  function connectable(sourceType: string, sourcePort: string, targetType: string, targetPort: string): boolean {
    const targets = typeOf(sourceType)?.connectable[sourcePort] ?? []
    return targets.some((t) => t.type === targetType && t.port === targetPort)
  }

  return { catalog, error, load, canonicalStages, nodeTypes, typeOf, can, connectable }
})
