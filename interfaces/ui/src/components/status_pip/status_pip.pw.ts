import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-status_pip-${profile}`

test('each state carries its stable class', async ({ page }) => {  // clause: STATUS_PIP-1
  await page.goto('/')
  for (const kind of ['running', 'blocked', 'failed', 'done', 'pending', 'quarantined']) {
    await expect(page.locator(`${at(kind)} .cmp-status-pip`)).toHaveClass(new RegExp(`cmp-status-pip-${kind}`))
  }
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

test('pending and quarantined render as rings', async ({ page }) => {  // clause: STATUS_PIP-3
  await page.goto('/')
  for (const kind of ['pending', 'quarantined']) {
    const ring = await page.locator(`${at(kind)} .cmp-status-pip`).evaluate((el) => getComputedStyle(el).boxShadow)
    expect(ring).not.toBe('none')
  }
  const filled = await page.locator(`${at('done')} .cmp-status-pip`).evaluate((el) => getComputedStyle(el).boxShadow)
  expect(filled).toBe('none')
})
