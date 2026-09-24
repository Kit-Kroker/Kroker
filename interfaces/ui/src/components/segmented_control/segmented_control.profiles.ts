import { defineProfiles } from '../../profile'
import SegmentedControl from './SegmentedControl.vue'

export default defineProfiles({
  component: 'segmented_control',
  group: 'Primitives',
  target: SegmentedControl,
  profiles: [
    {
      name: 'mode',
      summary: 'Two-way mode switch, as in the pipeline header.',
      props: { label: 'Mode', modelValue: 'observe', options: [{ value: 'observe', label: 'Observe' }, { value: 'design', label: 'Design' }] },
    },
    {
      name: 'with-counts',
      summary: 'Three views with counts, as on the run board.',
      props: {
        label: 'Board view',
        modelValue: 'tasks',
        options: [{ value: 'tasks', label: 'Tasks', count: 11 }, { value: 'artifacts', label: 'Artifacts', count: 3 }, { value: 'events', label: 'Events', count: 0 }],
      },
    },
  ],
})
