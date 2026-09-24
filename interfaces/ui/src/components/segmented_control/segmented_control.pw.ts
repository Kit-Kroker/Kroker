import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-segmented_control-${profile}`

test('selection moves with a click', async ({ page }) => {  // clause: SEGMENTED_CONTROL-1
  await page.goto('/')
  const design = page.locator(`${at('mode')} [data-testid="segment-design"]`)
  await expect(design).toHaveAttribute('aria-checked', 'false')
  await expect(page.locator(`${at('mode')} [data-testid="segment-observe"]`)).toHaveClass(/is-selected/)
})

test('counts render, zero included', async ({ page }) => {  // clause: SEGMENTED_CONTROL-3
  await page.goto('/')
  await expect(page.locator(`${at('with-counts')} .count`)).toHaveCount(3)
  await expect(page.locator(`${at('mode')} .count`)).toHaveCount(0)
})
