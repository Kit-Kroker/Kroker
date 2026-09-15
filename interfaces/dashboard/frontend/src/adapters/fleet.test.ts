import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { toFleetRow, toStageDots } from './fleet'
import type { Run } from '../api/types'
import catalogJson from '../api/__fixtures__/graph/catalog.json'

const CANONICAL: string[] = catalogJson.canonical_stages

const mkRun = (over: Partial<Run> = {}): Run => ({
  id: 'run-1',
  title: 'Test run',
  mode: 'brownfield',
  repo: 'org/repo',
  activeStages: ['requirements'],
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
    const row = toFleetRow(run, CANONICAL)
    expect(row.id).toBe('run-1')
    expect(row.title).toBe('Test run')
    expect(row.mode).toBe('brownfield')
    expect(row.cost).toBeNull()
    expect(row.href).toBe('/runs/run-1')
    expect(row.status.kind).toBe('running')
    expect(row.status.pulsing).toBe(true)
  })

  it('renders one dot per served canonical stage, keyed by name', () => {
    const dots = toStageDots(mkRun({ activeStages: ['clarify'], status: 'running' }), CANONICAL)
    expect(dots.map((d) => d.stage)).toEqual(CANONICAL)
    expect(dots).toHaveLength(18)
    expect(dots.find((d) => d.stage === 'research')!.state).toBe('done')
    expect(dots.find((d) => d.stage === 'clarify')!.state).toBe('active')
    expect(dots.find((d) => d.stage === 'architecture')!.state).toBe('pending')
  })

  it('regression: a run at clarify never lights architecture (the 14/18 index defect)', () => {
    const dots = toStageDots(mkRun({ activeStages: ['clarify'], status: 'blocked' }), CANONICAL)
    expect(dots.filter((d) => d.state === 'blocked').map((d) => d.stage)).toEqual(['clarify'])
  })

  it('renders nothing before the catalog loads', () => {
    expect(toStageDots(mkRun(), [])).toEqual([])
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
