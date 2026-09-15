import { defineProfiles } from '../../profile'
import IssueList from './IssueList.vue'

export default defineProfiles({
  component: 'issue_list',
  group: 'Graph',
  target: IssueList,
  profiles: [
    { name: 'none', summary: 'A clean draft.', props: { items: [] } },
    {
      name: 'mixed',
      summary: 'An edge error, a node error and a graph-level warning.',
      props: {
        items: [
          { key: 'i0', severity: 'error', message: 'intake.ok (signal) cannot feed architect.requirements', targetLabel: 'intake.ok → architect.requirements', focusKey: 'e0' },
          { key: 'i1', severity: 'error', message: "node id 'intake' is used by 2 nodes", targetLabel: 'intake', focusKey: 'intake' },
          { key: 'i2', severity: 'warning', message: 'no path reaches every node', targetLabel: 'graph', focusKey: null },
        ],
      },
    },
  ],
})
