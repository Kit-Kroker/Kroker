import { createRouter, createWebHashHistory } from 'vue-router'
import FleetView from '../features/fleet/FleetView.vue'
import InboxView from '../features/inbox/InboxView.vue'
import RunPage from './RunPage.vue'
import BoardTab from '../features/board/BoardTab.vue'
import GraphsView from '../features/graphs/GraphsView.vue'
import DesignView from '../features/graphs/DesignView.vue'
import CompareView from '../features/compare/CompareView.vue'
import { api } from '../api/client'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'fleet', component: FleetView },
    { path: '/inbox', name: 'inbox', component: InboxView },
    // 018 T072 (S10): /compare is the v5 benchmark view (arms × graphs +
    // the rework heatmap).
    { path: '/compare', name: 'compare', component: CompareView },
    {
      path: '/runs/:id',
      name: 'run',
      // R-13: the route component is the composition-only RunPage, which
      // fills RunView's #board slot with the board tab.
      component: RunPage,
      // R-4: the active tab travels as ?tab= and the rail section as ?rail=;
      // delivered as props only when the query carries a string. Replace,
      // never push, on switches.
      props: (r) => ({
        id: r.params.id as string,
        ...(typeof r.query.tab === 'string' ? { tab: r.query.tab } : {}),
        ...(typeof r.query.rail === 'string' ? { rail: r.query.rail } : {}),
      }),
    },
    // 018 T061 (S8): /graphs is the v5 catalog (cards + the PipelineConfig
    // panel). 018 T063: the query forms redirect onto the Design route —
    // ?sha=X lands on /graphs/X; ?from=run:ID resolves the run's pinned
    // sha first, so Design opens with the run copy loaded at its sha.
    {
      path: '/graphs',
      name: 'graphs',
      component: GraphsView,
      async beforeEnter(to) {
        const sha = to.query.sha
        if (typeof sha === 'string' && sha) return { path: `/graphs/${sha}`, replace: true }
        const from = to.query.from
        if (typeof from === 'string' && from.startsWith('run:')) {
          try {
            const res = await api.getRunGraph(from.slice(4))
            if (res.kind === 'graph' && res.sha) {
              return { path: `/graphs/${res.sha}`, query: { from }, replace: true }
            }
          } catch {
            /* fall through to the catalog */
          }
        }
        return true
      },
    },
    // 018 T063 (S9): Design on the shared canvas.
    { path: '/graphs/:sha', name: 'design', component: DesignView, props: true },
    {
      // 018 T054 (S7): the full Agent Board. BoardTab with its back link;
      // the run's row supplies the project key (BoardTab resolves it).
      path: '/runs/:id/board',
      name: 'run-board',
      component: BoardTab,
      props: (r) => ({ runId: r.params.id as string, back: true }),
    },
  ],
})
