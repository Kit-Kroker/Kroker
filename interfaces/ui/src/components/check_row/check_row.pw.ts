import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-check_row-${profile}`
const ground = (page: import('@playwright/test').Page, p: string) =>
  page.locator(`${at(p)} [data-testid="check-row"]`).evaluate((el) => getComputedStyle(el).backgroundColor)

test('only failing checks have a ground, and absolute differs from advisory', async ({ page }) => {  // clause: CHECK_ROW-2
  await page.goto('/')
  const abs = await ground(page, 'absolute-failing')
  const adv = await ground(page, 'advisory-failing')
  const ok = await ground(page, 'passing')
  expect(ok).toBe('rgba(0, 0, 0, 0)')
  expect(abs).not.toBe(ok)
  expect(adv).not.toBe(ok)
  expect(abs).not.toBe(adv)
})

test('marks are labelled', async ({ page }) => {  // clause: CHECK_ROW-3
  await page.goto('/')
  await expect(page.locator(`${at('passing')} .mark`)).toHaveAttribute('aria-label', 'passed')
  await expect(page.locator(`${at('absolute-failing')} .mark`)).toHaveAttribute('aria-label', 'failed')
})
