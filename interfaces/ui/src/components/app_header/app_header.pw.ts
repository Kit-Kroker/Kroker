import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-app_header-${profile}`

test('renders brand, tabs, and supplied stats', async ({ page }) => {  // clause: APP_HEADER-1
  await page.goto('/')
  const hdr = page.locator(`${at('with-inbox')} .cmp-app-header`)
  await expect(hdr.locator('.mark')).toHaveText('SDLC·FACTORY')
  await expect(hdr.locator('.stats')).toContainText('runs 12/50')
  await expect(hdr.locator('.stats')).toContainText('spend today $145.20')
})

test('inbox badge is omitted when inbox count is zero', async ({ page }) => {  // clause: APP_HEADER-1.1
  await page.goto('/')
  const badge = page.locator(`${at('zero-inbox')} [data-testid="inbox-count"]`)
  await expect(badge).toHaveCount(0)

  const withInboxBadge = page.locator(`${at('with-inbox')} [data-testid="inbox-count"]`)
  await expect(withInboxBadge).toHaveCount(1)
  await expect(withInboxBadge).toHaveText('3')
})

test('active tab carries stable tab-active class', async ({ page }) => {  // clause: APP_HEADER-2
  await page.goto('/')
  const fleetTab = page.locator(`${at('with-inbox')} .tab`).first()
  await expect(fleetTab).toHaveClass(/tab-active/)

  const inboxTab = page.locator(`${at('inbox-active')} .tab`).nth(1)
  await expect(inboxTab).toHaveClass(/tab-active/)
})
