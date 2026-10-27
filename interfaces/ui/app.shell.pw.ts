// The shell: header stats and the start form (018 T008, split from
// app.pw.ts; see app.helpers.ts).
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

// --- The start form's budget (011 T016): the form lives in the shell
// (the header's Start button) and starts a run on the fleet.
test('the start form rejects a zero budget and starts a budgeted run', async ({ page }) => {  // clause: CONSOLE-28
  await page.goto('/')
  // The fleet must be rendered before its rows are counted (the provider
  // answers asynchronously; CONSOLE-1's first-row wait).
  await expect(page.locator('[data-testid="fleet-row"]').first()).toBeVisible()
  const before = await page.locator('[data-testid="fleet-row"]').count()
  await page.locator('[data-testid="start-btn"]').click()
  await expect(page.locator('[data-testid="modal-card"]')).toBeVisible()
  // Zero is refused with the omit-it message; nothing is added.
  await page.locator('[data-testid="start-budget-input"]').fill('0')
  await expect(page.locator('[data-testid="start-budget-error"]')).toContainText(
    'omit it to run without a budget',
  )
  await expect(page.locator('[data-testid="submit"]')).toBeDisabled()
  expect(await page.locator('[data-testid="fleet-row"]').count()).toBe(before)
  // A valid budget starts the run, and the new run's Cost tab shows it.
  await page.locator('[data-testid="start-title-input"]').fill('Budgeted demo')
  await page.locator('[data-testid="start-budget-input"]').fill('5')
  await page.locator('[data-testid="submit"]').click()
  await page.goto('/#/runs/feature-budgeted-demo?tab=cost')
  await expect(page.locator('[data-testid="cost-budget"]')).toContainText('5.00')
})
