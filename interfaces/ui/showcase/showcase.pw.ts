import { test, expect } from '@playwright/test'
import { REGISTRY } from './registry'

// RED until T010: button is not yet in showcase/registry.ts, and
// Showcase.vue does not yet render Profile.slots. The button's primary
// profile puts its call-to-action text in the default slot.
test('a profile text slot renders inside its stage', async ({ page }) => {  // clause: SHOWCASE-1
  await page.goto('/')
  const stage = page.locator('#showcase-button-primary .showcase-stage')
  await expect(stage).toContainText('Run this version')
})

// Chaos companion to the test above: SHOWCASE-1 must not pass vacuously
// forever. If no registered profile declared slots, the rendering test
// above would rot into an unfailing locator once button's DOM moved.
// RED until T010 registers button, whose primary profile carries slots.
test('at least one registered profile declares text slots (no vacuous slot support)', async ({ page }) => {  // clause: SHOWCASE-1
  await page.goto('/')
  expect(
    REGISTRY.some((set) => set.profiles.some((p) => p.slots && Object.keys(p.slots).length > 0)),
  ).toBe(true)
})
