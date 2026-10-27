import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-app_header-${profile}`

test('renders the wordmark and the ordered nav, with no stats and no Start button', async ({ page }) => {  // clause: APP_HEADER-1
  await page.goto('/')
  const hdr = page.locator(`${at('with-inbox')} .cmp-app-header`)
  await expect(hdr.locator('.kmark')).toHaveText('K')
  await expect(hdr.locator('.name')).toHaveText('Kroker')
  // Primary then secondary, in order; unavailable items never render.
  const labels = await hdr.locator('[data-testid="nav-item"]').allInnerTexts()
  expect(labels.join('|')).toBe('Fleet|Inbox|Graphs')
  await expect(hdr.locator('.stats')).toHaveCount(0)
  await expect(hdr.locator('[data-testid="start-btn"]')).toHaveCount(0)
})

test('badge is omitted when the count is zero', async ({ page }) => {  // clause: APP_HEADER-1.1
  await page.goto('/')
  await expect(page.locator(`${at('zero-inbox')} [data-testid="inbox-count"]`)).toHaveCount(0)
  const withBadge = page.locator(`${at('with-inbox')} [data-testid="inbox-count"]`)
  await expect(withBadge).toHaveCount(1)
  await expect(withBadge).toHaveText('3')
})

test('the active run-switch tab carries the stable tab-active class', async ({ page }) => {  // clause: APP_HEADER-2
  await page.goto('/')
  const runSwitch = page.locator(`${at('run-switch')} [data-testid="run-switch"]`)
  const active = runSwitch.locator('.tab-active')
  await expect(active).toHaveCount(1)
  await expect(active).toHaveText(/run feature-1/)
})

test('the run switch renders with its mode segment, and Search and ⋯ are present', async ({ page }) => {  // clause: APP_HEADER-3
  await page.goto('/')
  const hdr = page.locator(`${at('run-switch')} .cmp-app-header`)
  await expect(hdr.locator('[data-testid="run-switch"]')).toHaveCount(1)
  await expect(hdr).toContainText('Observe')
  await expect(hdr).toContainText('Design')
  await expect(hdr.locator('[data-testid="header-search"]')).toHaveCount(1)
  await expect(hdr.locator('[data-testid="header-menu"]')).toHaveCount(1)
  // The sparse profile: no run switch, but the controls survive.
  const sparse = page.locator(`${at('sparse')} .cmp-app-header`)
  await expect(sparse.locator('[data-testid="run-switch"]')).toHaveCount(0)
  await expect(sparse.locator('[data-testid="header-search"]')).toHaveCount(1)
  await expect(sparse.locator('[data-testid="header-menu"]')).toHaveCount(1)
})
