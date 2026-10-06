import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-start_run_modal-${profile}`

test('submit button is enabled when form is filled', async ({ page }) => {  // clause: START_RUN_MODAL-1
  await page.goto('/')
  const btn = page.locator(`${at('open-filled')} [data-testid="submit"]`)
  await expect(btn).toBeVisible()
  await expect(btn).toBeEnabled()
})

test('submit button is disabled when title is empty', async ({ page }) => {  // clause: START_RUN_MODAL-1.1
  await page.goto('/')
  const btn = page.locator(`${at('open-empty')} [data-testid="submit"]`)
  await expect(btn).toBeVisible()
  await expect(btn).toBeDisabled()
})

test('modal is not rendered when open is false', async ({ page }) => {  // clause: START_RUN_MODAL-2
  await page.goto('/')
  const modal = page.locator(`${at('closed')} [data-testid="modal-card"]`)
  await expect(modal).toHaveCount(0)
})

test('a zero budget shows the omit-it message and blocks the submit', async ({ page }) => {  // clause: START_RUN_MODAL-3
  // Profile 'with-budget-error' (initialTitle valid, initialBudget '0') —
  // added by the executor together with the component change (011 T014).
  await page.goto('/')
  const modal = page.locator(`${at('with-budget-error')}`)
  const error = modal.locator('[data-testid="start-budget-error"]')
  await expect(error).toContainText('omit it to run without a budget')
  await expect(modal.locator('[data-testid="submit"]')).toBeDisabled()
})
