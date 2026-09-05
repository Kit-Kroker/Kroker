import { defineProfiles } from '../../profile'
import StatusPip from './StatusPip.vue'

export default defineProfiles({
  component: 'status_pip',
  group: 'Fleet',
  target: StatusPip,
  profiles: [
    { name: 'running', summary: 'Active execution: pulsing blue pip.', props: { kind: 'running', pulsing: true } },
    { name: 'blocked', summary: 'Held at a gate: pulsing gold pip.', props: { kind: 'blocked', pulsing: true } },
    { name: 'failed', summary: 'Failed terminal state: static red pip.', props: { kind: 'failed', pulsing: false } },
    { name: 'done', summary: 'Successful terminal state: static green pip.', props: { kind: 'done', pulsing: false } },
    { name: 'all-kinds', summary: 'All seven status kinds side by side.', props: { kind: 'running' } },
  ],
})
