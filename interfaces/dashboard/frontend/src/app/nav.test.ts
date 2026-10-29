import { describe, it, expect } from 'vitest'
import { navManifest, designAvailable } from './nav'

// 018 T011 (RED): the v5 route manifest (data-model §5). Static parts only:
// the six ids in v5 order and this slice's availability flags. The run
// entry's dynamic label/target are pinned in shell/AppHeader.test.ts.
describe('navManifest', () => {
  it('lists the six entries primary-first in v5 order', () => {
    expect(navManifest.map((n) => n.id)).toEqual([
      'fleet',
      'inbox',
      'run',
      'graphs',
      'compare',
      'interfaces',
    ])
  })

  it('every v5 entry is available since T079', () => {
    for (const item of navManifest) {
      expect(item.available, item.id).toBe(true)
    }
  })

  it('Fleet, Inbox, run, Graphs and Compare are available', () => {
    const byId = new Map(navManifest.map((n) => [n.id, n]))
    for (const id of ['fleet', 'inbox', 'run', 'graphs', 'compare', 'interfaces']) {
      expect(byId.get(id)?.available, id).toBe(true)
    }
  })

  it('Design is available since the Design route landed (T063)', () => {
    expect(designAvailable).toBe(true)
  })
})
