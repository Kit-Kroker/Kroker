import { defineProfiles } from '../../profile'
import Toasts from './Toasts.vue'

export default defineProfiles({
  component: 'toasts',
  group: 'Feedback',
  target: Toasts,
  profiles: [
    {
      name: 'multiple',
      summary: 'Multiple active notification toasts with distinct colors.',
      props: {
        toasts: [
          { id: 't1', msg: 'Run started — feature-123', color: 'var(--status-running)' },
          { id: 't2', msg: 'Clarification resolved', color: 'var(--status-done)' },
          { id: 't3', msg: 'Title required', color: 'var(--status-blocked)' },
        ],
      },
    },
    {
      name: 'empty',
      summary: 'Empty toasts list renders nothing at all.',
      props: {
        toasts: [],
      },
    },
  ],
})
