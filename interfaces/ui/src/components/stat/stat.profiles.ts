import { defineProfiles } from '../../profile'
import Stat from './Stat.vue'

export default defineProfiles({
  component: 'stat',
  group: 'Data',
  target: Stat,
  profiles: [
    { name: 'with-pip', summary: 'Status count led by its pip.', props: { label: 'In progress', value: 2, pip: 'in_progress' } },
    { name: 'plain', summary: 'Plain counter.', props: { label: 'Fix attempts', value: 6 } },
    { name: 'zero', summary: 'Zero renders as 0.', props: { label: 'Failed', value: 0, pip: 'failed' } },
    { name: 'unknown', summary: 'No value yet renders a dash.', props: { label: 'Spend', value: null } },
  ],
})
