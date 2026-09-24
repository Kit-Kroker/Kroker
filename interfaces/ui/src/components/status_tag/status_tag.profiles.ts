import { defineProfiles } from '../../profile'
import StatusTag from './StatusTag.vue'

export default defineProfiles({
  component: 'status_tag',
  group: 'Status',
  target: StatusTag,
  profiles: [
    { name: 'running', summary: 'Running with a caller label.', props: { kind: 'running', label: 'Running · code', pulsing: true } },
    { name: 'in-progress', summary: 'Board task kind with the default wording.', props: { kind: 'in_progress' } },
    { name: 'done', summary: 'Done on its tint.', props: { kind: 'done' } },
    { name: 'failed', summary: 'Failed on its tint.', props: { kind: 'failed' } },
    { name: 'pending', summary: 'Pending: hollow pip on the idle tint.', props: { kind: 'pending' } },
    { name: 'mono-waiting', summary: 'Mono uppercase, as on a canvas node.', props: { kind: 'waiting', label: 'Waiting · gate', mono: true } },
  ],
})
