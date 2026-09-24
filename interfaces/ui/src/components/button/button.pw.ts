import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-button-${profile}`

test('each variant carries its stable class', async ({ page }) => {  // clause: BUTTON-1
  await page.goto('/')
  for (const v of ['primary', 'secondary', 'ghost', 'danger']) {
    await expect(page.locator(`${at(v)} .cmp-button`)).toHaveClass(new RegExp(`cmp-button-${v}`))
  }
  await expect(page.locator(`${at('small')} .cmp-button`)).toHaveClass(/cmp-button-sm/)
})

test('disabled and busy render locked', async ({ page }) => {  // clause: BUTTON-2
  await page.goto('/')
  await expect(page.locator(`${at('disabled')} .cmp-button`)).toBeDisabled()
  await expect(page.locator(`${at('busy')} .cmp-button`)).toBeDisabled()
  await expect(page.locator(`${at('busy')} .cmp-button`)).toHaveAttribute('aria-busy', 'true')
})
