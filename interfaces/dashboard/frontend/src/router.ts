import { createRouter, createWebHashHistory } from 'vue-router'
import FleetView from './views/FleetView.vue'
import InboxView from './views/InboxView.vue'
import RunView from './views/RunView.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'fleet', component: FleetView },
    { path: '/inbox', name: 'inbox', component: InboxView },
    { path: '/runs/:id', name: 'run', component: RunView, props: true },
  ],
})
