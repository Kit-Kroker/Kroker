import { defineProfiles } from '../../profile'
import FleetTable from './FleetTable.vue'

const dots = (activeIdx: number, status: string) => [
  { stage: 'intake', state: 'done' as const },
  { stage: 'clarify', state: (activeIdx === 1 ? status : 'done') as any },
  { stage: 'architecture', state: (activeIdx === 2 ? status : 'pending') as any },
  { stage: 'code', state: 'pending' as const },
]

export default defineProfiles({
  component: 'fleet_table',
  group: 'Fleet',
  target: FleetTable,
  profiles: [
    {
      name: 'populated',
      summary: 'A populated fleet with multiple runs in various states.',
      props: {
        rows: [
          {
            id: 'run-auth',
            title: 'Add oauth provider',
            mode: 'brownfield',
            dots: dots(1, 'active'),
            status: { kind: 'running', label: 'running', pulsing: true },
            blocker: null,
            cost: 4.25,
            age: '14m',
            href: '/runs/run-auth',
          },
          {
            id: 'run-blocked',
            title: 'Schema migration',
            mode: 'brownfield',
            dots: dots(1, 'blocked'),
            status: { kind: 'blocked', label: 'awaiting human', pulsing: true },
            blocker: 'clarify gate',
            cost: 3.1,
            age: '2h',
            href: '/runs/run-blocked',
          },
          {
            id: 'run-done',
            title: 'Fix edge router',
            mode: 'greenfield',
            dots: dots(3, 'done'),
            status: { kind: 'done', label: 'done', pulsing: false },
            blocker: null,
            cost: null,
            age: '1d',
            href: '/runs/run-done',
          },
        ],
      },
    },
    {
      name: 'empty',
      summary: 'An empty fleet displaying the header and empty state message.',
      props: {
        rows: [],
      },
    },
  ],
})
