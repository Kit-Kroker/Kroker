import { defineProfiles } from '../../profile'
import DecisionCard from './DecisionCard.vue'

export default defineProfiles({
  component: 'decision_card',
  group: 'Forms',
  target: DecisionCard,
  profiles: [
    {
      name: 'gate',
      summary: 'An architecture gate card: three actions, consequences in view.',
      props: {
        kicker: 'architecture r1',
        schema: 'gate',
        title: 'Approve the architecture',
        where: 'feature-graph-demo · node architecture',
        fields: [
          { k: 'Round', v: 'r1' },
          { k: 'Cost', v: '$1.87', mono: true },
        ],
        actions: [
          { id: 'approve', label: 'Approve', title: 'grant this increment', variant: 'default' },
          { id: 'revise', label: 'Revise', title: 'send the plan back to the architect', variant: 'primary', needsText: true },
          { id: 'reject', label: 'Reject', title: 'end the round with a rejection', variant: 'danger' },
        ],
        foot: 'decided by policy (soft)',
      },
    },
    {
      name: 'clarify',
      summary: 'A clarify card with the answer area: the gated send.',
      props: {
        kicker: 'clarify r2',
        schema: 'clarify',
        title: 'Which SSO provider does the portal use today?',
        where: 'feature-add-sso · round 2',
        fields: [{ k: 'Suggestion', v: 'Auth0 (high confidence)' }],
        text: { label: 'Answer', hint: 'one line, plain text', value: '', required: true },
        actions: [
          { id: 'accept', label: 'Accept suggestion', title: 'send the suggested answer', variant: 'default' },
          { id: 'answer', label: 'Send answer', title: 'send the typed answer', variant: 'primary', needsText: true },
        ],
        foot: 'the run waits on this answer',
      },
    },
    {
      name: 'tool-approval',
      summary: 'A tool approval card: Approve and Deny only, timeout copy in the foot (V4).',
      props: {
        kicker: 'tool_approval',
        schema: 'gate',
        title: 'Allow the production shell step?',
        where: 'feature-graph-demo · node code',
        fields: [{ k: 'Command', v: 'pytest -q deploy/', mono: true }],
        actions: [
          { id: 'approve', label: 'Approve', title: 'run the step', variant: 'default' },
          { id: 'reject', label: 'Deny', title: 'skip the step', variant: 'danger' },
        ],
        foot: 'a timeout counts as not approved',
      },
    },
  ],
})
