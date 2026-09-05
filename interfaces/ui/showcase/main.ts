import { createApp } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import Showcase from './Showcase.vue'
import '../src/tokens/tokens.css'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:catchAll(.*)', component: { template: '<div />' } }],
})

createApp(Showcase).use(router).mount('#app')
