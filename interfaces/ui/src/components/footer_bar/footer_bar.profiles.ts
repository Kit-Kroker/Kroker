import { defineProfiles } from '../../profile'
import FooterBar from './FooterBar.vue'

export default defineProfiles({
  component: 'footer_bar',
  group: 'Shell',
  target: FooterBar,
  profiles: [
    {
      name: 'fleet-total',
      summary: 'Footer with the priced fleet total on the left and the command hint on the right.',
      props: { left: '$145.20 · 2 not priced', right: '⌘K commands' },
    },
    {
      name: 'empty-left',
      summary: 'Canvas screen: the left slot is empty, only the command hint shows.',
      props: { left: '', right: '⌘K commands' },
    },
  ],
})
