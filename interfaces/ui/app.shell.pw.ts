// The shell: header stats and the start form (018 T008, split from
// app.pw.ts; see app.helpers.ts).
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

// --- The v5 header (018 T010/T012): badge and nav. The stats strip is
// gone; totals live in the footer (CONSOLE-27/50 below).
test('the header shows the inbox badge with the pending count', async ({ page }) => {  // clause: CONSOLE-2
  const badge = page.locator('[data-testid="inbox-count"]')
  await expect(badge).toBeVisible()
  await expect(badge).toHaveText(/\d+/)
})

test('the header shows the primary and secondary nav, each navigating', async ({ page }) => {  // clause: CONSOLE-48
  // Slice 1: Compare and Interfaces are not yet available and do not
  // render; the run entry carries the newest seeded run's id.
  const tabs = page.locator('.cmp-app-header [data-testid="nav-item"]')
  await expect(tabs).toHaveCount(4)
  const labels = await tabs.allInnerTexts()
  expect(labels[0].trim()).toBe('Fleet')
  expect(labels[1].trim()).toBe('Inbox')
  expect(labels[2].trim()).toMatch(/feature-/)
  expect(labels[3].trim()).toBe('Graphs')
  await tabs.nth(2).click()
  await expect(page).toHaveURL(/\/#\/runs\/feature-/)
  await page.goto('/')
  await tabs.nth(3).click()
  await expect(page).toHaveURL(/\/#\/graphs/)
})

// --- The footer (018 T012): totals moved out of the header.
test('the footer total sums priced runs only and says how many it left out', async ({ page }) => {  // clause: CONSOLE-27
  const footer = page.locator('footer.cmp-footer-bar')
  await expect(footer).toBeVisible()
  // The mock seeds not-priced runs (011 T007): the total must name them,
  // never fold them in as zeros.
  await expect(footer.locator('span.side').first()).toContainText('not priced')
})

test('the footer shows context left and hints right on every screen', async ({ page }) => {  // clause: CONSOLE-50
  const footer = page.locator('footer.cmp-footer-bar')
  for (const route of ['/', '/#/inbox', '/#/graphs']) {
    await page.goto(route)
    await expect(footer).toBeVisible()
    await expect(footer.locator('span.side').first()).not.toBeEmpty()
    await expect(footer.locator('span.side').nth(1)).toHaveText('⌘K commands')
  }
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
