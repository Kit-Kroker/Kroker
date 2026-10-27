import { defineProfiles } from '../../profile'
import ToggleMenu from './ToggleMenu.vue'

export default defineProfiles({
  component: 'toggle_menu',
  group: 'Shell',
  target: ToggleMenu,
  profiles: [
    {
      name: 'session',
      summary: 'The ⋯ display menu with the four session toggles.',
      props: {
        items: [
          { id: 'payloads', label: 'Payloads', desc: 'show edge payloads on the canvas', on: true },
          { id: 'terminals', label: 'Terminals', desc: 'mark terminal stages on the canvas', on: true },
          { id: 'grid', label: 'Grid', desc: 'show the dot grid behind the canvas', on: false },
          { id: 'theme', label: 'Light theme', desc: 'light surfaces, same tokens', on: false },
        ],
      },
    },
    {
      name: 'all-off',
      summary: 'Every toggle off: no checks anywhere.',
      props: {
        items: [
          { id: 'payloads', label: 'Payloads', desc: '', on: false },
          { id: 'grid', label: 'Grid', desc: '', on: false },
        ],
      },
    },
  ],
})
