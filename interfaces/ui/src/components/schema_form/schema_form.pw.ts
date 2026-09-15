import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-schema_form-${profile}`

test('supported constructs render native controls; others a JSON snippet', async ({ page }) => {  // clause: SCHEMA_FORM-2
  await page.goto('/')
  const form = page.locator(at('object-with-defs'))
  await expect(form.locator('[data-path="settings.level"] select')).toHaveCount(1)
  await expect(form.locator('[data-path="settings.ratio"] input[type="number"]')).toHaveCount(1)
  await expect(form.locator('[data-path="settings.enabled"] input[type="checkbox"]')).toHaveCount(1)
  await expect(form.locator('[data-testid="schema-fallback"]')).toHaveCount(0)
  await expect(page.locator(`${at('unsupported-fallback')} [data-testid="schema-fallback"]`)).toHaveCount(1)
})

test('errors render beside their field and at the top', async ({ page }) => {  // clause: SCHEMA_FORM-5
  await page.goto('/')
  await expect(page.locator(`${at('with-errors')} [data-testid="form-error"]`)).toContainText('apply again')
  await expect(page.locator(`${at('with-errors')} [data-path="id"] [data-testid="field-error"]`)).toBeVisible()
})
