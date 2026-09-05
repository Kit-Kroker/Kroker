import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-stage_dots-${profile}`

test('each state carries its stable class', async ({ page }) => {  // clause: STAGE_DOTS-2
  await page.goto('/')
  const marks = page.locator(`${at('every-state')} [data-testid="stage-dot"]`)
  await expect(marks).toHaveCount(6)
  for (const state of ['pending', 'active', 'done', 'blocked', 'failed', 'skipped']) {
    await expect(page.locator(`${at('every-state')} .cmp-stage-dot-${state}`)).toHaveCount(1)
  }
})

test('only active and blocked animate', async ({ page }) => {  // clause: STAGE_DOTS-3
  await page.goto('/')
  const animated = async (sel: string) =>
    page.locator(sel).evaluate((el) => getComputedStyle(el).animationName)
  // Asserts that an animation resolves, never which colour or duration.
  expect(await animated(`${at('every-state')} .cmp-stage-dot-active`)).not.toBe('none')
  expect(await animated(`${at('every-state')} .cmp-stage-dot-blocked`)).not.toBe('none')
  expect(await animated(`${at('every-state')} .cmp-stage-dot-done`)).toBe('none')
})

test('an unresolved pipeline renders no marks', async ({ page }) => {  // clause: STAGE_DOTS-1.1
  await page.goto('/')
  await expect(page.locator(`${at('empty')} [data-testid="stage-dot"]`)).toHaveCount(0)
})
