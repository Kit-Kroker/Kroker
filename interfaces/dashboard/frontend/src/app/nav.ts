import type { NavItem } from '@kroker/ui/components/app_header/AppHeader.vue'

// 018 data-model §5 (R-1): the v5 route manifest. One array, primary items
// first (fleet, inbox, the run in context) then secondary. The shell
// rebuilds the run entry from live fleet state; the static entries are
// never mutated by consumers.
export const navManifest: NavItem[] = [
  { id: 'fleet', label: 'Fleet', to: '/', available: true },
  { id: 'inbox', label: 'Inbox', to: '/inbox', available: true },
  { id: 'run', label: 'Run', to: '/runs', available: true },
  { id: 'graphs', label: 'Graphs', to: '/graphs', available: true },
  // Slice 7 lights interfaces up; compare landed with slice 6 (T072).
  { id: 'compare', label: 'Compare', to: '/compare', available: true },
  { id: 'interfaces', label: 'Interfaces', to: '/interfaces', available: false },
]

// 018 T063: the Design route landed. Gates the header's Observe/Design
// switch and the design commands — never a nav item.
export const designAvailable = true
