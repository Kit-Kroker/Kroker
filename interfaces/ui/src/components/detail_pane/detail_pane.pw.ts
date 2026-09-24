import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-detail_pane-${profile}`

test('fields render in order with a dash for absent values', async ({ page }) => {  // clause: DETAIL_PANE-2
  await page.goto('/')
  const values = page.locator(`${at('task')} [data-testid="detail-value"]`)
  await expect(values).toHaveCount(5)
  await expect(values.last()).toHaveText('—')
})

test('no fields, no grid', async ({ page }) => {  // clause: DETAIL_PANE-4
  await page.goto('/')
  await expect(page.locator(`${at('title-only')} [data-testid="detail-fields"]`)).toHaveCount(0)
})
