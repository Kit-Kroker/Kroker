// The decision inbox (018 T008, split from app.pw.ts; see app.helpers.ts).
//
// 018 T041: the CONSOLE-17 to 22, 23 and 29 tests were deleted with the
// entry components they drove (inbox-entry, inbox-accept, gate-revise,
// check-row, inbox-override, inbox-analysis, inbox-quarantine,
// gate-budget-note, gate-decision, gate-approve). T044 restores the
// clauses' tests on the v5 list and card.
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

test('the v5 inbox loads its list surface', async ({ page }) => {  // clause: CONSOLE-2
  // A keep-alive so this file keeps exercising the route: the inbox badge
  // is CONSOLE-2's own clause (app.shell.pw.ts owns its assertion); the
  // list rules return with T044.
  await page.goto('/#/inbox')
  await expect(page.locator('[data-testid="inbox-view"]')).toBeVisible()
  await expect(page.locator('[data-testid="inbox-count"]')).toHaveText('6')
})
