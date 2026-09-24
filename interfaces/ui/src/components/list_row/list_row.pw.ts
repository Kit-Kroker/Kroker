import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-list_row-${profile}`

test('selected row is marked current', async ({ page }) => {  // clause: LIST_ROW-1
  await page.goto('/')
  await expect(page.locator(`${at('selected')} [data-testid="list-row"]`)).toHaveAttribute('aria-current', 'true')
  await expect(page.locator(`${at('plain')} [data-testid="list-row"]`)).not.toHaveAttribute('aria-current', 'true')
})

test('disabled row is inert', async ({ page }) => {  // clause: LIST_ROW-2
  await page.goto('/')
  await expect(page.locator(`${at('disabled')} [data-testid="list-row"]`)).toBeDisabled()
})
