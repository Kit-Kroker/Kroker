import { defineProfiles } from '../../profile'
import StatusPip from './StatusPip.vue'

export default defineProfiles({
  component: 'status_pip',
  group: 'Fleet', // FR-015: stays in Fleet (G9 -- no regrouping)
  target: StatusPip,
  profiles: [
    { name: 'running', summary: 'Active execution: pulsing blue pip.', props: { kind: 'running', pulsing: true } },
    { name: 'blocked', summary: 'Held for a human: pulsing violet pip.', props: { kind: 'blocked', pulsing: true } },
    { name: 'failed', summary: 'Failed terminal state: static red pip.', props: { kind: 'failed', pulsing: false } },
    { name: 'done', summary: 'Successful terminal state: static green pip.', props: { kind: 'done', pulsing: false } },
    { name: 'pending', summary: 'Not started: hollow idle ring.', props: { kind: 'pending' } },
    { name: 'quarantined', summary: 'Set aside by an operator: hollow red ring.', props: { kind: 'quarantined' } },
  ],
})
