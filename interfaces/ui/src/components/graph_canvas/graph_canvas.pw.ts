import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-graph_canvas-${profile}`

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('renders one node per supplied node, keyed by key', async ({ page }) => {  // clause: GRAPH_CANVAS-1
  await expect(page.locator(`${at('edit-pre-code')} [data-testid="graph-node"]`)).toHaveCount(4)
  const dup = page.locator(`${at('edit-duplicate-ids')} [data-testid="graph-node"]`)
  await expect(dup).toHaveCount(2)
  await expect(dup.nth(0)).toHaveAttribute('data-key', 'intake')
  await expect(dup.nth(1)).toHaveAttribute('data-key', 'intake~2')
})

test('a backward edge renders curved with its stable class', async ({ page }) => {  // clause: GRAPH_CANVAS-2
  const backward = page.locator(`${at('run-looped')} .cmp-graph-edge-backward`)
  await expect(backward).toHaveCount(1)
  const d = await backward.locator('path').first().getAttribute('d')
  expect(d).toMatch(/^M [-\d.]+,[-\d.]+ C /)
  await expect(page.locator(`${at('run-looped')} .cmp-graph-edge:not(.cmp-graph-edge-backward)`)).toHaveCount(3)
})

test('an edge with a counter renders used/max as text', async ({ page }) => {  // clause: GRAPH_CANVAS-3
  await expect(page.locator(`${at('run-looped')} .vue-flow__edge-text`, { hasText: '2/3' })).toHaveCount(1)
})

test('a node status carries its stable class', async ({ page }) => {  // clause: GRAPH_CANVAS-4
  await expect(page.locator(`${at('run-mid-flight')} .cmp-graph-node-running`)).toHaveCount(1)
  await expect(page.locator(`${at('run-mid-flight')} .cmp-graph-node-done`)).toHaveCount(1)
  await expect(page.locator(`${at('run-gate-pending')} .cmp-graph-node-blocked`)).toHaveCount(1)
  await expect(page.locator(`${at('run-skipped-leg')} .cmp-graph-node-skipped`)).toHaveCount(2)
  await expect(page.locator(`${at('run-interrupted')} .cmp-graph-node-cancelled`)).toHaveCount(1)
  await expect(page.locator(`${at('run-mid-flight')} [data-testid="node-metrics"]`)).toContainText('$1.87')
})

test('run mode offers no connectable handle and no draggable node', async ({ page }) => {  // clause: GRAPH_CANVAS-5
  await expect(page.locator(`${at('run-mid-flight')} .vue-flow__handle.connectable`)).toHaveCount(0)
  await expect(page.locator(`${at('run-mid-flight')} .vue-flow__node.draggable`)).toHaveCount(0)
  await expect(page.locator(`${at('edit-pre-code')} .vue-flow__node.draggable`)).toHaveCount(4)
})

test('issue counts decorate nodes', async ({ page }) => {  // clause: GRAPH_CANVAS-1
  await expect(page.locator(`${at('edit-with-issues')} [data-testid="node-issues"]`)).toHaveText(['2'])
})

test('canvas colours resolve through tokens', async ({ page }) => {  // clause: GRAPH_CANVAS-7
  const stroke = await page.locator(`${at('edit-pre-code')} .vue-flow__edge-path`).first()
    .evaluate((el) => getComputedStyle(el).stroke)
  const token = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--line-strong').trim())
  expect(token).not.toBe('')
  expect(stroke).not.toBe('')
  const linked = await page.evaluate(() => [...document.styleSheets].some((s) => (s.href ?? '').includes('vue-flow')))
  expect(linked).toBe(false)
})

// --- 018 T022 (data-model §4.1): sinks and edge decorations ---------------
test('a lit sink renders its outcome and sub; an unlit sink the same texts without the lit class', async ({ page }) => {  // clause: GRAPH_CANVAS-10
  const failed = page.locator(`${at('sink-failed')} [data-testid="graph-node"][data-key="outcome"]`)
  await expect(failed).toBeVisible()
  await expect(failed.locator('[data-testid="sink-outcome"]')).toHaveText('failed')
  await expect(failed.locator('[data-testid="sink-sub"]')).toHaveText('failed:quarantined-tasks')
  await expect(page.locator(`${at('sink-failed')} .cmp-graph-sink-lit`)).toHaveCount(1)
  await expect(page.locator(`${at('sink-escalated')} [data-testid="sink-outcome"]`)).toHaveText('escalated')
  await expect(page.locator(`${at('sink-escalated')} .cmp-graph-sink-lit`)).toHaveCount(0)
})

test('edge payloads show under the toggle, and never without one', async ({ page }) => {  // clause: GRAPH_CANVAS-11
  await expect(page.locator(`${at('sink-failed')} [data-testid="edge-payload"]`)).toHaveText('plan.json')
  await expect(page.locator(`${at('run-looped')} [data-testid="edge-payload"]`)).toHaveCount(0)
})

test('an edge note renders on the revise loop', async ({ page }) => {  // clause: GRAPH_CANVAS-12
  await expect(page.locator(`${at('sink-failed')} [data-testid="edge-note"]`)).toHaveText('next revise escalates the run')
})

test('the grid prop toggles the dot-grid class on the canvas', async ({ page }) => {  // clause: GRAPH_CANVAS-13
  await expect(page.locator(`${at('sink-completed')} .cmp-graph-canvas--grid`)).toHaveCount(1)
  await expect(page.locator(`${at('run-mid-flight')} .cmp-graph-canvas--grid`)).toHaveCount(0)
})
