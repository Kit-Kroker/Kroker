import { defineProfiles } from '../../profile'
import NodePalette from './NodePalette.vue'

export default defineProfiles({
  component: 'node_palette',
  group: 'Graph',
  target: NodePalette,
  profiles: [
    {
      name: 'seed',
      summary: 'The seed catalog: six stages, three gates.',
      props: {
        items: [
          { type: 'architect', kind: 'stage', stage: 'architecture' },
          { type: 'clarify', kind: 'stage', stage: 'clarify' },
          { type: 'context', kind: 'stage', stage: 'context' },
          { type: 'gate.architecture', kind: 'gate', stage: 'architecture' },
          { type: 'gate.plan', kind: 'gate', stage: 'planning' },
          { type: 'gate.research', kind: 'gate', stage: 'research' },
          { type: 'intake', kind: 'stage', stage: 'intake' },
          { type: 'plan', kind: 'stage', stage: 'planning' },
          { type: 'research', kind: 'stage', stage: 'research' },
        ],
      },
    },
    { name: 'empty', summary: 'No catalog yet: an empty state.', props: { items: [] } },
  ],
})
