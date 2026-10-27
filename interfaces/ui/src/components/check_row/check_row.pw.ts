import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-check_row-${profile}`
const row = (page: import('@playwright/test').Page, p: string) =>
  page.locator(`${at(p)} [data-testid="check-row"]`)
const ground = (page: import('@playwright/test').Page, p: string) =>
  row(page, p).evaluate((el) => getComputedStyle(el).backgroundColor)

test('only failing checks have a ground, and absolute differs from advisory', async ({ page }) => {  // clause: CHECK_ROW-2
  await page.goto('/')
  // The ground rides on .is-failing classes (018 R-10: no colour literal).
  const passingClass = await row(page, 'passing').evaluate((el) => el.className)
  expect(passingClass).not.toContain('is-failing')
  const abs = await ground(page, 'absolute-failing')
  const adv = await ground(page, 'advisory-failing')
  const ok = await ground(page, 'passing')
  expect(abs).not.toBe(ok)
  expect(adv).not.toBe(ok)
  expect(abs).not.toBe(adv)
})

test('marks are labelled', async ({ page }) => {  // clause: CHECK_ROW-3
  await page.goto('/')
  await expect(page.locator(`${at('passing')} .mark`)).toHaveAttribute('aria-label', 'passed')
  await expect(page.locator(`${at('absolute-failing')} .mark`)).toHaveAttribute('aria-label', 'failed')
})
