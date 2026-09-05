// interfaces/ui/scripts/build-ds-bundle.spec.ts
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'

const f = 'dist-ds/stage_dots/every-state.html'

describe('the ds bundle', () => {
  it('emits one file per profile', () => { // clause: DS_BUNDLE-1
    expect(existsSync(f)).toBe(true)
  })

  it('puts the dsCard marker on the literal first line', () => { // clause: DS_BUNDLE-2
    const first = readFileSync(f, 'utf8').split('\n')[0]
    expect(first).toMatch(/^<!-- @dsCard group="[^"]+" -->$/)
  })

  it('inlines the styles so a preview stands alone', () => { // clause: DS_BUNDLE-3
    expect(readFileSync(f, 'utf8')).toContain('.cmp-stage-dot')
  })
})
