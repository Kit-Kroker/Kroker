// interfaces/ui/scripts/build-ds-bundle.spec.ts
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'

// 018 T049: stage_dots is deleted (the strip retired, S6); the bundle
// contract is retargeted to a surviving profile — status_pip's running
// state and its .cmp-status-pip class.
const f = 'dist-ds/status_pip/running.html'

describe('the ds bundle', () => {
  it('emits one file per profile', () => { // clause: DS_BUNDLE-1
    expect(existsSync(f)).toBe(true)
  })

  it('puts the dsCard marker on the literal first line', () => { // clause: DS_BUNDLE-2
    const first = readFileSync(f, 'utf8').split('\n')[0]
    expect(first).toMatch(/^<!-- @dsCard group="[^"]+" -->$/)
  })

  it('inlines the styles so a preview stands alone', () => { // clause: DS_BUNDLE-3
    expect(readFileSync(f, 'utf8')).toContain('.cmp-status-pip')
  })
})
