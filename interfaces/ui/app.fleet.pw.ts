// The fleet screen (018 T008, rewritten T050; see app.helpers.ts).
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('fleet renders one v5 row per run', async ({ page }) => {  // clause: CONSOLE-1
  await expect(page.locator('[data-testid="fleet-view"]')).toBeVisible()
  // The v5 columns are present by name; rows render and the empty state
  // never shows while the provider reports runs.
  for (const name of ['Run', 'Graph', 'Arm', 'Outcome', 'Where', 'Revise', 'Cost', 'Elapsed']) {
    await expect(page.locator('.thead .col', { hasText: name }).first()).toBeVisible()
  }
  await expect(page.locator('[data-testid="fleet-row"]').first()).toBeVisible()
  await expect(page.locator('[data-testid="fleet-empty"]')).toHaveCount(0)
})

// 018 T049/T050 (S6): CONSOLE-3 (the fleet stage strip) is retired with its
// test — tombstoned in this file's app.md Retired list; the Observe canvas
// is the per-run stage spine (FR-601).

test('V10: arms read verbatim; an unpriced run never reads $0.00', async ({ page }) => {  // clause: CONSOLE-39
  const halted = page.locator('[data-testid="fleet-row"]', { hasText: 'Halted at the code node' })
  await expect(halted.locator('.col-arm')).toContainText('opencode')
  await expect(halted.locator('.col-arm')).toContainText('zai-coding-plan/glm-5.3')
  const unpriced = page.locator('[data-testid="fleet-row"]', { hasText: 'Self-serve onboarding' })
  await expect(unpriced.locator('.col-cost')).toHaveText('unpriced')
})

test('S16: rows offer Decide, Open run and Open', async ({ page }) => {  // clause: CONSOLE-53
  // A row waiting on a person offers Decide.
  const blocked = page.locator('[data-testid="fleet-row"]', { hasText: 'Add SSO to customer portal' })
  await expect(blocked.locator('[data-testid="fleet-open"]')).toHaveText('Decide')
  // Every other row offers Open.
  const done = page.locator('[data-testid="fleet-row"]', { hasText: 'Completed at two sinks' })
  await expect(done.locator('[data-testid="fleet-open"]')).toHaveText('Open')
  // Opening a run makes it the run in context; back on Fleet it offers
  // Open run.
  await done.locator('[data-testid="fleet-open"]').click()
  await expect(page).toHaveURL(/runs\/feature-multisink-demo/)
  await page.goBack()
  await expect(page.locator('[data-testid="fleet-view"]')).toBeVisible()
  await expect(
    page
      .locator('[data-testid="fleet-row"]', { hasText: 'Completed at two sinks' })
      .locator('[data-testid="fleet-open"]'),
  ).toHaveText('Open run')
})
