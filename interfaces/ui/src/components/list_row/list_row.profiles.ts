import { defineProfiles } from '../../profile'
import ListRow from './ListRow.vue'

export default defineProfiles({
  component: 'list_row',
  group: 'Data',
  target: ListRow,
  profiles: [
    { name: 'selected', summary: 'Selected row: raised ground and inset line.', props: { selected: true }, slots: { default: 'Degraded mode: PPTX-only when the renderer is down', meta: '09-23 09:22' } },
    { name: 'plain', summary: 'Unselected row with a meta column.', props: {}, slots: { default: 'Render retry endpoint in the API process', meta: '09-23 09:40' } },
    { name: 'dense', summary: 'Dense row for execution rails.', props: { dense: true }, slots: { default: 'architect' } },
    { name: 'disabled', summary: 'Not reached: muted and inert.', props: { disabled: true }, slots: { default: 'deploy' } },
  ],
})
