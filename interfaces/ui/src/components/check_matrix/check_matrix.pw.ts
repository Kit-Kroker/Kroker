import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-check_matrix-${profile}`

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('one header per column with name and ref; one row per harness', async ({ page }) => {  // clause: CHECK_MATRIX-1
  const board = page.locator(at('interfaces'))
  const cols = board.locator('[data-testid="matrix-column"]')
  await expect(cols).toHaveCount(6)
  await expect(cols.nth(0)).toContainText('Layers')
  await expect(cols.nth(1)).toContainText('policy/containment.yaml')
  await expect(board.locator('[data-testid="matrix-row"]')).toHaveCount(5)
})

test('cell marks carry the state; the not-measured cell shows its text', async ({ page }) => {  // clause: CHECK_MATRIX-3
  const board = page.locator(at('interfaces'))
  const claude = board.locator('[data-testid="matrix-row"]').first()
  await expect(claude.locator('[data-testid="matrix-cell"]').nth(0)).toHaveAttribute('data-state', 'yes')
  const opencode = board.locator('[data-testid="matrix-row"]').nth(1)
  await expect(opencode.locator('[data-testid="matrix-cell"]').nth(1)).toHaveAttribute('data-state', 'partial')
})

test('the planned row dims; facts carry severity', async ({ page }) => {  // clause: CHECK_MATRIX-4
  const board = page.locator(at('interfaces'))
  const planned = board.locator('[data-testid="matrix-row"].planned')
  await expect(planned).toHaveCount(1)
  await expect(planned).toContainText('pyai')
  const facts = board.locator('[data-testid="matrix-fact"]')
  await expect(facts).toHaveCount(2)
  await expect(facts.first()).toHaveAttribute('data-severity', 'warn')
  await expect(facts.nth(1)).toHaveAttribute('data-severity', 'error')
})
