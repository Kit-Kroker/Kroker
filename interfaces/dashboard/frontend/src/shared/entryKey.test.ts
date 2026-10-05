// FR-012: a per-entry key is formed only by entryKey(item), and it must mix
// the run id and the item id so two runs sharing an id never collide. The
// pair { runId: 'a:b', id: 'c' } and { runId: 'a', id: 'b:c' } guards the
// separator: a naive join on ':' would confuse them.
import { describe, it, expect } from 'vitest'
import { entryKey } from './entryKey'

describe('entryKey', () => {
  it('two items with different runId and the same id give different keys', () => {
    const a = { runId: 'feature-add-sso', id: 'architecture#1' }
    const b = { runId: 'feature-graph-demo', id: 'architecture#1' }
    expect(entryKey(a)).not.toBe(entryKey(b))
  })

  it('a colon in the runId does not merge with a colon in the id', () => {
    const a = { runId: 'a:b', id: 'c' }
    const b = { runId: 'a', id: 'b:c' }
    expect(entryKey(a)).not.toBe(entryKey(b))
  })

  it('the same runId and id give the same key on two calls, and extra fields do not change it', () => {
    const a = { runId: 'feature-add-sso', id: 'q1' }
    const b = { runId: 'feature-add-sso', id: 'q1', type: 'clarify', title: 'Answer the question' }
    expect(entryKey(a)).toBe(entryKey(a))
    expect(entryKey(a)).toBe(entryKey(b))
  })
})
