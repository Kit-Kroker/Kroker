// The shell: header stats and the start form (018 T008, split from
// app.pw.ts; see app.helpers.ts).
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

// --- The v5 header (018 T010/T012): badge and nav. The stats strip is
// gone; totals live in the footer (CONSOLE-27/50 below).
test('the header shows the inbox badge with the pending count', async ({ page }) => {  // clause: CONSOLE-2
  const badge = page.locator('[data-testid="inbox-count"]')
  await expect(badge).toBeVisible()
  await expect(badge).toHaveText(/\d+/)
})

test('the header shows the primary and secondary nav, each navigating', async ({ page }) => {  // clause: CONSOLE-48
  // Slice 7 (T079): every v5 entry is live - six items. The run entry
  // carries the newest seeded run's id and lands with the fleet state -
  // wait for it by name, never by count (a count can be satisfied
  // before it arrives).
  const tabs = page.locator('.cmp-app-header [data-testid="nav-item"]')
  const runTab = tabs.filter({ hasText: /feature-/ })
  await expect(runTab).toBeVisible()
  await expect(tabs).toHaveCount(6)
  const labels = await tabs.allInnerTexts()
  expect(labels[0].trim()).toBe('Fleet')
  expect(labels[1].trim()).toBe('Inbox')
  expect(labels[2].trim()).toMatch(/feature-/)
  expect(labels[3].trim()).toBe('Graphs')
  expect(labels[4].trim()).toBe('Compare')
  expect(labels[5].trim()).toBe('Interfaces')
  await runTab.click()
  await expect(page).toHaveURL(/\/#\/runs\/feature-/)
  await page.goto('/')
  await expect(runTab).toBeVisible()
  await tabs.nth(3).click()
  await expect(page).toHaveURL(/\/#\/graphs/)
  await page.goto('/')
  await expect(runTab).toBeVisible()
  await tabs.nth(4).click()
  await expect(page).toHaveURL(/\/#\/compare/)
  await page.goto('/')
  await expect(runTab).toBeVisible()
  await tabs.nth(5).click()
  await expect(page).toHaveURL(/\/#\/interfaces/)
})

// --- The footer (018 T012): totals moved out of the header.
test('the footer total sums priced runs only and says how many it left out', async ({ page }) => {  // clause: CONSOLE-27
  const footer = page.locator('footer.cmp-footer-bar')
  await expect(footer).toBeVisible()
  // The mock seeds not-priced runs (011 T007): the total must name them,
  // never fold them in as zeros.
  await expect(footer.locator('span.side').first()).toContainText('not priced')
})

test('the footer shows context left and hints right on every screen', async ({ page }) => {  // clause: CONSOLE-50
  const footer = page.locator('footer.cmp-footer-bar')
  for (const route of ['/', '/#/inbox', '/#/graphs']) {
    await page.goto(route)
    await expect(footer).toBeVisible()
    await expect(footer.locator('span.side').first()).not.toBeEmpty()
    await expect(footer.locator('span.side').nth(1)).toHaveText('⌘K commands')
  }
})

// --- The v5 palette and session menu (018 T019): ⌘K opens the palette,
// ⋯ opens the session toggles. The components' own contracts are pinned
// at the library tier (COMMAND_PALETTE-*, TOGGLE_MENU-*); this tier pins
// the shell wiring.
test('Ctrl+K opens the palette, filtering runs the chosen command', async ({ page }) => {  // clause: CONSOLE-47
  await page.keyboard.press('Control+k')
  const input = page.locator('[data-testid="palette-input"]')
  await expect(input).toBeVisible()
  await input.fill('inbox')
  await expect(page.locator('[data-testid="palette-command"]')).toHaveCount(1)
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#\/inbox/)
  // 018 T080: every command is available - the compare and interfaces
  // commands run too.
  await page.keyboard.press('Control+k')
  await input.fill('compare')
  await expect(page.locator('[data-testid="palette-command"]')).toHaveCount(1)
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#\/compare/)
  await page.keyboard.press('Control+k')
  await input.fill('interfaces')
  await expect(page.locator('[data-testid="palette-command"]')).toHaveCount(1)
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#\/interfaces/)
})

test('the ⋯ menu light theme switches data-theme on the document', async ({ page }) => {  // clause: CONSOLE-47
  await expect(page.locator('html')).not.toHaveAttribute('data-theme', 'light')
  await page.locator('[data-testid="header-menu"]').click()
  await page.locator('[data-testid="toggle-item"]', { hasText: 'Light theme' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
})

// --- 018 T065 (R-1 ends): the CONSOLE-28 test ('the start form rejects a
// zero budget and starts a budgeted run') is deleted — it opened the form
// via the header's start-btn, removed with T065. T066 restores it in this
// phase, opened from Design's "Run this version", with the budget shown in
// the rail. The clause reads untested mid-phase; SG-5 checks at phase end.
