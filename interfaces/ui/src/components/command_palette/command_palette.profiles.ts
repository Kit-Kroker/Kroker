import { defineProfiles } from '../../profile'
import CommandPalette from './CommandPalette.vue'

export default defineProfiles({
  component: 'command_palette',
  group: 'Shell',
  target: CommandPalette,
  profiles: [
    {
      name: 'open',
      summary: 'The palette open over the console with v5 commands.',
      props: {
        open: true,
        commands: [
          { id: 'review-r1', label: 'Review r1 — pending gate', hint: 'waiting' },
          { id: 'open-inbox', label: 'Open Inbox', hint: '2 pending' },
          { id: 'open-fleet', label: 'Open Fleet', hint: '' },
          { id: 'switch-design', label: 'Switch to Design', hint: '' },
        ],
      },
    },
    {
      name: 'closed',
      summary: 'The palette closed renders nothing at all.',
      props: { open: false, commands: [] },
    },
  ],
})
