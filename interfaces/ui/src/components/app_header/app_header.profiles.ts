import { defineProfiles } from '../../profile'
import AppHeader from './AppHeader.vue'

const primary = [
  { id: 'fleet', label: 'Fleet', to: '/', available: true },
  { id: 'inbox', label: 'Inbox', to: '/inbox', available: true },
]
const secondary = [
  { id: 'graphs', label: 'Graphs', to: '/graphs', available: true },
  { id: 'compare', label: 'Compare', to: '/compare', available: false },
  { id: 'interfaces', label: 'Interfaces', to: '/interfaces', available: false },
]

export default defineProfiles({
  component: 'app_header',
  group: 'Shell',
  target: AppHeader,
  profiles: [
    {
      name: 'with-inbox',
      summary: 'v5 header with the inbox badge and unavailable secondary items hidden.',
      props: { primary, secondary, badge: 3 },
    },
    {
      name: 'zero-inbox',
      summary: 'Zero badge: the inbox badge is omitted, never a "0".',
      props: { primary, secondary, badge: 0 },
    },
    {
      name: 'run-switch',
      summary: 'Run in context with two run tabs and the Observe mode set.',
      props: {
        primary,
        secondary,
        badge: 5,
        runSwitch: {
          tabs: [
            { label: 'run feature-1', to: '/runs/feature-1', active: true },
            { label: 'run feature-2', to: '/runs/feature-2' },
          ],
          active: 'feature-1',
          mode: 'observe',
        },
      },
    },
    {
      name: 'sparse',
      summary: 'Every list empty: the wordmark and the Search/⋯ skeleton remain.',
      props: { primary: [], secondary: [], badge: 0 },
    },
  ],
})
