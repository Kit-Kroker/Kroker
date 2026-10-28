import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-kanban-${profile}`

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('one column per entry with title and count, cards with id, tag and meta', async ({ page }) => {  // clause: KANBAN-1
  const board = page.locator(at('run-board'))
  const columns = board.locator('[data-testid="kanban-column"]')
  await expect(columns).toHaveCount(3)
  await expect(columns.nth(0)).toContainText('In progress')
  await expect(columns.nth(0)).toContainText('2')
  await expect(columns.nth(2)).toContainText('0')
  const cards = board.locator('[data-testid="kanban-card"]')
  await expect(cards).toHaveCount(3)
  await expect(cards.nth(0)).toContainText('task:T07#1')
  await expect(cards.nth(0)).toContainText('Fix the retry loop')
  await expect(cards.nth(0)).toContainText('fix attempts: 3')
})

test('the tag carries its wire-status kind as a class; a bare card never says undefined', async ({ page }) => {  // clause: KANBAN-2
  const board = page.locator(at('run-board'))
  await expect(board.locator('[data-testid="kanban-tag"]').first()).toHaveClass(/in_progress/)
  const bare = board.locator('[data-testid="kanban-card"]').nth(1)
  await expect(bare).toContainText('task:T09#1')
  await expect(bare).not.toContainText('undefined')
  const sparse = page.locator(at('sparse'))
  await expect(sparse.locator('[data-testid="kanban-tag"]').first()).toHaveClass(/quarantined/)
  await expect(sparse.locator('[data-testid="kanban-tag"]').nth(1)).toHaveClass(/failed/)
})

test('the link renders only when one is given', async ({ page }) => {  // clause: KANBAN-3
  await expect(page.locator(`${at('run-board')} [data-testid="kanban-link"]`)).toHaveCount(1)
  await expect(page.locator(`${at('run-board')} [data-testid="kanban-link"]`)).toHaveText('Open full Agent Board →')
  await expect(page.locator(`${at('sparse')} [data-testid="kanban-link"]`)).toHaveCount(0)
})
