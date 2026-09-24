import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-filter_chip-${profile}`

test('selected chip is pressed', async ({ page }) => {  // clause: FILTER_CHIP-1
  await page.goto('/')
  await expect(page.locator(`${at('selected')} [data-testid="filter-chip"]`)).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator(`${at('unselected')} [data-testid="filter-chip"]`)).toHaveAttribute('aria-pressed', 'false')
})

test('zero count renders', async ({ page }) => {  // clause: FILTER_CHIP-3
  await page.goto('/')
  await expect(page.locator(`${at('zero')} .count`)).toHaveText('0')
  await expect(page.locator(`${at('disabled')} .count`)).toHaveCount(0)
})
