import { defineProfiles } from '../../profile'
import Field from './Field.vue'

export default defineProfiles({
  component: 'field',
  group: 'Forms',
  target: Field,
  profiles: [
    { name: 'with-hint', summary: 'Gate comment with its rule as a hint.', props: { label: 'Comment', modelValue: '', placeholder: 'Optional for approve.', hint: 'Required to revise or reject.' } },
    { name: 'error', summary: 'Required justification left blank on submit.', props: { label: 'Justification', modelValue: '', required: true, error: 'Justification is required for this action.' } },
    { name: 'single-line', summary: 'Single-line input.', props: { label: 'Title', modelValue: 'Scope publish dedupe by run_id', multiline: false } },
    { name: 'disabled', summary: 'Locked while a decision is in flight.', props: { label: 'Answer', modelValue: 'Require a static bearer token.', disabled: true } },
  ],
})
