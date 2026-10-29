import { defineProfiles } from '../../profile'
import CheckMatrix from './CheckMatrix.vue'

const COLUMNS = [
  { key: 'layers', name: 'Layers', ref: 'harness declarations' },
  { key: 'strict', name: 'Strict', ref: 'policy/containment.yaml' },
  { key: 'family', name: 'Family', ref: 'agents/registry.yaml' },
  { key: 'installed', name: 'Installed', ref: 'unmeasured' },
  { key: 'checkpoint', name: 'Checkpoint', ref: 'unmeasured' },
  { key: 'session', name: 'Session', ref: 'unmeasured' },
]

export default defineProfiles({
  component: 'check_matrix',
  group: 'Data',
  target: CheckMatrix,
  profiles: [
    {
      name: 'interfaces',
      summary: 'The Interfaces matrix: four measured harnesses and the planned pyai row.',
      props: {
        columns: COLUMNS,
        rows: [
          {
            harness: 'claude_code',
            sub: 'claude -p',
            planned: false,
            cells: [
              { state: 'yes', text: 'native + hook' },
              { state: 'yes', text: 'starts' },
              { state: 'not_measured', text: '' },
              { state: 'not_measured', text: '' },
              { state: 'not_measured', text: '' },
              { state: 'not_measured', text: '' },
            ],
          },
          {
            harness: 'opencode',
            sub: 'opencode run',
            planned: false,
            cells: [
              { state: 'yes', text: 'native' },
              { state: 'partial', text: 'refuses: read-only-sandbox, no-test-edit-during-repair' },
              { state: 'yes', text: 'zai-coding-plan' },
              { state: 'not_measured', text: '' },
              { state: 'not_measured', text: '' },
              { state: 'not_measured', text: '' },
            ],
          },
          {
            harness: 'cursor',
            sub: 'cursor agent',
            planned: false,
            cells: [
              { state: 'partial', text: 'none' },
              { state: 'not_measured', text: '' },
              { state: 'not_measured', text: '' },
              { state: 'not_measured', text: '' },
              { state: 'not_measured', text: '' },
              { state: 'not_measured', text: '' },
            ],
          },
          {
            harness: 'crew',
            sub: 'lead + critics',
            planned: false,
            cells: [
              { state: 'partial', text: 'per role harness' },
              { state: 'not_measured', text: '' },
              { state: 'not_measured', text: '' },
              { state: 'not_measured', text: '' },
              { state: 'not_measured', text: '' },
              { state: 'not_measured', text: '' },
            ],
          },
          {
            harness: 'pyai',
            sub: 'pydantic-ai agents',
            planned: true,
            cells: COLUMNS.map(() => ({ state: 'planned', text: '' })),
          },
        ],
        facts: [
          {
            who: 'opencode',
            severity: 'warn',
            text: 'hook-layer rules land in rules_unenforceable: read-only-sandbox, no-test-edit-during-repair',
          },
          { who: 'cursor', severity: 'error', text: 'no containment layers - nothing to enforce' },
        ],
      },
    },
    {
      name: 'sparse',
      summary: 'One measured row, one column, no facts.',
      props: {
        columns: [{ key: 'layers', name: 'Layers', ref: 'harness declarations' }],
        rows: [
          { harness: 'opencode', sub: 'opencode run', planned: false, cells: [{ state: 'yes', text: 'native' }] },
        ],
        facts: [],
      },
    },
  ],
})
