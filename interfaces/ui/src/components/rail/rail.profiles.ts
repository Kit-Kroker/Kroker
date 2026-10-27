import { defineProfiles } from '../../profile'
import Rail from './Rail.vue'

export default defineProfiles({
  component: 'rail',
  group: 'Shell',
  target: Rail,
  profiles: [
    {
      name: 'run-halted',
      summary: 'A halted run: failed state, fact rows, a budget bar and two call-to-actions.',
      props: {
        head: {
          title: 'feature-graph-demo',
          state: 'halted',
          stateKind: 'failed',
          rows: [
            { k: 'round', v: 'r3' },
            { k: 'nodes', v: '12' },
            { k: 'revise loops', v: '2/3' },
          ],
          budget: { spent: '$2.60', limit: 20, pct: 13, note: 'coding spend only' },
        },
        tabs: [
          { id: 'path', label: 'Path' },
          { id: 'events', label: 'Events' },
          { id: 'cost', label: 'Cost' },
        ],
        active: 'path',
        calls: [
          { label: 'Revise plan', kind: 'primary' },
          { label: 'Halt run', kind: 'danger' },
        ],
      },
      slots: {
        path: 'The path through the graph, sink to sink.',
        events: 'Every decision and transition this run took.',
        cost: 'Role, stage and revise-traversal spend.',
      },
    },
    {
      name: 'no-budget',
      summary: 'A run without a budget: the budget block reads off, no bar.',
      props: {
        head: {
          title: 'feature-dark-mode',
          state: 'running',
          stateKind: 'waiting',
          rows: [{ k: 'round', v: 'r1' }],
          budget: { spent: 'not measured', limit: null, pct: null, note: 'no budget set' },
        },
        tabs: [
          { id: 'path', label: 'Path' },
          { id: 'events', label: 'Events' },
        ],
        active: 'events',
        calls: [],
      },
      slots: {
        path: 'The path section.',
        events: 'The events section.',
      },
    },
  ],
})
