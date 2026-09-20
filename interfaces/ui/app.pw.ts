// The app tier (spec C §6): the net stretched over the pages that ship.
// Every other Playwright spec here asserts a profile in the showcase; this
// one drives the real SPA — the dashboard build served on 4174 by the
// second webServer in playwright.config.ts, with VITE_API=mock baked in at
// build time so the whole console runs headless with no backend.
//
// Canvas run-mode wiring (E75-OQ-1, 2026-09-20): the mock's demo run is the
// RECORDED default graph (12 nodes, 20 edges, 2 back loops, no traversals in
// the blocked projection), and its script is blocked -approve-> completed /
// -reject-> rejected. The editor flows paste the recorded pre_code scenario
// text (the demo run's graph has no recorded serialization — the mock's
// honest fallback is non-canonical JSON, which is not canvas-parseable).
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

test.use({ baseURL: 'http://localhost:4174' })

const PRE_CODE_YAML = (JSON.parse(readFileSync(fileURLToPath(new URL(
  '../dashboard/frontend/src/api/__fixtures__/graph/scenarios/pre_code.json',
  import.meta.url,
)), 'utf8')) as { yaml: string }).yaml

async function pasteRecordedGraph(page: import('@playwright/test').Page) {
  await page.goto('/#/graphs')
  await page.locator('[data-testid="tab-yaml"]').click()
  const text = page.locator('[data-testid="yaml-text"]')
  await text.fill(PRE_CODE_YAML)
  await page.locator('[data-testid="yaml-apply"]').click()
  await expect(page.locator('[data-testid="editor-state"]')).toHaveAttribute('data-state', 'graph_loaded')
  await page.locator('[data-testid="tab-canvas"]').click()
  // The paste flow mounts the canvas before the graph exists, so the initial
  // fit differs from the load-a-graph flow and later nodes can sit under the
  // right-hand inspector aside. Pan the empty bottom band of the pane left
  // (the graph occupies the top row) -- what a user would do.
  const pane = page.locator('[data-testid="graph-canvas"] .vue-flow__pane')
  const box = await pane.boundingBox()
  if (box) {
    await page.mouse.move(box.x + box.width * 0.7, box.y + box.height - 40)
    await page.mouse.down()
    await page.mouse.move(box.x + box.width * 0.25, box.y + box.height - 40, { steps: 6 })
    await page.mouse.up()
  }
}

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
  await page.goto('/#/graphs')
  await page.locator('[data-testid="tab-yaml"]').click()
  const text = page.locator('[data-testid="yaml-text"]')
  await text.fill(PRE_CODE_YAML)
  await expect(text).toHaveValue(/^schema_version: 1/)
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
  // The pasted scenario's parse associates its sha; the touched-field object
  // is its own recording, so the commit moves the sha.
  await pasteRecordedGraph(page)
  const sha = page.locator('[data-testid="editor-sha"]')
  await expect(sha).toHaveCount(1)
  const before = await sha.textContent()
  await page.locator('[data-testid="graph-node"][data-key="architecture"] .title').click()
  const inspector = page.locator('[data-testid="graph-inspector"]')
  await inspector.locator('[data-path="gate.policy"] select').selectOption('soft')
  await inspector.locator('[data-testid="inspector-apply"]').click()
  await expect(sha).toHaveCount(1)
  expect(await sha.textContent()).not.toBe(before)
  await expect(inspector.locator('[data-testid="field-error"]')).toHaveCount(0)
  await expect(inspector.locator('[data-testid="inspector-apply"]')).toBeDisabled()
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
