import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-field-${profile}`

test('label click focuses the control', async ({ page }) => {  // clause: FIELD-1
  await page.goto('/')
  // The showcase also renders start_run_modal's open profiles, whose fixed
  // backdrop intercepts pointer events across the page. Remove those
  // articles so the label click is a real, unobstructed user click.
  await page
    .locator('#showcase-start_run_modal-open-filled, #showcase-start_run_modal-open-empty')
    .evaluateAll((els) => els.forEach((e) => e.remove()))
  await page.locator(`${at('with-hint')} label`).click()
  await expect(page.locator(`${at('with-hint')} [data-testid="field-control"]`)).toBeFocused()
})

test('error state is announced and replaces the hint', async ({ page }) => {  // clause: FIELD-2
  await page.goto('/')
  await expect(page.locator(`${at('error')} [data-testid="field-control"]`)).toHaveAttribute('aria-invalid', 'true')
  await expect(page.locator(`${at('error')} [role="alert"]`)).toHaveCount(1)
  await expect(page.locator(`${at('error')} [data-testid="field-hint"]`)).toHaveCount(0)
})
