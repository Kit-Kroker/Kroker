import { createRouter, createWebHashHistory } from 'vue-router'
import FleetView from '../features/fleet/FleetView.vue'
import InboxView from '../features/inbox/InboxView.vue'
import RunView from '../features/run/RunView.vue'
import GraphEditorView from '../features/graphs/GraphEditorView.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'fleet', component: FleetView },
    { path: '/inbox', name: 'inbox', component: InboxView },
    { path: '/runs/:id', name: 'run', component: RunView, props: true },
    { path: '/graphs', name: 'graphs', component: GraphEditorView },
  ],
})
