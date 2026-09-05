import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-toasts-${profile}`

test('renders every supplied toast in order', async ({ page }) => {  // clause: TOASTS-1
  await page.goto('/')
  const toasts = page.locator(`${at('multiple')} [data-testid="toast"]`)
  await expect(toasts).toHaveCount(3)
  await expect(toasts.nth(0)).toHaveText('Run started — feature-123')
  await expect(toasts.nth(1)).toHaveText('Clarification resolved')
  await expect(toasts.nth(2)).toHaveText('Title required')
})

test('empty toasts list renders nothing at all', async ({ page }) => {  // clause: TOASTS-1.1
  await page.goto('/')
  const toasts = page.locator(`${at('empty')} [data-testid="toast"]`)
  await expect(toasts).toHaveCount(0)
})
