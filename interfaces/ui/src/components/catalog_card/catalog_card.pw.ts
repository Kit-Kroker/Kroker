import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-catalog_card-${profile}`

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('kicker, name, mono sha, description, when and count chips render', async ({ page }) => {  // clause: CATALOG_CARD-1
  const card = page.locator(at('shipped'))
  await expect(card.locator('[data-testid="catalog-kicker"]')).toHaveText('shipped graph')
  await expect(card.locator('[data-testid="catalog-name"]')).toHaveText('default')
  await expect(card.locator('[data-testid="catalog-sha"]')).toContainText('a021c25b')
  await expect(card.locator('[data-testid="catalog-sha"]')).toHaveClass(/mono/)
  await expect(card.locator('[data-testid="catalog-description"]')).toHaveText('The pre-code pipeline as shipped.')
  await expect(card.locator('[data-testid="catalog-when"]')).toHaveText('2026-09-20')
  const chips = card.locator('[data-testid="catalog-count"]')
  await expect(chips).toHaveCount(3)
  await expect(chips.nth(0)).toContainText('nodes')
  await expect(chips.nth(0)).toContainText('12')
})

test('null description or when reads not measured; a zero count still shows', async ({ page }) => {  // clause: CATALOG_CARD-2
  const card = page.locator(at('unmeasured'))
  await expect(card.locator('[data-testid="catalog-description"]')).toHaveText('not measured')
  await expect(card.locator('[data-testid="catalog-when"]')).toContainText('not measured')
  await expect(card.locator('[data-testid="catalog-count"]', { hasText: 'gates' })).toContainText('0')
})

test('the action button carries the action label', async ({ page }) => {  // clause: CATALOG_CARD-3
  await expect(page.locator(`${at('shipped')} [data-testid="catalog-action"]`)).toHaveText('Open in Design')
})
