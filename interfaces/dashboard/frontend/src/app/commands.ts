import type { PaletteCommand } from '@kroker/ui'
import { designAvailable, navManifest } from './nav'

// 018 T018/T019 (S11): the app state the palette list is derived from.
// `pending` are the inbox items of the run in context; `graphs` are the
// shipped graph names (empty until the Design slice serves them, T063).
export interface CommandsState {
  run: { id: string; pending: { id: string; title: string }[] } | null
  inboxCount: number
  mode: 'observe' | 'design'
  graphs: string[]
}

// v5's command list in v5's order, filtered by what the app can serve:
// a command whose nav target is unavailable is omitted, and the Design
// trio (switch, design-*, validate) waits for designAvailable (T063).
export function commandsOf(state: CommandsState): PaletteCommand[] {
  const nav = (id: string) => navManifest.find((n) => n.id === id)?.available === true
  const cmds: PaletteCommand[] = []
  if (state.run) {
    for (const p of state.run.pending) {
      cmds.push({ id: `review-${p.id}`, label: `Review ${p.title}`, hint: 'waiting' })
    }
  }
  if (nav('inbox')) {
    cmds.push({ id: 'open-inbox', label: 'Open Inbox', hint: `${state.inboxCount} pending` })
  }
  if (nav('fleet')) cmds.push({ id: 'open-fleet', label: 'Open Fleet' })
  if (state.run && nav('run')) {
    cmds.push({ id: 'open-run-board', label: 'Open run board', hint: state.run.id })
  }
  if (designAvailable) {
    cmds.push({
      id: 'switch-mode',
      label: state.mode === 'observe' ? 'Switch to Design' : 'Switch to Observe',
    })
    for (const g of state.graphs) cmds.push({ id: `design-${g}`, label: `Design ${g}` })
    cmds.push({ id: 'validate-graph', label: 'Validate graph' })
  }
  if (nav('graphs')) cmds.push({ id: 'fit-graph', label: 'Fit graph to view' })
  if (nav('compare')) cmds.push({ id: 'compare', label: 'Compare arms × graphs' })
  if (nav('interfaces')) cmds.push({ id: 'interfaces', label: 'Harness interfaces' })
  return cmds
}
