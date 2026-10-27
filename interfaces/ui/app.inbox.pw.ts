// The decision inbox (018 T008, split from app.pw.ts; see app.helpers.ts).
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('the inbox lists every waiting item and links to its run', async ({ page }) => {  // clause: CONSOLE-17
  await page.goto('/#/inbox')
  const view = page.locator('[data-testid="inbox-view"]')
  // One entry per seeded item (FR-001), and the count equals the badge (FR-002).
  await expect(view.locator('[data-testid="inbox-entry"]')).toHaveCount(6)
  await expect(page.locator('[data-testid="inbox-count"]')).toHaveText('6')
  // Kind, run, age and title are shown (FR-003).
  const entry = view.locator(
    '[data-testid="inbox-entry"][data-run-id="feature-add-sso"][data-key="q1"]',
  )
  await expect(entry.locator('[data-testid="inbox-entry-kind"]')).not.toBeEmpty()
  await expect(entry.locator('[data-testid="inbox-entry-age"]')).not.toBeEmpty()
  await expect(entry.locator('[data-testid="inbox-entry-title"]')).not.toBeEmpty()
  // The run link opens that run's page.
  await entry.locator('[data-testid="inbox-entry-run"]').click()
  await expect(page.locator('[data-testid="run-view"]')).toBeVisible()
})

test('a clarify entry is answered by accepting or typing', async ({ page }) => {  // clause: CONSOLE-18
  await page.goto('/#/inbox')
  const view = page.locator('[data-testid="inbox-view"]')
  // One action accepts the suggestion (SC-003): the entry leaves, badge 6 -> 5.
  await view.locator(
    '[data-testid="inbox-entry"][data-run-id="feature-add-sso"][data-key="q1"] [data-testid="inbox-accept"]',
  ).click()
  await expect(view.locator('[data-testid="inbox-entry"][data-key="q1"]')).toHaveCount(0)
  await expect(page.locator('[data-testid="inbox-count"]')).toHaveText('5')
  // A typed answer: opening the field seeds the suggestion; a blank answer
  // cannot be sent; a filled one can. The entry leaves, badge 5 -> 4.
  const q2 = view.locator('[data-testid="inbox-entry"][data-key="q2"]')
  await q2.locator('[data-testid="inbox-edit"]').click()
  const field = q2.locator('[data-testid="field-control"]')
  await expect(q2.locator('[data-testid="inbox-send"]')).toBeEnabled()
  await field.fill('')
  await expect(q2.locator('[data-testid="inbox-send"]')).toBeDisabled()
  await field.fill('Ship the OIDC fallback first.')
  await q2.locator('[data-testid="inbox-send"]').click()
  await expect(view.locator('[data-testid="inbox-entry"][data-key="q2"]')).toHaveCount(0)
  await expect(page.locator('[data-testid="inbox-count"]')).toHaveText('4')
})

test('a gate entry is decided from the inbox', async ({ page }) => {  // clause: CONSOLE-19
  await page.goto('/#/inbox')
  const view = page.locator('[data-testid="inbox-view"]')
  // Revise is unavailable until a comment is entered (FR-005).
  const g2 = view.locator(
    '[data-testid="inbox-entry"][data-run-id="feature-usage-metering"][data-key="g2"]',
  )
  await expect(g2.locator('[data-testid="gate-revise"]')).toBeDisabled()
  await g2.locator('[data-testid="gate-comment"]').fill('Tighten the rollback story first.')
  await expect(g2.locator('[data-testid="gate-revise"]')).toBeEnabled()
  await g2.locator('[data-testid="gate-revise"]').click()
  await expect(view.locator('[data-testid="inbox-entry"][data-key="g2"]')).toHaveCount(0)
  await expect(page.locator('[data-testid="inbox-count"]')).toHaveText('5')
  // Reject sends at once.
  const graphGate = view.locator('[data-testid="inbox-entry"][data-run-id="feature-graph-demo"]')
  await graphGate.locator('[data-testid="gate-reject"]').click()
  await expect(
    view.locator('[data-testid="inbox-entry"][data-run-id="feature-graph-demo"]'),
  ).toHaveCount(0)
})

test('a gate decided in the inbox leaves the run canvas too', async ({ page }) => {  // clause: CONSOLE-23
  await page.goto('/#/inbox')
  const view = page.locator('[data-testid="inbox-view"]')
  const graphGate = view.locator('[data-testid="inbox-entry"][data-run-id="feature-graph-demo"]')
  await graphGate.locator('[data-testid="gate-approve"]').click()
  await expect(
    view.locator('[data-testid="inbox-entry"][data-run-id="feature-graph-demo"]'),
  ).toHaveCount(0)
  // The same gate is no longer offered on that run's canvas (FR-008).
  await page.goto('/#/runs/feature-graph-demo')
  await expect(page.locator('[data-testid="run-view"] [data-testid="gate-decision"]')).toHaveCount(0)
})

test('a merge override needs a justification and then resolves', async ({ page }) => {  // clause: CONSOLE-20
  await page.goto('/#/inbox')
  const view = page.locator('[data-testid="inbox-view"]')
  const entry = view.locator(
    '[data-testid="inbox-entry"][data-run-id="feature-billing-webhooks"][data-key="g1"]',
  )
  // Every check and the verdict are shown (FR-006).
  await expect(entry.locator('[data-testid="check-row"]')).toHaveCount(6)
  await expect(entry.locator('[data-testid="inbox-verdict"]')).not.toBeEmpty()
  // Override is unavailable until a justification is entered; send-back is not.
  await expect(entry.locator('[data-testid="inbox-override"]')).toBeDisabled()
  await expect(entry.locator('[data-testid="inbox-send-back"]')).toBeEnabled()
  await entry.locator('[data-testid="field-control"]').fill('Advisory only; the diff is reviewed.')
  await expect(entry.locator('[data-testid="inbox-override"]')).toBeEnabled()
  await entry.locator('[data-testid="inbox-override"]').click()
  await expect(view.locator('[data-testid="inbox-entry"][data-key="g1"]')).toHaveCount(0)
  await expect(page.locator('[data-testid="inbox-count"]')).toHaveText('5')
})

test('an escalation retry with guidance resolves the entry', async ({ page }) => {  // clause: CONSOLE-21
  await page.goto('/#/inbox')
  const view = page.locator('[data-testid="inbox-view"]')
  const entry = view.locator(
    '[data-testid="inbox-entry"][data-run-id="fix-rate-limit-retry"][data-key="e1"]',
  )
  await expect(entry.locator('[data-testid="inbox-analysis"]')).not.toBeEmpty()
  await entry.locator('[data-testid="field-control"]').fill('Check the token bucket constants.')
  await entry.locator('[data-testid="inbox-retry"]').click()
  await expect(view.locator('[data-testid="inbox-entry"][data-key="e1"]')).toHaveCount(0)
})

test('an escalation quarantine works without guidance', async ({ page }) => {  // clause: CONSOLE-21
  await page.goto('/#/inbox')
  const view = page.locator('[data-testid="inbox-view"]')
  const entry = view.locator(
    '[data-testid="inbox-entry"][data-run-id="fix-rate-limit-retry"][data-key="e1"]',
  )
  await expect(entry.locator('[data-testid="inbox-analysis"]')).not.toBeEmpty()
  await entry.locator('[data-testid="inbox-quarantine"]').click()
  await expect(view.locator('[data-testid="inbox-entry"][data-key="e1"]')).toHaveCount(0)
})

test('resolving every waiting item ends in the empty state and no badge', async ({ page }) => {  // clause: CONSOLE-22
  await page.goto('/#/inbox')
  const view = page.locator('[data-testid="inbox-view"]')
  const entries = view.locator('[data-testid="inbox-entry"]')
  const badge = page.locator('[data-testid="inbox-count"]')
  // SC-002: after every resolution, both the entry count and the header
  // badge drop by exactly one -- seven observations including the first.
  // The badge is asserted only down to 1: at zero it is omitted (that is
  // the end state this clause pins), not a zero-width "0".
  const observe = async (n: number) => {
    await expect(entries).toHaveCount(n)
    if (n > 0) await expect(badge).toHaveText(String(n))
  }
  await observe(6)
  // accept q1, accept q2 (CONSOLE-18's one-action accept)
  await view.locator(
    '[data-testid="inbox-entry"][data-run-id="feature-add-sso"][data-key="q1"] [data-testid="inbox-accept"]',
  ).click()
  await observe(5)
  await view.locator(
    '[data-testid="inbox-entry"][data-key="q2"] [data-testid="inbox-accept"]',
  ).click()
  await observe(4)
  // approve the usage-metering gate, then the graph-demo gate (CONSOLE-19)
  await view.locator(
    '[data-testid="inbox-entry"][data-run-id="feature-usage-metering"][data-key="g2"] [data-testid="gate-approve"]',
  ).click()
  await observe(3)
  await view.locator(
    '[data-testid="inbox-entry"][data-run-id="feature-graph-demo"] [data-testid="gate-approve"]',
  ).click()
  await observe(2)
  // override the merge gate with a justification (CONSOLE-20)
  const g1 = view.locator(
    '[data-testid="inbox-entry"][data-run-id="feature-billing-webhooks"][data-key="g1"]',
  )
  await g1.locator('[data-testid="field-control"]').fill('Advisory only; the diff is reviewed.')
  await g1.locator('[data-testid="inbox-override"]').click()
  await observe(1)
  // quarantine the escalation (CONSOLE-21)
  await view.locator(
    '[data-testid="inbox-entry"][data-run-id="fix-rate-limit-retry"][data-key="e1"] [data-testid="inbox-quarantine"]',
  ).click()
  // The end state: the explicit empty state shows, no entries, and the
  // badge is omitted at zero (the seventh observation).
  await expect(entries).toHaveCount(0)
  await expect(view.locator('[data-testid="inbox-empty"]')).toBeVisible()
  await expect(badge).toHaveCount(0)
})

// --- The inbox budget gate (011 T016). This test loads its OWN page
// (/?mockBudgetGate=1#/inbox, search before the hash) so the default
// six-item badge chains above stay intact.
test('the inbox budget gate entry says what approving grants', async ({ page }) => {  // clause: CONSOLE-29
  // The seventh (budget) item exists only behind the mock switch; this test
  // owns its page load so the badge chains of the other inbox tests are
  // untouched.
  await page.goto('/?mockBudgetGate=1#/inbox')
  await expect(page.locator('[data-testid="gate-budget-note"]')).toContainText(
    'Approve raises the limit to $60.00 and the run continues. Any other decision ends the run.',
  )
})
