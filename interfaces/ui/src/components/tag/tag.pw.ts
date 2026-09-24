import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-tag-${profile}`

test('tones and mono carry stable classes', async ({ page }) => {  // clause: TAG-1
  await page.goto('/')
  await expect(page.locator(`${at('neutral')} .cmp-tag`)).toHaveClass(/cmp-tag-neutral/)
  await expect(page.locator(`${at('strong')} .cmp-tag`)).toHaveClass(/cmp-tag-strong/)
  await expect(page.locator(`${at('mono')} .cmp-tag`)).toHaveClass(/is-mono/)
})
