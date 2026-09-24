import { defineProfiles } from '../../profile'
import Tag from './Tag.vue'

export default defineProfiles({
  component: 'tag',
  group: 'Primitives',
  target: Tag,
  profiles: [
    { name: 'neutral', summary: 'Outlined label, e.g. a decision kind.', props: {}, slots: { default: 'Gate · architecture' } },
    { name: 'strong', summary: 'Inverse label for the one marked item.', props: { tone: 'strong' }, slots: { default: 'Best' } },
    { name: 'mono', summary: 'Mono label for identifiers, e.g. evidence kinds.', props: { mono: true }, slots: { default: 'qa' } },
  ],
})
