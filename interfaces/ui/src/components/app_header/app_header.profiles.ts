import { defineProfiles } from '../../profile'
import AppHeader from './AppHeader.vue'

export default defineProfiles({
  component: 'app_header',
  group: 'Shell',
  target: AppHeader,
  profiles: [
    {
      name: 'with-inbox',
      summary: 'Header with active items waiting in inbox and fleet tab active.',
      props: {
        activeCount: 12,
        maxCount: 50,
        totalCost: '$145.20',
        inboxCount: 3,
        activeTab: 'fleet',
      },
    },
    {
      name: 'zero-inbox',
      summary: 'Header with zero inbox items; inbox badge is omitted.',
      props: {
        activeCount: 5,
        maxCount: 50,
        totalCost: '$42.00',
        inboxCount: 0,
        activeTab: 'fleet',
      },
    },
    {
      name: 'inbox-active',
      summary: 'Inbox tab is active with amber underline.',
      props: {
        activeCount: 8,
        maxCount: 50,
        totalCost: '$88.50',
        inboxCount: 5,
        activeTab: 'inbox',
      },
    },
  ],
})
