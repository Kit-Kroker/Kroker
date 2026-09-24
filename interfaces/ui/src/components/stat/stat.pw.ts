import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-stat-${profile}`

test('zero and unknown values', async ({ page }) => {  // clause: STAT-3
  await page.goto('/')
  await expect(page.locator(`${at('zero')} [data-testid="stat-value"]`)).toHaveText('0')
  await expect(page.locator(`${at('unknown')} [data-testid="stat-value"]`)).toHaveText('—')
})

test('pip only where given', async ({ page }) => {  // clause: STAT-2
  await page.goto('/')
  await expect(page.locator(`${at('with-pip')} .cmp-status-pip`)).toHaveCount(1)
  await expect(page.locator(`${at('plain')} .cmp-status-pip`)).toHaveCount(0)
})
