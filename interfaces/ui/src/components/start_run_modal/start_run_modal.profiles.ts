import { defineProfiles } from '../../profile'
import StartRunModal from './StartRunModal.vue'

export default defineProfiles({
  component: 'start_run_modal',
  group: 'Modals',
  target: StartRunModal,
  profiles: [
    {
      name: 'open-filled',
      summary: 'Modal open with pre-filled valid feature title and repo.',
      props: {
        open: true,
        initialTitle: 'Add Google OAuth provider',
        initialRepo: 'git@github.com:Kit-Kroker/Kroker.git',
        initialMode: 'brownfield',
      },
    },
    {
      name: 'open-empty',
      summary: 'Modal open with empty title; submit is disabled.',
      props: {
        open: true,
        initialTitle: '',
        initialRepo: 'git@github.com:Kit-Kroker/Kroker.git',
        initialMode: 'brownfield',
      },
    },
    {
      name: 'closed',
      summary: 'Modal closed; nothing is rendered in DOM.',
      props: {
        open: false,
      },
    },
    {
      // 011 T014 (START_RUN_MODAL-3): a zero budget blocks the submit with
      // the omit-it message.
      name: 'with-budget-error',
      summary: 'Modal open with a zero budget; the inline error blocks submit.',
      props: {
        open: true,
        initialTitle: 'Add Google OAuth provider',
        initialRepo: 'git@github.com:Kit-Kroker/Kroker.git',
        initialMode: 'brownfield',
        initialBudget: '0',
      },
    },
  ],
})
