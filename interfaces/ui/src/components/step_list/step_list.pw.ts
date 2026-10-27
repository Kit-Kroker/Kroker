import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-step_list-${profile}`

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('one row per step with name, ref and a status-carrying pip', async ({ page }) => {  // clause: STEP_LIST-1
  const rows = page.locator(`${at('inner-loop')} [data-testid="step-row"]`)
  await expect(rows).toHaveCount(4)
  await expect(rows.nth(0)).toContainText('read plan')
  await expect(rows.nth(0)).toContainText('plan@sha1')
  await expect(rows.nth(3)).toContainText('failed:quarantined-tasks')
  await expect(rows.nth(0).locator('[data-testid="step-pip"]')).toHaveClass(/done/)
  await expect(rows.nth(1).locator('[data-testid="step-pip"]')).toHaveClass(/running/)
  await expect(rows.nth(3).locator('[data-testid="step-pip"]')).toHaveClass(/failed/)
})

test('no interactive control anywhere in the list', async ({ page }) => {  // clause: STEP_LIST-2
  const list = page.locator(`${at('inner-loop')}`)
  await expect(list.locator('button, a, input, select, textarea')).toHaveCount(0)
  await expect(page.locator(`${at('single-done')} [data-testid="step-row"]`)).toHaveCount(1)
})
