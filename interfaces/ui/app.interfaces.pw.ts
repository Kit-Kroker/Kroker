// The Interfaces screen at /interfaces (018 T080): the harness
// containment matrix and the adapter facts, over the mock replay of the
// recorded interfaces fixture.
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('the interfaces screen shows the matrix, the marks and the facts', async ({ page }) => {  // clause: CONSOLE-46
  await page.goto('/#/interfaces')
  await expect(page.locator('[data-testid="if-view"]')).toBeVisible()
  const rows = page.locator('[data-testid="matrix-row"]')
  await expect(rows).toHaveCount(5)
  // The marks: claude_code layers yes; opencode strict partial; the
  // planned pyai row dims.
  const claude = rows.nth(0).locator('[data-testid="matrix-cell"]').first()
  await expect(claude).toHaveAttribute('data-state', 'yes')
  const strict = rows.nth(1).locator('[data-testid="matrix-cell"]').nth(1)
  await expect(strict).toHaveAttribute('data-state', 'partial')
  await expect(page.locator('[data-testid="matrix-row"].planned')).toHaveCount(1)
  // The two facts carry their severities.
  const facts = page.locator('[data-testid="matrix-fact"]')
  await expect(facts).toHaveCount(2)
  await expect(facts.first()).toHaveAttribute('data-severity', 'warn')
  await expect(facts.nth(1)).toHaveAttribute('data-severity', 'error')
})

test('the nav item is live and navigates', async ({ page }) => {  // clause: CONSOLE-46
  const navInterfaces = page.getByTestId('nav-item').filter({ hasText: 'Interfaces' })
  await expect(navInterfaces).toBeVisible()
  await navInterfaces.click()
  await expect(page.locator('[data-testid="if-view"]')).toBeVisible()
})
