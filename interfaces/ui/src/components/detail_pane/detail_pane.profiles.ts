import { defineProfiles } from '../../profile'
import DetailPane from './DetailPane.vue'

export default defineProfiles({
  component: 'detail_pane',
  group: 'Data',
  target: DetailPane,
  profiles: [
    {
      name: 'task',
      summary: 'A board task: eyebrow id, title, key/value grid.',
      props: {
        eyebrow: 'T09',
        title: 'Degraded mode: PPTX-only when the renderer is down',
        fields: [
          { k: 'Plan', v: 'v3' },
          { k: 'Run', v: 'feature-neon-welcome-phase-2-package-and-deliver' },
          { k: 'Branch', v: 'sdlc/neon-p2/T09' },
          { k: 'Fix attempts', v: 2 },
          { k: 'Error', v: null },
        ],
      },
    },
    { name: 'title-only', summary: 'No fields: the grid is absent.', props: { title: 'Select a decision.' } },
  ],
})
