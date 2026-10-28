import { defineProfiles } from '../../profile'
import CatalogCard from './CatalogCard.vue'

export default defineProfiles({
  component: 'catalog_card',
  group: 'Graph',
  target: CatalogCard,
  profiles: [
    {
      name: 'shipped',
      summary: 'A shipped graph with full metadata: counts and the Design action.',
      props: {
        kicker: 'shipped graph',
        name: 'default',
        sha: 'a021c25b8f7e012faaf9f4de9664d8cc5b11a977c1b878e20d50cfec78b23c38',
        description: 'The pre-code pipeline as shipped.',
        when: '2026-09-20',
        counts: [
          { label: 'nodes', n: 12 },
          { label: 'gates', n: 2 },
          { label: 'edges', n: 20 },
        ],
        action: { label: 'Open in Design' },
      },
    },
    {
      name: 'unmeasured',
      summary: 'A card with no description and no when-used date: not measured, never null.',
      props: {
        kicker: 'shipped graph',
        name: 'seeded',
        sha: 'c1bbef2d33379ca4252d8971ed4b65934dd54e7d4c306a887698df0f0520c5ab',
        description: null,
        when: null,
        counts: [
          { label: 'nodes', n: 7 },
          { label: 'gates', n: 0 },
          { label: 'edges', n: 12 },
        ],
        action: { label: 'Open in Design' },
      },
    },
  ],
})
