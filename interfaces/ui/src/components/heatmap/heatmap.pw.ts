import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-heatmap-${profile}`

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('one column header per column in wire order, one row per arm', async ({ page }) => {  // clause: HEATMAP-1
  const board = page.locator(at('rework'))
  const cols = board.locator('[data-testid="heat-column"]')
  await expect(cols).toHaveCount(7)
  await expect(cols.nth(0)).toHaveText('research')
  await expect(cols.nth(4)).toHaveText('code')
  await expect(board.locator('[data-testid="heat-row"]')).toHaveCount(2)
})

test('a value cell shows its number; a blank cell is empty', async ({ page }) => {  // clause: HEATMAP-3
  const cells = page.locator(`${at('rework')} [data-testid="heat-cell"]`)
  await expect(cells.nth(0)).toContainText('0.12')
  // glm-5.3's architecture column is blank.
  const row1 = page.locator(`${at('rework')} [data-testid="heat-row"]`).first()
  await expect(row1.locator('[data-testid="heat-cell"]').nth(3)).toHaveText('')
})

test('low n carries the muted class and the scale rides token steps', async ({ page }) => {  // clause: HEATMAP-4
  const row1 = page.locator(`${at('rework')} [data-testid="heat-row"]`).first()
  await expect(row1.locator('[data-testid="heat-cell"]').nth(2)).toHaveClass(/low-n/)
  await expect(row1.locator('[data-testid="heat-cell"]').nth(4)).not.toHaveClass(/low-n/)
  // The token scale class, never a literal.
  await expect(row1.locator('[data-testid="heat-cell"]').nth(4)).toHaveClass(/heat-scale-/)
})
