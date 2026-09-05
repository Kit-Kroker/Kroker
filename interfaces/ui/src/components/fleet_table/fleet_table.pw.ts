import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-fleet_table-${profile}`

test('renders one row per supplied run in order', async ({ page }) => {  // clause: FLEET_TABLE-1
  await page.goto('/')
  const rows = page.locator(`${at('populated')} [data-testid="fleet-row"]`)
  await expect(rows).toHaveCount(3)
  await expect(rows.nth(0)).toContainText('run-auth')
  await expect(rows.nth(1)).toContainText('run-blocked')
  await expect(rows.nth(2)).toContainText('run-done')
})

test('renders explicit empty state when rows empty', async ({ page }) => {  // clause: FLEET_TABLE-1.1
  await page.goto('/')
  const empty = page.locator(`${at('empty')} [data-testid="fleet-empty"]`)
  await expect(empty).toBeVisible()
  await expect(empty).toHaveText('No runs in fleet')
  const rows = page.locator(`${at('empty')} [data-testid="fleet-row"]`)
  await expect(rows).toHaveCount(0)
})
