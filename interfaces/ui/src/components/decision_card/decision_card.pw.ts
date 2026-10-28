import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-decision_card-${profile}`

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('kicker, schema chip, title, where, fields and foot render', async ({ page }) => {  // clause: DECISION_CARD-1
  const card = page.locator(`${at('gate')}`)
  await expect(card.locator('[data-testid="card-kicker"]')).toHaveText('architecture r1')
  await expect(card.locator('[data-testid="card-schema"]')).toHaveText('gate')
  await expect(card.locator('[data-testid="card-title"]')).toHaveText('Approve the architecture')
  await expect(card.locator('[data-testid="card-where"]')).toContainText('node architecture')
  await expect(card.locator('[data-testid="card-field"]')).toHaveCount(2)
  await expect(card.locator('[data-testid="card-foot"]')).not.toBeEmpty()
})

test('the text area exists only with text; the gated action follows the input', async ({ page }) => {  // clause: DECISION_CARD-2
  await expect(page.locator(`${at('gate')} [data-testid="card-text"]`)).toHaveCount(0)
  const card = page.locator(`${at('clarify')}`)
  await expect(card.locator('[data-testid="card-text"]')).toBeVisible()
  await expect(card.locator('[data-testid="card-text"]')).toHaveAttribute('aria-label', 'Answer')
})

test('consequence titles render as visible text; needsText gates the button', async ({ page }) => {  // clause: DECISION_CARD-3
  const card = page.locator(`${at('clarify')}`)
  const titles = card.locator('[data-testid="action-title"]')
  await expect(titles.filter({ hasText: 'send the suggested answer' })).toBeVisible()
  await expect(titles.filter({ hasText: 'send the typed answer' })).toBeVisible()
  const gated = card.locator('[data-testid="card-action"]', { hasText: 'Send answer' })
  await expect(gated).toBeDisabled()
  await card.locator('[data-testid="card-text"]').fill('use Auth0')
  await expect(gated).toBeEnabled()
})
