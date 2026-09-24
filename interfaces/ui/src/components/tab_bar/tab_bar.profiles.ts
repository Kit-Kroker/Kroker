import { defineProfiles } from '../../profile'
import TabBar from './TabBar.vue'

export default defineProfiles({
  component: 'tab_bar',
  group: 'Shell',
  target: TabBar,
  profiles: [
    {
      name: 'run',
      summary: 'Run tabs with Board active and one gate waiting.',
      props: {
        label: 'Run',
        active: 'board',
        tabs: [{ id: 'graph', label: 'Graph' }, { id: 'board', label: 'Board' }, { id: 'gates', label: 'Gates', count: 1 }, { id: 'cost', label: 'Cost', count: 0 }],
      },
    },
    {
      name: 'disabled-tab',
      summary: 'A tab the server has no capability for yet.',
      props: { active: 'graph', tabs: [{ id: 'graph', label: 'Graph' }, { id: 'board', label: 'Board', disabled: true }] },
    },
  ],
})
