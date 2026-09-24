import { test, expect } from '@playwright/test'

// RED until T010: button is not yet in showcase/registry.ts, and
// Showcase.vue does not yet render Profile.slots. The button's primary
// profile puts its call-to-action text in the default slot.
test('a profile text slot renders inside its stage', async ({ page }) => {  // clause: SHOWCASE-1
  await page.goto('/')
  const stage = page.locator('#showcase-button-primary .showcase-stage')
  await expect(stage).toContainText('Run this version')
})
