import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-gate_decision-${profile}`

test('revise enables only once a comment is typed', async ({ page }) => {  // clause: GATE_DECISION-2
  await page.goto('/')
  const revise = page.locator(`${at('revise-needs-comment')} [data-testid="gate-revise"]`)
  await expect(revise).toBeDisabled()
  await expect(page.locator(`${at('revise-needs-comment')} [data-testid="gate-approve"]`)).toBeEnabled()
  await page.locator(`${at('revise-needs-comment')} [data-testid="gate-comment"]`).fill('tighten the plan')
  await expect(revise).toBeEnabled()
})

test('busy disables every control', async ({ page }) => {  // clause: GATE_DECISION-3
  await page.goto('/')
  for (const id of ['gate-approve', 'gate-revise', 'gate-reject', 'gate-comment']) {
    await expect(page.locator(`${at('busy')} [data-testid="${id}"]`)).toBeDisabled()
  }
})
