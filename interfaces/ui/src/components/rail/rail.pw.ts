import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-rail-${profile}`

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('the head renders title, state, rows and the budget with its bar', async ({ page }) => {  // clause: RAIL-1
  const rail = page.locator(`${at('run-halted')}`)
  await expect(rail.locator('[data-testid="rail-title"]')).toHaveText('feature-graph-demo')
  await expect(rail.locator('[data-testid="rail-state"]')).toHaveText('halted')
  await expect(rail.locator('[data-testid="rail-rows"] [data-testid="rail-row"]')).toHaveCount(3)
  await expect(rail.locator('[data-testid="rail-budget"]')).toContainText('$2.60')
  await expect(rail.locator('[data-testid="rail-budget"]')).toContainText('coding spend only')
  await expect(rail.locator('[data-testid="rail-budget-bar"]')).toHaveCount(1)
})

test('a null limit reads off and draws no bar', async ({ page }) => {  // clause: RAIL-1
  const rail = page.locator(`${at('no-budget')}`)
  await expect(rail.locator('[data-testid="rail-budget"]')).toContainText('off')
  await expect(rail.locator('[data-testid="rail-budget-bar"]')).toHaveCount(0)
})

test('the active tab section shows and the tabs render in order', async ({ page }) => {  // clause: RAIL-2
  const rail = page.locator(`${at('run-halted')}`)
  await expect(rail.locator('[data-testid="rail-tab"]')).toHaveCount(3)
  await expect(rail.locator('[data-testid="rail-tab"].is-active')).toHaveText('Path')
  await expect(rail.locator('.cmp-rail .section')).toContainText('The path through the graph')
  await expect(rail.locator('.cmp-rail .section')).not.toContainText('Every decision')
})

test('calls render as call-to-action buttons in order', async ({ page }) => {  // clause: RAIL-3
  const calls = page.locator(`${at('run-halted')} [data-testid="rail-call"]`)
  await expect(calls).toHaveCount(2)
  await expect(calls.nth(0)).toHaveText('Revise plan')
  await expect(calls.nth(1)).toHaveText('Halt run')
  await expect(page.locator(`${at('no-budget')} [data-testid="rail-call"]`)).toHaveCount(0)
})
