import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-node_palette-${profile}`

test('stages render before gates, one item per type', async ({ page }) => {  // clause: NODE_PALETTE-1
  await page.goto('/')
  const items = page.locator(`${at('seed')} [data-testid="palette-item"]`)
  await expect(items).toHaveCount(9)
  await expect(items.nth(0)).toHaveAttribute('data-type', 'architect')
  await expect(items.nth(8)).toHaveAttribute('data-type', 'gate.research')
  await expect(page.locator(`${at('empty')} [data-testid="palette-empty"]`)).toBeVisible()
})

test('items are draggable buttons', async ({ page }) => {  // clause: NODE_PALETTE-2
  await page.goto('/')
  await expect(page.locator(`${at('seed')} [data-type="gate.plan"]`)).toHaveAttribute('draggable', 'true')
})
