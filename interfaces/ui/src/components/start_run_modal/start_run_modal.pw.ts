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
