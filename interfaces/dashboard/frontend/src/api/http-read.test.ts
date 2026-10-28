import { describe, it, expect } from 'vitest'
import { mapFleetSummary, mapShippedGraphs } from './http-read'
import fixture from './__fixtures__/read/fleet-summary.json'
import shippedFixture from './__fixtures__/read/graphs-shipped.json'

// 018 T048 (RED): the fleet-summary read mapper. The recorded fixture is the
// wire; the mapper answers camelCase. RED cause: ./http-read does not exist.

describe('mapFleetSummary (018 T048 RED)', () => {
  it('maps the recorded fixture to camelCase rows and unreadable ids', () => {
    const summary = mapFleetSummary(fixture as never)
    const graph = summary.runs.find((r) => r.runId === 'graph-run')!
    expect(graph.graphSha).toBe('a021c25b8f7e012faaf9f4de9664d8cc5b11a977c1b878e20d50cfec78b23c38')
    expect(graph.graphName).toBe('default')
    expect(graph.arm).toEqual({ harness: 'opencode', model: 'zai-coding-plan/glm-5.3' })
    expect(graph.traversals).toHaveLength(2)
    expect(graph.traversals[0]).toMatchObject({
      used: 0,
      max: 2,
      edge: { source: 'architecture', sourcePort: 'revise', target: 'architect', targetPort: 'guidance' },
    })
    expect(graph.outcome).toEqual({ state: 'running', reason: null, result: null })
    expect(graph.where).toEqual(['intake'])
    expect(graph.gateTimeouts[0]).toMatchObject({ gate: 'clarify', onTimeout: 'reject' })

    const legacy = summary.runs.find((r) => r.runId === 'legacy-run')!
    expect(legacy.graphSha).toBeNull()
    expect(legacy.outcome).toBeNull()
    expect(legacy.traversals).toEqual([])

    expect(summary.unreadable).toEqual(['unreadable-run'])
  })

  it('maps gate_timeouts key casing per row (the gated run carries exactly one)', () => {
    const summary = mapFleetSummary(fixture as never)
    const gated = summary.runs.find((r) => r.runId === 'gated-run')!
    expect(gated.gateTimeouts).toEqual([{ gate: 'architecture', onTimeout: 'reject' }])
  })
})

// --- 018 T060 (RED): the shipped-graphs mapper --------------------------------

describe('mapShippedGraphs (018 T060 RED)', () => {
  it('maps the recorded fixture: three graphs, null description/when preserved, counts from the wire numbers', () => {
    const shipped = mapShippedGraphs(shippedFixture as never)
    expect(shipped.graphs.map((g: { name: string }) => g.name)).toEqual([
      'default', 'default-research', 'seeded',
    ])
    const def = shipped.graphs[0] as Record<string, unknown>
    expect(def['sha']).toBe('a021c25b8f7e012faaf9f4de9664d8cc5b11a977c1b878e20d50cfec78b23c38')
    expect(def['description']).toBeNull()
    expect(def['when']).toBeNull()
    expect(def['counts']).toEqual([
      { label: 'nodes', n: 12 },
      { label: 'gates', n: 2 },
      { label: 'edges', n: 20 },
    ])
    const seeded = shipped.graphs[2] as Record<string, unknown>
    expect((seeded['counts'] as Array<{ label: string; n: number }>)[1]).toEqual({ label: 'gates', n: 0 })
  })

  it('carries the checks and sections through, null row values intact', () => {
    const shipped = mapShippedGraphs(shippedFixture as never)
    expect(shipped.checks).toHaveLength(3)
    expect(shipped.checks.every((c: { state: string }) => c.state === 'pass')).toBe(true)
    expect(shipped.sections.map((s: { title: string }) => s.title)).toEqual([
      'Roles', 'Proposer roles', 'Gates', 'Limits', 'Arms',
    ])
    const limits = shipped.sections.find((s: { title: string }) => s.title === 'Limits')!
    const nulls = (limits.rows as Array<{ k: string; v: string | null }>).filter((r) => r.v === null)
    expect(nulls.map((r) => r.k)).toEqual(['remind_after_hours', 'escalate_after_hours'])
  })
})
