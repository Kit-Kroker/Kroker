import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-status_tag-${profile}`

test('each tag carries its kind and a matching pip', async ({ page }) => {  // clause: STATUS_TAG-1
  await page.goto('/')
  for (const [profile, kind] of [['done', 'done'], ['failed', 'failed'], ['in-progress', 'in_progress']]) {
    await expect(page.locator(`${at(profile)} .cmp-status-tag`)).toHaveClass(new RegExp(`cmp-status-tag-${kind}`))
    await expect(page.locator(`${at(profile)} .cmp-status-pip`)).toHaveClass(new RegExp(`cmp-status-pip-${kind}`))
  }
})

test('default wording and mono treatment', async ({ page }) => {  // clause: STATUS_TAG-2
  await page.goto('/')
  await expect(page.locator(`${at('in-progress')} .label`)).toHaveText('In progress')
  await expect(page.locator(`${at('mono-waiting')} .cmp-status-tag`)).toHaveClass(/is-mono/)
})
