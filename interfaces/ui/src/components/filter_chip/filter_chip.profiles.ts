import { defineProfiles } from '../../profile'
import FilterChip from './FilterChip.vue'

export default defineProfiles({
  component: 'filter_chip',
  group: 'Primitives',
  target: FilterChip,
  profiles: [
    { name: 'selected', summary: 'The active filter, with a count.', props: { label: 'All', count: 5, selected: true } },
    { name: 'unselected', summary: 'An available filter.', props: { label: 'Escalations', count: 1 } },
    { name: 'zero', summary: 'A filter with nothing in it still shows 0.', props: { label: 'Quarantined', count: 0 } },
    { name: 'disabled', summary: 'Unavailable filter.', props: { label: 'Blocked', disabled: true } },
  ],
})
