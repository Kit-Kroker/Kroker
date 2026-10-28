// The fleet screen (018 T008, split from app.pw.ts; see app.helpers.ts).
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('the fleet view renders rows from the provider', async ({ page }) => {  // clause: CONSOLE-1
  await expect(page.locator('[data-testid="fleet-view"]')).toBeVisible()
  // The mock seeds a fleet; rows must render and the empty state must not.
  await expect(page.locator('[data-testid="fleet-row"]').first()).toBeVisible()
  await expect(page.locator('[data-testid="fleet-empty"]')).toHaveCount(0)
})

// 018 T049 (S6): the CONSOLE-3 test ('the fleet strip renders one mark per
// served canonical stage') is deleted with the stage strip; T050 tombstones
// the clause. The Observe canvas is the per-run stage spine (FR-601).
