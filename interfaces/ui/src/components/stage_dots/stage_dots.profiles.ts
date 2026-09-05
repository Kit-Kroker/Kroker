import { defineProfiles } from '../../profile'
import StageDots from './StageDots.vue'

const S = ['intake', 'clarify', 'architecture', 'code', 'review', 'qa', 'deploy']
const all = (state: string) => S.map((stage) => ({ stage, state }))

export default defineProfiles({
  component: 'stage_dots',
  group: 'Fleet',
  target: StageDots,
  profiles: [
    { name: 'untouched', summary: 'A queued run: every stage pending.', props: { dots: all('pending') } },
    { name: 'mid-flight', summary: 'Four done, one active, the rest pending.',
      props: { dots: S.map((stage, i) => ({ stage, state: i < 4 ? 'done' : i === 4 ? 'active' : 'pending' })) } },
    { name: 'blocked', summary: 'Held at a gate — the blocked mark pulses.',
      props: { dots: S.map((stage, i) => ({ stage, state: i < 3 ? 'done' : i === 3 ? 'blocked' : 'pending' })) } },
    { name: 'every-state', summary: 'All six states in sequence, for mark comparison.',
      props: { dots: ['pending', 'active', 'done', 'blocked', 'failed', 'skipped'].map((state, i) => ({ stage: S[i], state })) } },
    { name: 'empty', summary: 'An unresolved pipeline renders no marks and is not an error.', props: { dots: [] } },
  ],
})
