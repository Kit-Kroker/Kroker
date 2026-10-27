// The shell: header stats and the start form (018 T008, split from
// app.pw.ts; see app.helpers.ts).
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('the header renders stats and the inbox badge', async ({ page }) => {  // clause: CONSOLE-2
  const stats = page.locator('.cmp-app-header .stats')
  await expect(stats).toContainText('runs')
  // 011 T008: the label is `spend` (the sum was never windowed by day).
  await expect(stats).toContainText('spend')
  await expect(stats.locator('b').first()).toHaveText(/\d/)
  // The badge is absent at zero (APP_HEADER-1.1); the mock seeds inbox
  // items, so the assembled console must show it.
  const badge = page.locator('[data-testid="inbox-count"]')
  await expect(badge).toBeVisible()
  await expect(badge).toHaveText(/\d+/)
})

test('the header spend states how many runs it left out', async ({ page }) => {  // clause: CONSOLE-27
  await page.goto('/')
  const stats = page.locator('.cmp-app-header .stats')
  // The spend figure names the excluded runs ("N not priced") rather than
  // summing them in as zeros; the dollar sum itself is ticker-fed on running
  // seeds, so only the exclusion wording is pinned here.
  await expect(stats).toContainText('not priced')
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
