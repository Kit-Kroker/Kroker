import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-issue_list-${profile}`

test('issues render in order with severity classes', async ({ page }) => {  // clause: ISSUE_LIST-1
  await page.goto('/')
  const rows = page.locator(`${at('mixed')} [data-testid="issue"]`)
  await expect(rows).toHaveCount(3)
  await expect(rows.nth(0)).toHaveClass(/cmp-issue-error/)
  await expect(rows.nth(2)).toHaveClass(/cmp-issue-warning/)
  const notExecutable = page.locator(`${at('with-not-executable')} [data-testid="issue"]`)
  await expect(notExecutable).toHaveCount(2)
  await expect(notExecutable.nth(1)).toHaveClass(/cmp-issue-not_executable/)
  await expect(page.locator(`${at('none')} [data-testid="issues-none"]`)).toBeVisible()
})

test('a graph-level issue offers no focus control', async ({ page }) => {  // clause: ISSUE_LIST-2
  await page.goto('/')
  const rows = page.locator(`${at('mixed')} [data-testid="issue"]`)
  await expect(rows.nth(0).locator('button')).toHaveCount(1)
  await expect(rows.nth(2).locator('button')).toHaveCount(0)
})
