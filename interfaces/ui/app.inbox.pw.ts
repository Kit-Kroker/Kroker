// The decision inbox (018 T008, split from app.pw.ts; see app.helpers.ts).
// 018 T044: the v5 list-and-card rules — CONSOLE-17 to 23 and 29 restored on
// the new surfaces, CONSOLE-33 and 34 added (V4/V5).
import { test, expect, type Page } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

const view = (page: Page) => page.locator('[data-testid="inbox-view"]')

async function selectRow(page: Page, key: string) {
  // entryKey is a JSON pair, so the id part appears quoted inside data-key;
  // single-quote the CSS value so embedded double quotes are legal.
  await view(page).locator(`[data-testid="inbox-row"][data-key*='${key}']`).click()
  await expect(page.locator('[data-testid="inbox-card"]')).toBeVisible()
}

test.beforeEach(async ({ page }) => {
  await page.goto('/#/inbox')
})

test('the v5 list shows one row per item, the badge equals the count, and the card opens', async ({ page }) => {  // clause: CONSOLE-17
  await expect(view(page).locator('[data-testid="inbox-row"]')).toHaveCount(8)
  await expect(page.locator('[data-testid="inbox-count"]')).toHaveText('8')
  // Each row carries its kind, age, title and run.
  const q1 = view(page).locator('[data-testid="inbox-row"][data-key*="q1"]')
  await expect(q1).toContainText('clarify')
  await expect(q1).toContainText('Q1')
  await expect(q1).toContainText('feature-add-sso')
  // Selecting shows the card; the card's run reference opens that run.
  await selectRow(page, 'q1')
  await expect(page.locator('[data-testid="inbox-card"] [data-testid="card-title"]')).toContainText('Q1')
  await page.locator('[data-testid="card-run-link"]').click()
  await expect(page.locator('[data-testid="run-view"]')).toBeVisible()
})

test('a clarify card accepts the suggestion in one action or sends a non-blank answer', async ({ page }) => {  // clause: CONSOLE-18
  await selectRow(page, '"q1"')
  await page.locator('[data-testid="card-action"]', { hasText: 'Accept suggestion' }).click()
  await expect(view(page).locator('[data-testid="inbox-row"]')).toHaveCount(7)
  await expect(page.locator('[data-testid="inbox-count"]')).toHaveText('7')

  // q2: the answer is seeded with the suggestion (R-12); blank cannot send.
  await selectRow(page, '"q2"')
  const send = page.locator('[data-testid="card-action"]', { hasText: 'Send answer' })
  await expect(send).toBeEnabled()
  await page.locator('[data-testid="card-text"]').fill('')
  await expect(send).toBeDisabled()
  await page.locator('[data-testid="card-text"]').fill('Ship the OIDC fallback first.')
  await send.click()
  await expect(view(page).locator('[data-testid="inbox-row"]')).toHaveCount(6)
})

test('a gate card sends approve and reject at once; revise waits for a comment', async ({ page }) => {  // clause: CONSOLE-19
  await selectRow(page, '"g2"')
  const revise = page.locator('[data-testid="card-action"]', { hasText: 'Revise' })
  await expect(revise).toBeDisabled()
  await page.locator('[data-testid="card-text"]').fill('Tighten the rollback story first.')
  await expect(revise).toBeEnabled()
  await revise.click()
  await expect(view(page).locator('[data-testid="inbox-row"]')).toHaveCount(7)
  await selectRow(page, 'architecture')
  await page.locator('[data-testid="card-action"]', { hasText: 'Reject' }).click()
  await expect(view(page).locator('[data-testid="inbox-row"]')).toHaveCount(6)
})

test('a gate decided in the inbox is no longer offered in that run\'s rail', async ({ page }) => {  // clause: CONSOLE-23
  await selectRow(page, 'architecture')
  await page.locator('[data-testid="card-action"]', { hasText: 'Approve' }).click()
  await expect(view(page).locator('[data-testid="inbox-row"]')).toHaveCount(7)
  await page.goto('/#/runs/feature-graph-demo')
  await expect(page.locator('[data-testid="rail-call"]')).toHaveCount(0)
  await expect(page.locator('[data-testid="run-view"] [data-testid="pending-mark"]')).toHaveCount(0)
})

test('an override card shows the checks and verdict; override needs a justification', async ({ page }) => {  // clause: CONSOLE-20
  await selectRow(page, '"g1"')
  const pane = page.locator('[data-testid="inbox-card"]')
  await expect(pane.locator('[data-testid="card-field"]')).toHaveCount(7) // verdict + 6 checks
  await expect(pane).toContainText('MergeVerdict 0.91')
  const override = page.locator('[data-testid="card-action"]', { hasText: 'Override' })
  const sendBack = page.locator('[data-testid="card-action"]', { hasText: 'Send back' })
  await expect(override).toBeDisabled()
  await expect(sendBack).toBeEnabled()
  await page.locator('[data-testid="card-text"]').fill('Advisory only; the diff is reviewed.')
  await expect(override).toBeEnabled()
  await override.click()
  await expect(view(page).locator('[data-testid="inbox-row"]')).toHaveCount(7)
})

test('the task card sends exactly the chosen outcome; retry is never approve', async ({ page }) => {  // clause: CONSOLE-21
  await selectRow(page, '"e1"')
  const pane = page.locator('[data-testid="inbox-card"]')
  await expect(pane).toContainText('Analysis')
  const retry = page.locator('[data-testid="card-action"]', { hasText: 'retry' })
  await expect(retry).toBeDisabled()
  await page.locator('[data-testid="card-text"]').fill('Check the token bucket constants.')
  await expect(retry).toBeEnabled()
  // The reject consequence is stated before the action (V5, CONSOLE-34).
  await expect(pane.locator('[data-testid="action-title"]', { hasText: 'failed:quarantined-tasks' })).toBeVisible()
  await retry.click()
  await expect(view(page).locator('[data-testid="inbox-row"]')).toHaveCount(7)
})

test('the task card states the quarantine consequence before the action', async ({ page }) => {  // clause: CONSOLE-34
  await selectRow(page, '"e1"')
  const titles = page.locator('[data-testid="inbox-card"] [data-testid="action-title"]')
  await expect(titles.filter({ hasText: 'quarantine; the build ends failed:quarantined-tasks after the wave' })).toBeVisible()
})

test('the tool-approval card offers Approve and Deny only, with the timeout rule (V4)', async ({ page }) => {  // clause: CONSOLE-33
  await selectRow(page, 'tool')
  const pane = page.locator('[data-testid="inbox-card"]')
  const actions = pane.locator('[data-testid="card-action"]')
  await expect(actions).toHaveCount(2)
  await expect(actions.filter({ hasText: 'Approve' })).toBeVisible()
  await expect(actions.filter({ hasText: 'Deny' })).toBeVisible()
  const words = await pane.innerText()
  expect(words).not.toMatch(/halt/i)
  await expect(pane.locator('[data-testid="card-foot"]')).toHaveText('a timeout counts as not approved')
})

test('the budget card prices its consequences into the action titles (V6)', async ({ page }) => {  // clause: CONSOLE-29
  await selectRow(page, 'budget')
  const pane = page.locator('[data-testid="inbox-card"]')
  await expect(pane).toContainText('one more increment')
  await expect(pane).toContainText('rejected:budget')
})

test('resolving every waiting item ends in the empty state and no badge', async ({ page }) => {  // clause: CONSOLE-22
  const rows = view(page).locator('[data-testid="inbox-row"]')
  const badge = page.locator('[data-testid="inbox-count"]')
  const observe = async (n: number) => {
    await expect(rows).toHaveCount(n)
    if (n > 0) await expect(badge).toHaveText(String(n))
  }
  await observe(8)
  const act = async (key: string, label: string, text?: string) => {
    await selectRow(page, key)
    if (text) {
      await page.locator('[data-testid="card-text"]').fill(text)
    }
    await page.locator('[data-testid="card-action"]', { hasText: label }).click()
  }
  // q1 accept, q2 accept
  await act('"q1"', 'Accept suggestion')
  await observe(7)
  await act('"q2"', 'Accept suggestion')
  await observe(6)
  // g2 approve, the tool approval, the budget gate, the architecture gate
  await act('"g2"', 'Approve')
  await observe(5)
  await act('tool', 'Approve')
  await observe(4)
  await act('budget', 'Approve')
  await observe(3)
  await act('architecture', 'Approve')
  await observe(2)
  // override with a justification, quarantine the escalation
  await act('"g1"', 'Override', 'Advisory only; the diff is reviewed.')
  await observe(1)
  await act('"e1"', 'Quarantine')
  // The end state: the empty state, no rows, the badge omitted at zero.
  await expect(rows).toHaveCount(0)
  await expect(view(page).locator('[data-testid="inbox-empty"]')).toBeVisible()
  await expect(badge).toHaveCount(0)
})
