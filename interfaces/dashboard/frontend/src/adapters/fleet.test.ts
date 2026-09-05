import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { toFleetRow, toStageDots } from './fleet'
import type { Run } from '../api/types'

const mkRun = (over: Partial<Run> = {}): Run => ({
  id: 'run-1',
  title: 'Test run',
  mode: 'brownfield',
  repo: 'org/repo',
  stageIdx: 3,
  status: 'running',
  blocker: null,
  cost: null,
  budget: 50,
  age: '10m',
  decisions: [],
  ...over,
})

describe('fleet adapter', () => {
  it('adapts a run into FleetRowProps preserving null cost', () => {
    const run = mkRun({ cost: null })
    const row = toFleetRow(run)
    expect(row.id).toBe('run-1')
    expect(row.title).toBe('Test run')
    expect(row.mode).toBe('brownfield')
    expect(row.cost).toBeNull()
    expect(row.href).toBe('/runs/run-1')
    expect(row.status.kind).toBe('running')
    expect(row.status.pulsing).toBe(true)
  })

  it('adapts stageIdx into per-stage StageDot state array', () => {
    const run = mkRun({ stageIdx: 2, status: 'running' })
    const dots = toStageDots(run)
    expect(dots).toHaveLength(14)
    expect(dots[0].state).toBe('done')
    expect(dots[1].state).toBe('done')
    expect(dots[2].state).toBe('active')
    expect(dots[3].state).toBe('pending')
  })

  it('satisfies the ownership rule: ui never imports from dashboard or api/types', () => {
    function getFiles(dir: string): string[] {
      const entries = readdirSync(dir)
      const files: string[] = []
      for (const e of entries) {
        const full = join(dir, e)
        if (statSync(full).isDirectory()) {
          files.push(...getFiles(full))
        } else if (full.endsWith('.ts') || full.endsWith('.vue')) {
          files.push(full)
        }
      }
      return files
    }

    const uiSrc = join(__dirname, '../../../../ui/src')
    const files = getFiles(uiSrc)
    const violations: string[] = []

    for (const f of files) {
      const content = readFileSync(f, 'utf8')
      if (content.includes("from '../../dashboard") || content.includes('api/types')) {
        violations.push(f)
      }
    }

    expect(violations).toEqual([])
  })
})
