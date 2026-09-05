import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-status_pip-${profile}`

test('each state carries its stable class', async ({ page }) => {  // clause: STATUS_PIP-1
  await page.goto('/')
  const running = page.locator(`${at('running')} .cmp-status-pip`)
  await expect(running).toHaveClass(/cmp-status-pip-running/)

  const blocked = page.locator(`${at('blocked')} .cmp-status-pip`)
  await expect(blocked).toHaveClass(/cmp-status-pip-blocked/)

  const failed = page.locator(`${at('failed')} .cmp-status-pip`)
  await expect(failed).toHaveClass(/cmp-status-pip-failed/)

  const done = page.locator(`${at('done')} .cmp-status-pip`)
  await expect(done).toHaveClass(/cmp-status-pip-done/)
})

test('only running and blocked pulse when active', async ({ page }) => {  // clause: STATUS_PIP-2
  await page.goto('/')
  const animated = async (sel: string) =>
    page.locator(sel).evaluate((el) => getComputedStyle(el).animationName)

  expect(await animated(`${at('running')} .cmp-status-pip`)).not.toBe('none')
  expect(await animated(`${at('blocked')} .cmp-status-pip`)).not.toBe('none')
  expect(await animated(`${at('failed')} .cmp-status-pip`)).toBe('none')
  expect(await animated(`${at('done')} .cmp-status-pip`)).toBe('none')
})
