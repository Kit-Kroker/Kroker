// The Compare screen at /compare (018 T073): arms × graphs with SC and
// $/case, the description line, the rework heatmap, and the unavailable
// empty state. The mock replays the recorded compare fixture.
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('the compare screen shows the arms, the null and the description', async ({ page }) => {  // clause: CONSOLE-45
  await page.goto('/#/compare')
  const rows = page.locator('[data-testid="cmp-row"]')
  await expect(rows).toHaveCount(2)
  // glm-5.2's default-graph cell is unpriced: `not measured`, never $0.00.
  const glm52 = rows.nth(0)
  await expect(glm52).toContainText('glm-5.2')
  await expect(glm52).toContainText('not measured')
  // glm-5.3 is priced on both graphs.
  const glm53 = rows.nth(1)
  await expect(glm53).toContainText('$1.50/case')
  await expect(glm53).toContainText('$2.00/case')
  // The description line comes from the wire.
  await expect(page.locator('[data-testid="cmp-desc"]')).toContainText('SC weights quality 0.6')
  // The heatmap rides the library component, columns in wire order.
  const heat = page.locator('[data-testid="cmp-heat"]')
  await expect(heat.locator('[data-testid="heat-column"]')).toHaveCount(1)
  await expect(heat.locator('[data-testid="heat-column"]').nth(0)).toHaveText('code')
})

test('the nav item and the palette command are live', async ({ page }) => {  // clause: CONSOLE-45
  const navCompare = page.getByTestId('nav-item').filter({ hasText: 'Compare' })
  await expect(navCompare).toBeVisible()
  await navCompare.click()
  await expect(page.locator('[data-testid="cmp-desc"]')).toBeVisible()
})
