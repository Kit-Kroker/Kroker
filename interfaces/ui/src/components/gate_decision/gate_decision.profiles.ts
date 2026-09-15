import { defineProfiles } from '../../profile'
import GateDecision from './GateDecision.vue'

export default defineProfiles({
  component: 'gate_decision',
  group: 'Graph',
  target: GateDecision,
  profiles: [
    { name: 'idle', summary: 'A pending gate awaiting a decision.', props: { title: 'architecture · round 2' } },
    { name: 'busy', summary: 'A decision in flight: every control disabled.', props: { title: 'architecture · round 2', busy: true } },
    { name: 'revise-needs-comment', summary: 'Revise stays disabled until a comment is typed.', props: { title: 'plan · round 1' } },
  ],
})
