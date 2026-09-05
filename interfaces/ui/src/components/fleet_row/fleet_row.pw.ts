import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-fleet_row-${profile}`

test('renders every supplied field in column order', async ({ page }) => {  // clause: FLEET_ROW-1
  await page.goto('/')
  const row = page.locator(`${at('typical')} [data-testid="fleet-row"]`)
  await expect(row).toBeVisible()
  await expect(row.locator('.cmp-fleet-row-id')).toHaveText('run-feat-auth')
  await expect(row.locator('.cmp-fleet-row-title-text')).toHaveText('Add oauth2 authentication provider')
  await expect(row.locator('.cmp-fleet-row-mode')).toHaveText('brownfield')
  await expect(row.locator('.cmp-fleet-row-status')).toContainText('running')
  await expect(row.locator('.cmp-fleet-row-cost')).toHaveText('$4.25')
  await expect(row.locator('.cmp-fleet-row-age')).toHaveText('14m')
})

test('renders null cost as an em dash', async ({ page }) => {  // clause: FLEET_ROW-1.1
  await page.goto('/')
  const cost = page.locator(`${at('null-cost')} .cmp-fleet-row-cost`)
  await expect(cost).toHaveText('—')
})

test('links the whole row to the supplied destination', async ({ page }) => {  // clause: FLEET_ROW-2
  await page.goto('/')
  const link = page.locator(`${at('typical')} a[data-testid="fleet-row"]`)
  await expect(link).toHaveAttribute('href', '/runs/run-feat-auth')
})

test('truncates a long title while keeping columns intact', async ({ page }) => {  // clause: FLEET_ROW-3
  await page.goto('/')
  const title = page.locator(`${at('crowded-trail')} .cmp-fleet-row-title-text`)
  const overflow = await title.evaluate((el) => getComputedStyle(el).textOverflow)
  expect(overflow).toBe('ellipsis')
})
