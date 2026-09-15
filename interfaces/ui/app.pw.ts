// The app tier (spec C §6): the net stretched over the pages that ship.
// Every other Playwright spec here asserts a profile in the showcase; this
// one drives the real SPA — the dashboard build served on 4174 by the
// second webServer in playwright.config.ts, with VITE_API=mock baked in at
// build time so the whole console runs headless with no backend.
import { test, expect } from '@playwright/test'

test.use({ baseURL: 'http://localhost:4174' })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('the fleet view renders rows from the provider', async ({ page }) => {  // clause: CONSOLE-1
  await expect(page.locator('[data-testid="fleet-view"]')).toBeVisible()
  // The mock seeds a fleet; rows must render and the empty state must not.
  await expect(page.locator('[data-testid="fleet-row"]').first()).toBeVisible()
  await expect(page.locator('[data-testid="fleet-empty"]')).toHaveCount(0)
})

test('the header renders stats and the inbox badge', async ({ page }) => {  // clause: CONSOLE-2
  const stats = page.locator('.cmp-app-header .stats')
  await expect(stats).toContainText('runs')
  await expect(stats).toContainText('spend today')
  await expect(stats.locator('b').first()).toHaveText(/\d/)
  // The badge is absent at zero (APP_HEADER-1.1); the mock seeds inbox
  // items, so the assembled console must show it.
  const badge = page.locator('[data-testid="inbox-count"]')
  await expect(badge).toBeVisible()
  await expect(badge).toHaveText(/\d+/)
})

test('the fleet strip renders one mark per served canonical stage', async ({ page }) => {  // clause: CONSOLE-3
  const firstRow = page.locator('[data-testid="fleet-row"]').first()
  await expect(firstRow.locator('[data-testid="stage-dot"]')).toHaveCount(18)
  await expect(firstRow.locator('[data-testid="stage-dot"]').nth(4)).toHaveAttribute('title', /^research · /)
})

test('the editor renders recorded text and holds shape errors with the canvas disabled', async ({ page }) => {  // clause: CONSOLE-7
  await page.goto('/#/graphs?from=run:feature-graph-demo')
  await expect(page.locator('[data-testid="editor-state"]')).toHaveAttribute('data-state', 'graph_loaded')
  await page.locator('[data-testid="tab-yaml"]').click()
  const text = page.locator('[data-testid="yaml-text"]')
  await expect(text).toHaveValue(/^schema_version: 1/)
  // Re-applying the served canonical text is a recorded parse: canvas back.
  await text.fill(await text.inputValue())
  await page.locator('[data-testid="yaml-apply"]').click()
  await page.locator('[data-testid="tab-canvas"]').click()
  await expect(page.locator('[data-testid="graph-editor-view"] [data-testid="graph-node"]')).toHaveCount(8)
  // Text that does not parse: errors with a line, canvas disabled.
  await page.locator('[data-testid="tab-yaml"]').click()
  await text.fill('schema_version: 1\nnodes: [\n')
  await page.locator('[data-testid="yaml-apply"]').click()
  await expect(page.locator('[data-testid="editor-state"]')).toHaveAttribute('data-state', 'text_broken')
  await expect(page.locator('[data-testid="yaml-error"]').first()).toContainText('line 3')
  await page.locator('[data-testid="tab-canvas"]').click()
  await expect(page.locator('[data-testid="canvas-disabled"]')).toBeVisible()
  await expect(page.locator('[data-testid="graph-editor-view"] [data-testid="graph-canvas"]')).toHaveCount(0)
})

test('an inspector edit applies through the parse and commits', async ({ page }) => {  // clause: CONSOLE-9
  // Recorded flow (E-76 spec §7.2): a fully positioned graph, no drag before
  // apply, one touched field -- exactly objects/pre_code_architecture_soft.
  await page.goto('/#/graphs?from=run:feature-graph-demo')
  await expect(page.locator('[data-testid="editor-sha"]')).toHaveCount(0)
  await page.locator('[data-testid="graph-node"][data-key="architecture"] .title').click()
  const inspector = page.locator('[data-testid="graph-inspector"]')
  await inspector.locator('[data-path="gate.policy"] select').selectOption('soft')
  await inspector.locator('[data-testid="inspector-apply"]').click()
  await expect(page.locator('[data-testid="editor-sha"]')).toHaveCount(1)
  await expect(inspector.locator('[data-testid="field-error"]')).toHaveCount(0)
  await expect(inspector.locator('[data-testid="inspector-apply"]')).toBeDisabled()
})

test('a graph run renders its nodes, a loop counter and a curved backward edge', async ({ page }) => {  // clause: CONSOLE-4
  await page.goto('/#/runs/feature-graph-demo')
  const canvas = page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')
  await expect(canvas.locator('[data-testid="graph-node"]')).toHaveCount(8)
  await expect(canvas.locator('.vue-flow__edge-text', { hasText: '1/2' })).toHaveCount(1)
  await expect(canvas.locator('.cmp-graph-edge-backward')).toHaveCount(3)
  await expect(canvas.locator('.cmp-graph-node-blocked')).toHaveCount(1)
})

test('run-state re-renders never drop the canvas edges', async ({ page }) => {  // clause: GRAPH_CANVAS-9
  // Regression (2026-09-14): RunView's elapsed clock re-renders every second;
  // replacing vue-flow's element arrays on each tick dropped every edge.
  await page.clock.install()
  await page.goto('/#/runs/feature-graph-demo')
  const canvas = page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(11)
  // Fire RunView's 1 s clock deterministically -- no sleep, no flake budget.
  await page.clock.runFor(5000)
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(11)
  await expect(canvas.locator('.vue-flow__edge-text', { hasText: '1/2' })).toHaveCount(1)
})

test('deciding the pending gate from the canvas clears it', async ({ page }) => {  // clause: CONSOLE-5
  await page.goto('/#/runs/feature-graph-demo')
  const gate = page.locator('[data-testid="run-view"] [data-testid="gate-decision"]')
  await expect(gate).toHaveCount(1)
  await gate.locator('[data-testid="gate-approve"]').click()
  await expect(gate).toHaveCount(0)
  await expect(page.locator('[data-testid="run-view"] .cmp-graph-node-running')).toHaveCount(1)
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
  await expect(page.locator('[data-testid="graph-editor-view"] [data-testid="graph-node"]')).toHaveCount(8)
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
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(11)
  const before = await metrics.textContent()
  await page.clock.runFor(70_000)
  const after = await metrics.textContent()
  expect(after).not.toBe(before)  // the clock really ticks
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(11)
  await expect(canvas.locator('.vue-flow__edge-text', { hasText: '1/2' })).toHaveCount(1)
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
