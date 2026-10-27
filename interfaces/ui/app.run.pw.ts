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

test('a legacy run shows the no-graph empty state and the strip', async ({ page }) => {  // clause: CONSOLE-6
  await page.goto('/#/runs/feature-add-sso')
  await expect(page.locator('[data-testid="run-graph-empty"]')).toBeVisible()
  await expect(page.locator('[data-testid="run-view"] [data-testid="stage-dot"]')).toHaveCount(18)
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

// --- The Cost tab (011 T010): the budget run is the seeded
// feature-graph-demo (blocked, three roles, one not-priced); the no-budget
// run is the closed feature-dark-mode. Both are non-running, so the mock
// ticker never moves their figures.

test('the Cost tab lists the roles, the total, and reopens from a copied URL', async ({ page }) => {  // clause: CONSOLE-24
  await page.goto('/#/runs/feature-graph-demo?tab=cost')
  const tab = page.locator('[data-testid="cost-tab"]')
  await expect(tab).toBeVisible()
  await expect(tab.locator('[data-testid="cost-row"]')).toHaveCount(3)
  const total = tab.locator('[data-testid="cost-total-price"]')
  await expect(total).toBeVisible()
  await expect(total).toContainText('2.60')
  // A copied URL reopens the tab (SC-005 for cost).
  await page.reload()
  await expect(page.locator('[data-testid="cost-tab"]')).toBeVisible()
})

test('the budget block counts the dollars, the share, the crossings and the scope', async ({ page }) => {  // clause: CONSOLE-26
  await page.goto('/#/runs/feature-graph-demo?tab=cost')
  const budget = page.locator('[data-testid="cost-tab"] [data-testid="cost-budget"]')
  await expect(budget).toContainText('20.00')
  await expect(budget).toContainText('40.00')
  const counted = page.locator('[data-testid="cost-budget-counted"]')
  await expect(counted).toContainText('counted toward budget')
  await expect(counted).toContainText('2.60')
  // Whole percent of the CURRENT limit (2.6 of 40 -> 6%), never cost/budget.
  await expect(page.locator('[data-testid="cost-budget-pct"]')).toHaveText(/^\d+%$/)
  await expect(page.locator('[data-testid="cost-budget-crossings"]')).toContainText('1')
  await expect(page.locator('[data-testid="cost-budget-note"]')).not.toBeEmpty()
  // A closed run without a budget says so and how one is set.
  await page.goto('/#/runs/feature-dark-mode?tab=cost')
  const none = page.locator('[data-testid="cost-tab"] [data-testid="cost-budget"]')
  await expect(none).toContainText('No budget')
  await expect(none).toContainText('start form')
})

test('a missing price reads "not priced" and no figure on the tab is $0.00', async ({ page }) => {  // clause: CONSOLE-25
  await page.goto('/#/runs/feature-graph-demo?tab=cost')
  // The unpriced dev role states the absence in words, never as dollars.
  const rowPrices = page.locator('[data-testid="cost-row-price"]')
  await expect(rowPrices.filter({ hasText: 'not priced' }).first()).toBeVisible()
  // The total says what it left out: partial.
  await expect(page.locator('[data-testid="cost-total-price"]')).toContainText('partial')
  // And nowhere on the tab does a figure read exactly $0.00 (FR-003).
  const priceEls = page.locator('[data-testid="cost-row-price"], [data-testid="cost-total-price"]')
  const count = await priceEls.count()
  expect(count).toBeGreaterThan(0)
  for (let i = 0; i < count; i++) {
    expect(await priceEls.nth(i).textContent()).not.toContain('$0.00')
  }
})
