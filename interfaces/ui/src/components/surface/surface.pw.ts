import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-surface-${profile}`

test('only the overlay casts a shadow', async ({ page }) => {  // clause: SURFACE-1
  await page.goto('/')
  const shadow = (sel: string) => page.locator(sel).evaluate((el) => getComputedStyle(el).boxShadow)
  expect(await shadow(`${at('overlay')} .cmp-surface`)).not.toBe('none')
  expect(await shadow(`${at('card')} .cmp-surface`)).toBe('none')
})

test('overlay renders as a list', async ({ page }) => {  // clause: SURFACE-2
  await page.goto('/')
  await expect(page.locator(`${at('overlay')} ul.cmp-surface`)).toHaveCount(1)
})
