import { defineProfiles } from '../../profile'
import Button from './Button.vue'

export default defineProfiles({
  component: 'button',
  group: 'Primitives',
  target: Button,
  profiles: [
    { name: 'primary', summary: 'The one action a surface exists for: inverse ink.', props: { variant: 'primary' }, slots: { default: 'Run this version' } },
    { name: 'secondary', summary: 'Default action: raised ground, strong line.', props: { variant: 'secondary' }, slots: { default: 'Save' } },
    { name: 'ghost', summary: 'Low-weight action with no chrome until hover.', props: { variant: 'ghost' }, slots: { default: 'Cancel' } },
    { name: 'danger', summary: 'Ends or discards work: failed ink on a line.', props: { variant: 'danger' }, slots: { default: 'Abort task' } },
    { name: 'small', summary: 'Compact size for rows and label bars.', props: { variant: 'secondary', size: 'sm' }, slots: { default: 'Use suggestion' } },
    { name: 'disabled', summary: 'Locked: native disabled, dimmed.', props: { variant: 'primary', disabled: true }, slots: { default: 'Run this version' } },
    { name: 'busy', summary: 'In flight: locked and aria-busy.', props: { variant: 'primary', busy: true }, slots: { default: 'Sending…' } },
  ],
})
