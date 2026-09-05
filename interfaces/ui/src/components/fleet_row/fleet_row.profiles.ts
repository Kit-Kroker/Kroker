import { defineProfiles } from '../../profile'
import FleetRow from './FleetRow.vue'

const dots = (activeIdx: number, status: string) => [
  { stage: 'intake', state: 'done' as const },
  { stage: 'clarify', state: (activeIdx === 1 ? status : 'done') as any },
  { stage: 'architecture', state: (activeIdx === 2 ? status : 'pending') as any },
  { stage: 'code', state: 'pending' as const },
]

export default defineProfiles({
  component: 'fleet_row',
  group: 'Fleet',
  target: FleetRow,
  profiles: [
    {
      name: 'typical',
      summary: 'A typical in-flight run with cost and age.',
      props: {
        id: 'run-feat-auth',
        title: 'Add oauth2 authentication provider',
        mode: 'brownfield',
        dots: dots(1, 'active'),
        status: { kind: 'running', label: 'running', pulsing: true },
        blocker: null,
        cost: 4.25,
        age: '14m',
        href: '/runs/run-feat-auth',
      },
    },
    {
      name: 'null-cost',
      summary: 'Unresolved cost renders as an em dash.',
      props: {
        id: 'run-spec-intake',
        title: 'Intake spec review',
        mode: 'greenfield',
        dots: dots(0, 'active'),
        status: { kind: 'pending', label: 'pending', pulsing: false },
        blocker: null,
        cost: null,
        age: '1m',
        href: '/runs/run-spec-intake',
      },
    },
    {
      name: 'crowded-trail',
      summary: 'A long title truncates with ellipsis without shifting columns.',
      props: {
        id: 'run-long-title',
        title: 'Refactor enterprise telemetry pipeline across multiple asynchronous distributed workflow workers',
        mode: 'brownfield',
        dots: dots(2, 'active'),
        status: { kind: 'running', label: 'running', pulsing: true },
        blocker: null,
        cost: 18.5,
        age: '1h 22m',
        href: '/runs/run-long-title',
      },
    },
    {
      name: 'blocked-at-gate',
      summary: 'Held at a gate with pulsing pip and blocker text.',
      props: {
        id: 'run-blocked',
        title: 'Migrate users database table',
        mode: 'brownfield',
        dots: dots(1, 'blocked'),
        status: { kind: 'blocked', label: 'awaiting human', pulsing: true },
        blocker: 'architecture gate',
        cost: 3.12,
        age: '2h',
        href: '/runs/run-blocked',
      },
    },
    {
      name: 'terminal-failed',
      summary: 'Terminal failed run with failure blocker.',
      props: {
        id: 'run-failed',
        title: 'Deploy canary to production',
        mode: 'brownfield',
        dots: dots(2, 'failed'),
        status: { kind: 'failed', label: 'failed', pulsing: false },
        blocker: 'health check failed',
        cost: 1.8,
        age: '5h',
        href: '/runs/run-failed',
      },
    },
  ],
})
