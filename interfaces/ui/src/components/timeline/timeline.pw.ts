import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-timeline-${profile}`

test('one entry per item, marked by status', async ({ page }) => {  // clause: TIMELINE-1
  await page.goto('/')
  await expect(page.locator(`${at('task-history')} [data-testid="timeline-entry"]`)).toHaveCount(4)
  await expect(page.locator(`${at('task-history')} .cmp-status-pip`).first()).toHaveClass(/cmp-status-pip-done/)
})

test('empty history shows the empty slot', async ({ page }) => {  // clause: TIMELINE-4
  await page.goto('/')
  await expect(page.locator(`${at('empty')} [data-testid="timeline-entry"]`)).toHaveCount(0)
  await expect(page.locator(`${at('empty')} .cmp-timeline-empty`)).toHaveText('No transitions yet.')
})
