import { test, expect } from '@playwright/test'

test('renders each item with label and description, and checks only what is on', async ({ page }) => {  // clause: TOGGLE_MENU-1
  await page.goto('/')
  const at = '#showcase-toggle_menu-session'
  const rows = page.locator(`${at} [data-testid="toggle-item"]`)
  await expect(rows).toHaveCount(4)
  await expect(rows.first()).toContainText('Payloads')
  await expect(rows.first()).toContainText('show edge payloads on the canvas')
  await expect(rows.nth(1).locator('[data-testid="toggle-check"]')).toHaveCount(1)
  await expect(rows.nth(2).locator('[data-testid="toggle-check"]')).toHaveCount(0)
})

test('an all-off menu shows no checks anywhere', async ({ page }) => {  // clause: TOGGLE_MENU-2
  await page.goto('/')
  const at = '#showcase-toggle_menu-all-off'
  await expect(page.locator(`${at} [data-testid="toggle-item"]`)).toHaveCount(2)
  await expect(page.locator(`${at} [data-testid="toggle-check"]`)).toHaveCount(0)
})
