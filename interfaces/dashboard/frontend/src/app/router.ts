import { createRouter, createWebHashHistory } from 'vue-router'
import FleetView from '../features/fleet/FleetView.vue'
import InboxView from '../features/inbox/InboxView.vue'
import RunPage from './RunPage.vue'
import GraphEditorView from '../features/graphs/GraphEditorView.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'fleet', component: FleetView },
    { path: '/inbox', name: 'inbox', component: InboxView },
    {
      path: '/runs/:id',
      name: 'run',
      // R-13: the route component is the composition-only RunPage, which
      // fills RunView's #board slot with the board tab.
      component: RunPage,
      // R-4: the active tab travels as ?tab=; delivered as a prop only when
      // the query carries a string. Replace, never push, on switches.
      props: (r) => ({
        id: r.params.id as string,
        ...(typeof r.query.tab === 'string' ? { tab: r.query.tab } : {}),
      }),
    },
    { path: '/graphs', name: 'graphs', component: GraphEditorView },
  ],
})
