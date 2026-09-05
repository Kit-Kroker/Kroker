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
