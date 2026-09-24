import { defineProfiles } from '../../profile'
import Timeline from './Timeline.vue'

export default defineProfiles({
  component: 'timeline',
  group: 'Data',
  target: Timeline,
  profiles: [
    {
      name: 'task-history',
      summary: 'A task that failed, was reset and finished.',
      props: {
        items: [
          { id: 408, from: 'in_progress', to: 'done', at: '09-23 08:05', actor: 'workflow', detail: 'qa + review attached' },
          { id: 407, from: 'failed', to: 'in_progress', at: '09-23 07:48', actor: 'workflow', detail: 'reset replay from event 1152' },
          { id: 406, from: 'in_progress', to: 'failed', at: '09-23 06:10', actor: 'workflow', detail: 'child wall-clock timeout (3000s)' },
          { id: 405, from: 'pending', to: 'in_progress', at: '09-23 05:05', actor: 'workflow' },
        ],
      },
    },
    { name: 'created', summary: 'A single creation entry with no from.', props: { items: [{ id: 1, to: 'pending', at: '09-22 21:18', actor: 'workflow', detail: 'Created from plan v3' }] } },
    { name: 'empty', summary: 'No history: the empty slot renders.', props: { items: [] }, slots: { empty: 'No transitions yet.' } },
  ],
})
