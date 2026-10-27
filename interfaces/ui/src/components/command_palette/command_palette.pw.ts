import { test, expect } from '@playwright/test'

test('renders every command with label and hint, and filters by label', async ({ page }) => {  // clause: COMMAND_PALETTE-2
  await page.goto('/')
  const at = '#showcase-command_palette-open'
  const cmds = page.locator(`${at} [data-testid="palette-command"]`)
  await expect(cmds).toHaveCount(4)
  await expect(cmds.first()).toContainText('Review r1 — pending gate')
  await expect(cmds.first()).toContainText('waiting')
  await page.locator(`${at} [data-testid="palette-input"]`).fill('inbox')
  await expect(cmds).toHaveCount(1)
  await expect(cmds.first()).toContainText('Open Inbox')
})

test('keyboard drives the palette: arrows move the highlight and clamp at the ends', async ({ page }) => {  // clause: COMMAND_PALETTE-4
  await page.goto('/')
  const at = '#showcase-command_palette-open'
  const cmds = page.locator(`${at} [data-testid="palette-command"]`)
  const input = page.locator(`${at} [data-testid="palette-input"]`)
  await expect(cmds.first()).toHaveAttribute('aria-selected', 'true')
  // Clamps at the top: ArrowUp on the first keeps it highlighted.
  await input.press('ArrowUp')
  await expect(cmds.first()).toHaveAttribute('aria-selected', 'true')
  await input.press('ArrowDown')
  await input.press('ArrowDown')
  await expect(cmds.nth(2)).toHaveAttribute('aria-selected', 'true')
})

test('the closed palette renders nothing at all', async ({ page }) => {  // clause: COMMAND_PALETTE-1
  await page.goto('/')
  const at = '#showcase-command_palette-closed'
  await expect(page.locator(`${at} [data-testid="palette-backdrop"]`)).toHaveCount(0)
  await expect(page.locator(`${at} [data-testid="palette-command"]`)).toHaveCount(0)
})
