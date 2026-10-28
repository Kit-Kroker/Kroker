import { defineProfiles } from '../../profile'
import Kanban from './Kanban.vue'

export default defineProfiles({
  component: 'kanban',
  group: 'Data',
  target: Kanban,
  profiles: [
    {
      name: 'run-board',
      summary: 'Three wire-status columns with cards and the full-board link.',
      props: {
        columns: [
          {
            id: 'in_progress',
            title: 'In progress',
            status: 'in_progress',
            count: 2,
            cards: [
              { id: 'task:T07#1', title: 'Fix the retry loop', tag: 'T07', tagKind: 'in_progress', meta: 'fix attempts: 3' },
              { id: 'task:T09#1', tag: 'T09', tagKind: 'in_progress', meta: 'fix attempts: 1' },
            ],
          },
          {
            id: 'blocked',
            title: 'Blocked',
            status: 'blocked',
            count: 1,
            cards: [{ id: 'task:T12#1', title: 'Rate limit', tag: 'T12', tagKind: 'blocked', meta: 'r2' }],
          },
          { id: 'done', title: 'Done', status: 'done', count: 0, cards: [] },
        ],
        link: { label: 'Open full Agent Board →', to: '/runs/feature-graph-demo/board' },
      },
    },
    {
      name: 'sparse',
      summary: 'A quarantined card beside a failed one; no link without one given.',
      props: {
        columns: [
          {
            id: 'quarantined',
            title: 'Quarantined',
            status: 'quarantined',
            count: 1,
            cards: [{ id: 'task:T15#1', title: 'Tests fail on retry', tag: 'T15', tagKind: 'quarantined', meta: 'r1' }],
          },
          {
            id: 'failed',
            title: 'Failed',
            status: 'failed',
            count: 1,
            cards: [{ id: 'task:T16#1', tag: 'T16', tagKind: 'failed', meta: 'fix attempts: 2' }],
          },
        ],
      },
    },
  ],
})
