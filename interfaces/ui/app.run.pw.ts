// The run detail screen and its tabs: the canvas, the board's sibling tabs
// and the Cost tab (018 T008, split from app.pw.ts; see app.helpers.ts).
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('a graph run renders its nodes and its curved backward edges', async ({ page }) => {  // clause: CONSOLE-4
  await page.goto('/#/runs/feature-graph-demo')
  const canvas = page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')
  // The recorded default graph: 12 nodes, the 2 revise loops curved. The
  // blocked projection carries no traversals, so no counter renders here --
  // the counter feature stays pinned by GRAPH_CANVAS-3 (showcase) and the
  // adapter rows over the escalated recording.
  await expect(canvas.locator('[data-testid="graph-node"]')).toHaveCount(12)
  await expect(canvas.locator('.cmp-graph-edge-backward')).toHaveCount(2)
  await expect(canvas.locator('.cmp-graph-node-blocked')).toHaveCount(1)
  await expect(canvas.locator('.cmp-graph-node-skipped')).toHaveCount(1)
})

test('run-state re-renders never drop the canvas edges', async ({ page }) => {  // clause: GRAPH_CANVAS-9
  // Regression (2026-09-14): RunView's elapsed clock re-renders every second;
  // replacing vue-flow's element arrays on each tick dropped every edge.
  await page.clock.install()
  await page.goto('/#/runs/feature-graph-demo')
  const canvas = page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(20)
  // Fire RunView's 1 s clock deterministically -- no sleep, no flake budget.
  await page.clock.runFor(5000)
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(20)
  await expect(canvas.locator('.cmp-graph-node-blocked')).toHaveCount(1)
})

test('deciding the pending gate from the canvas clears it', async ({ page }) => {  // clause: CONSOLE-5
  await page.goto('/#/runs/feature-graph-demo')
  const gate = page.locator('[data-testid="run-view"] [data-testid="gate-decision"]')
  await expect(gate).toHaveCount(1)
  await gate.locator('[data-testid="gate-approve"]').click()
  await expect(gate).toHaveCount(0)
  // The recorded completed projection: the gate resolves, every node of the
  // run's graph is done except the skipped context leg.
  await expect(page.locator('[data-testid="run-view"] .cmp-graph-node-done')).toHaveCount(11)
  await expect(page.locator('[data-testid="run-view"] .cmp-graph-node-skipped')).toHaveCount(1)
})

test('a legacy run shows the no-graph empty state and no canvas', async ({ page }) => {  // clause: CONSOLE-6
  await page.goto('/#/runs/feature-add-sso')
  await expect(page.locator('[data-testid="run-graph-empty"]')).toBeVisible()
  // 018 T032: the run header's stage strip is gone (v5 draws none on the
  // run); the clause keeps its no-graph-empty rule.
  await expect(page.locator('[data-testid="run-view"] [data-testid="stage-dot"]')).toHaveCount(0)
  await expect(page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')).toHaveCount(0)
})

test('the run view offers no edit affordance and opens a copy in the editor', async ({ page }) => {  // clause: CONSOLE-8
  await page.goto('/#/runs/feature-graph-demo')
  const view = page.locator('[data-testid="run-view"]')
  await expect(view.locator('.vue-flow__node.draggable')).toHaveCount(0)
  await expect(view.locator('.vue-flow__handle.connectable')).toHaveCount(0)
  await expect(view.locator('[data-testid="node-palette"]')).toHaveCount(0)
  await view.locator('[data-testid="open-copy"]').click()
  await expect(page.locator('[data-testid="graph-editor-view"]')).toBeVisible()
  await expect(page.locator('[data-testid="editor-state"]')).toHaveAttribute('data-state', 'graph_loaded')
  await expect(page.locator('[data-testid="graph-editor-view"] [data-testid="graph-node"]')).toHaveCount(12)
  await expect(page.locator('[data-testid="editor-sha"]')).toHaveCount(0)
})

test('the elapsed clock flows while the canvas structure survives a minute of ticks', async ({ page }) => {  // clause: GRAPH_CANVAS-9
  // Positive control for the regression above: a fix that silenced the clock
  // would also keep the edges. 70 fired seconds must move the minute-grain
  // elapsed readout AND leave every edge in place.
  await page.clock.install()
  await page.goto('/#/runs/feature-graph-demo')
  const canvas = page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')
  const metrics = canvas.locator('[data-key="architecture"] [data-testid="node-metrics"]')
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(20)
  const before = await metrics.textContent()
  await page.clock.runFor(70_000)
  const after = await metrics.textContent()
  expect(after).not.toBe(before)  // the clock really ticks
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(20)
  await expect(canvas.locator('.cmp-graph-node-blocked')).toHaveCount(1)
})

test('a gate decision shows its busy window before the state clears it', async ({ page }) => {  // clause: CONSOLE-5
  await page.goto('/#/runs/feature-graph-demo')
  const gate = page.locator('[data-testid="run-view"] [data-testid="gate-decision"]')
  await expect(gate).toHaveCount(1)
  await gate.locator('[data-testid="gate-approve"]').click()
  // In flight: the controls lock at once, so a rapid second submit cannot fire.
  await expect(gate.locator('[data-testid="gate-approve"]')).toBeDisabled()
  await expect(gate).toHaveCount(0)  // then the next state clears the whole control
})

// --- The Cost tab is retired (018 T032, S3): the CONSOLE-24/25/26 tests
// were deleted with the CostTab they drove (their cases were ported to
// costRail.adapter.test.ts in T027); T033 restores the clauses on the
// rail's Cost section. The budget run remains the seeded
// feature-graph-demo; the no-budget run feature-dark-mode.
