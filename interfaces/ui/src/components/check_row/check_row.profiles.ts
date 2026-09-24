import { defineProfiles } from '../../profile'
import CheckRow from './CheckRow.vue'

export default defineProfiles({
  component: 'check_row',
  group: 'Data',
  target: CheckRow,
  profiles: [
    { name: 'absolute-failing', summary: 'The check that blocked the merge: failed tint.', props: { name: 'dangerous-eval', kind: 'ABSOLUTE', ok: false, detail: 'Pattern eval\\s*\\( matched in a test docstring. No call site.' } },
    { name: 'advisory-failing', summary: 'A failing advisory: neutral tint.', props: { name: 'traceability', kind: 'ADVISORY', ok: false, detail: '2 tasks cite no FR clause.' } },
    { name: 'passing', summary: 'A passing check: no ground.', props: { name: 'build_integration_green', kind: 'ABSOLUTE', ok: true, detail: '502/503 tests passed.' } },
  ],
})
