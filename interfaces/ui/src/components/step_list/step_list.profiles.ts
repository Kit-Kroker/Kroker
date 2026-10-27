import { defineProfiles } from '../../profile'
import StepList from './StepList.vue'
import type { CanvasStatus } from '../graph_canvas/types'

export default defineProfiles({
  component: 'step_list',
  group: 'Data',
  target: StepList,
  profiles: [
    {
      name: 'inner-loop',
      summary: 'A code node\'s inner loop: steps with mixed statuses and meta lines.',
      props: {
        steps: [
          { name: 'read plan', ref: 'plan@sha1', status: 'done' as CanvasStatus, meta: '0m 03s' },
          { name: 'patch file', ref: 'src/api.py', status: 'running' as CanvasStatus, meta: 'attempt 2' },
          { name: 'run tests', ref: 'pytest -q', status: 'idle' as CanvasStatus, meta: '' },
          { name: 'quarantine', ref: 'tasks 4-7', status: 'failed' as CanvasStatus, meta: 'failed:quarantined-tasks' },
        ],
      },
    },
    {
      name: 'single-done',
      summary: 'One finished step: pip done, meta elapsed.',
      props: {
        steps: [{ name: 'verify', ref: 'v1', status: 'done' as CanvasStatus, meta: '0m 41s' }],
      },
    },
  ],
})
