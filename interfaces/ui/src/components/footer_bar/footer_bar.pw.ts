import { test, expect } from '@playwright/test'

test('renders the left and right texts', async ({ page }) => {  // clause: FOOTER_BAR-1
  await page.goto('/')
  const bar = page.locator('#showcase-footer_bar-fleet-total .cmp-footer-bar')
  await expect(bar).toContainText('$145.20 · 2 not priced')
  await expect(bar).toContainText('⌘K commands')
})
