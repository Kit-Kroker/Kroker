import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-tab_bar-${profile}`

test('active tab carries tab-active', async ({ page }) => {  // clause: TAB_BAR-1
  await page.goto('/')
  await expect(page.locator(`${at('run')} [data-testid="tab-board"]`)).toHaveClass(/tab-active/)
  await expect(page.locator(`${at('run')} .tab-active`)).toHaveCount(1)
})

test('zero count renders no badge', async ({ page }) => {  // clause: TAB_BAR-3
  await page.goto('/')
  await expect(page.locator(`${at('run')} [data-testid="tab-gates"] [data-testid="tab-count"]`)).toHaveText('1')
  await expect(page.locator(`${at('run')} [data-testid="tab-cost"] [data-testid="tab-count"]`)).toHaveCount(0)
})
