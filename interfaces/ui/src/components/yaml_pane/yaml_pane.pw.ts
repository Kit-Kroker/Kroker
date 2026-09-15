import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-yaml_pane-${profile}`

test('shape errors render with their locations', async ({ page }) => {  // clause: YAML_PANE-2
  await page.goto('/')
  const rows = page.locator(`${at('shape-errors')} [data-testid="yaml-error"]`)
  await expect(rows).toHaveCount(2)
  await expect(rows.nth(0)).toContainText('line 3:1')
  await expect(rows.nth(1)).toContainText('nodes[0].id')
})

test('over-cap text cannot be applied', async ({ page }) => {  // clause: YAML_PANE-4
  await page.goto('/')
  await expect(page.locator(`${at('too-large')} [data-testid="yaml-too-large"]`)).toBeVisible()
  await expect(page.locator(`${at('too-large')} [data-testid="yaml-apply"]`)).toBeDisabled()
  await expect(page.locator(`${at('dirty')} [data-testid="yaml-apply"]`)).toBeEnabled()
})
