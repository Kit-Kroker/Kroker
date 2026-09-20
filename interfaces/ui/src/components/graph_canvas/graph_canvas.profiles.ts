import { defineProfiles } from '../../profile'
import GraphCanvas from './GraphCanvas.vue'
import type { CanvasEdge, CanvasNode, CanvasPort, CanvasStatus } from './types'

const port = (name: string, side: 'in' | 'out', kind: 'signal' | 'data' = 'data', optional = false): CanvasPort =>
  ({ name, side, kind, label: name, optional })

const node = (key: string, x: number, ports: CanvasPort[], extra: Partial<CanvasNode> = {}): CanvasNode =>
  ({ key, title: key, ports, issueCount: 0, position: { x, y: 0 }, ...extra })

const edge = (from: string, fromPort: string, to: string, toPort: string, extra: Partial<CanvasEdge> = {}): CanvasEdge =>
  ({ key: `${from}.${fromPort}>${to}.${toPort}`, from: { node: from, port: fromPort }, to: { node: to, port: toPort }, backward: false, issueCount: 0, ...extra })

const pipeline = (status?: Record<string, CanvasStatus>): CanvasNode[] => [
  node('intake', 0, [port('ok', 'out', 'signal')], { subtitle: 'intake', status: status?.intake }),
  node('architect', 260, [port('requirements', 'in'), port('guidance', 'in', 'data', true), port('spec', 'out')], { subtitle: 'architect', status: status?.architect }),
  node('architecture', 520, [port('artifact', 'in'), port('approve', 'out'), port('revise', 'out'), port('reject', 'out', 'signal')], { subtitle: 'gate.architecture', status: status?.architecture }),
  node('planner', 780, [port('spec', 'in'), port('plan', 'out')], { subtitle: 'plan', status: status?.planner }),
]

const wires = (used?: number): CanvasEdge[] => [
  edge('intake', 'ok', 'architect', 'requirements'),
  edge('architect', 'spec', 'architecture', 'artifact'),
  edge('architecture', 'approve', 'planner', 'spec'),
  edge('architecture', 'revise', 'architect', 'guidance', { backward: true, counter: used === undefined ? undefined : { used, max: 3 } }),
]

export default defineProfiles({
  component: 'graph_canvas',
  group: 'Graph',
  target: GraphCanvas,
  profiles: [
    { name: 'edit-empty', summary: 'An empty draft: no nodes, no edges.', props: { nodes: [], edges: [], editable: true } },
    { name: 'edit-pre-code', summary: 'A loaded draft in edit mode, loop edge curved.', props: { nodes: pipeline(), edges: wires(), editable: true } },
    {
      name: 'edit-with-issues',
      summary: 'Validation issues decorate a node and an edge.',
      props: {
        nodes: pipeline().map((n) => (n.key === 'planner' ? { ...n, issueCount: 2 } : n)),
        edges: wires().map((e, i) => (i === 0 ? { ...e, issueCount: 1 } : e)),
        editable: true,
      },
    },
    {
      name: 'edit-duplicate-ids',
      summary: 'Two nodes share a domain id; the adapter gave them distinct keys.',
      props: {
        nodes: [node('intake', 0, [port('ok', 'out', 'signal')], { issueCount: 1 }), node('intake~2', 260, [port('ok', 'out', 'signal')], { title: 'intake', issueCount: 1 })],
        edges: [],
        editable: true,
      },
    },
    {
      name: 'run-mid-flight',
      summary: 'Run mode: status rings and metrics, nothing editable.',
      props: {
        nodes: pipeline({ intake: 'done', architect: 'running', architecture: 'idle', planner: 'idle' })
          .map((n) => (n.key === 'architect' ? { ...n, metrics: { cost: '$1.87', elapsed: '6m 02s', round: 'r1' } } : n)),
        edges: wires(0),
      },
    },
    {
      name: 'run-looped',
      summary: 'A revise loop taken twice: the counter reads 2/3 on a curved edge.',
      props: { nodes: pipeline({ intake: 'done', architect: 'running', architecture: 'done', planner: 'idle' }), edges: wires(2) },
    },
    {
      name: 'run-gate-pending',
      summary: 'A gate node held for a human decision.',
      props: { nodes: pipeline({ intake: 'done', architect: 'done', architecture: 'blocked', planner: 'idle' }), edges: wires(1) },
    },
    {
      name: 'run-skipped-leg',
      summary: 'A graph that routes around the architecture leg: those nodes render skipped.',
      props: { nodes: pipeline({ intake: 'done', architect: 'skipped', architecture: 'skipped', planner: 'running' }), edges: wires(0) },
    },
    {
      name: 'run-interrupted',
      summary: 'A closed execution cancels the node it held mid-flight.',
      props: { nodes: pipeline({ intake: 'done', architect: 'done', architecture: 'cancelled', planner: 'idle' }), edges: wires(1) },
    },
  ],
})
