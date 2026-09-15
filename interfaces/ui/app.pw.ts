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
