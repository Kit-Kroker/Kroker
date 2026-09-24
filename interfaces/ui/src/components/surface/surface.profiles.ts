import { defineProfiles } from '../../profile'
import Surface from './Surface.vue'

export default defineProfiles({
  component: 'surface',
  group: 'Primitives',
  target: Surface,
  profiles: [
    { name: 'card', summary: 'Flat card: raised ground, line, 8px radius.', props: { elevation: 'flat' }, slots: { default: 'architect · waiting at gate' } },
    { name: 'overlay', summary: 'Popover or menu: 12px radius and the overlay shadow.', props: { elevation: 'overlay', padding: 'sm', as: 'ul' }, slots: { default: 'Show all schemas' } },
  ],
})
