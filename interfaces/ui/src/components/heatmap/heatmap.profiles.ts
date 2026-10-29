import { defineProfiles } from '../../profile'
import Heatmap from './Heatmap.vue'

export default defineProfiles({
  component: 'heatmap',
  group: 'Data',
  target: Heatmap,
  profiles: [
    {
      name: 'rework',
      summary: 'Rework by canonical stage: two arms, values, low n and blanks.',
      props: {
        columns: ['research', 'clarify', 'architecture', 'plan', 'code', 'qa', 'review'],
        rows: [
          {
            name: 'opencode × zai-coding-plan/glm-5.3',
            cells: [
              { state: 'value', value: 0.12, n: 9 },
              { state: 'value', value: 0.0, n: 14 },
              { state: 'low_n', value: 0.31, n: 2 },
              { state: 'blank', value: null, n: 0 },
              { state: 'value', value: 0.66, n: 11 },
              { state: 'low_n', value: 0.2, n: 3 },
              { state: 'blank', value: null, n: 0 },
            ],
          },
          {
            name: 'opencode × zai-coding-plan/glm-5.2',
            cells: [
              { state: 'value', value: 0.0, n: 10 },
              { state: 'blank', value: null, n: 0 },
              { state: 'value', value: 0.44, n: 12 },
              { state: 'value', value: 0.9, n: 12 },
              { state: 'value', value: 0.28, n: 12 },
              { state: 'value', value: 0.05, n: 8 },
              { state: 'low_n', value: 0.5, n: 1 },
            ],
          },
        ],
      },
    },
    {
      name: 'sparse',
      summary: 'One arm, one stage: the low-n-only view.',
      props: {
        columns: ['code'],
        rows: [
          { name: 'opencode × zai-coding-plan/glm-5.3', cells: [{ state: 'low_n', value: 0.75, n: 2 }] },
        ],
      },
    },
  ],
})
