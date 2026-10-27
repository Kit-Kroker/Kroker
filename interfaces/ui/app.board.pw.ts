// The board tab of the run screen (018 T008, split from app.pw.ts; see
// app.helpers.ts).
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

// --- The board tab (002 group C): the four mock board runs carry the
// scenarios -- feature-graph-demo -> 'kroker' (populated), feature-add-sso
// -> null (no project), fix-board-ghost-project -> 'ghost-project' (404),
// feature-empty-board -> 'kroker-empty' (empty).

test('the board tab round-trips through ?tab', async ({ page }) => {  // clause: CONSOLE-10
  await page.goto('/#/runs/feature-graph-demo?tab=board')
  await expect(page.locator('[data-testid="board-tab"]')).toBeVisible()
  // A copied URL reopens on Board (SC-005).
  await page.reload()
  await expect(page.locator('[data-testid="board-tab"]')).toBeVisible()
  // Selecting Graph clears ?tab (replace semantics).
  await page.locator('[data-testid="tab-graph"]').click()
  await expect(page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')).toBeVisible()
  expect(page.url()).not.toContain('tab=')
  // Unknown and disabled values render Graph; the URL is left untouched.
  await page.goto('/#/runs/feature-graph-demo?tab=nonsense')
  await expect(page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')).toBeVisible()
  await expect(page.locator('[data-testid="board-tab"]')).toHaveCount(0)
  // 011 T009 (CONSOLE-10's disabled example moves to gates): Cost is live
  // through the #cost slot, so the disabled-value case is gates.
  await page.goto('/#/runs/feature-graph-demo?tab=gates')
  await expect(page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')).toBeVisible()
  await expect(page.locator('[data-testid="board-tab"]')).toHaveCount(0)
})

test('the board lists this run\'s tasks; a selection shows detail, evidence and timeline', async ({ page }) => {  // clause: CONSOLE-11
  await page.goto('/#/runs/feature-graph-demo?tab=board')
  const rows = page.locator('[data-testid="board-task-list"] [data-testid="list-row"]')
  await expect(rows).toHaveCount(7)
  await rows.filter({ hasText: 'T02' }).first().click()
  const detail = page.locator('[data-testid="board-detail"]')
  await expect(detail.locator('.title')).toHaveText('T02')
  await expect(detail.locator('[data-testid="detail-fields"] [data-testid="detail-value"]').first()).toBeVisible()
  await expect(detail.locator('.cmp-detail-section', { hasText: 'Evidence' })).toBeVisible()
  await expect(detail.locator('[data-testid="timeline-entry"]')).toHaveCount(3)
})

test("the board counter strip reads 'this run'", async ({ page }) => {  // clause: CONSOLE-12
  await page.goto('/#/runs/feature-graph-demo?tab=board')
  const strip = page.locator('[data-testid="board-counters"]')
  await expect(strip).toBeVisible()
  await expect(strip).toContainText('pending · this run')
  await expect(strip).toContainText('diverged · this run')
  await expect(strip.locator('.cmp-stat', { hasText: 'pending' }).locator('[data-testid="stat-value"]')).toHaveText('1')
  await expect(strip.locator('.cmp-stat', { hasText: 'diverged' }).locator('[data-testid="stat-value"]')).toHaveText('2')
})

test('a run without a project and a ghost project each degrade to their banner', async ({ page }) => {  // clause: CONSOLE-13
  await page.goto('/#/runs/feature-add-sso?tab=board')
  await expect(page.locator('[data-testid="board-banner-no-project"]')).toBeVisible()
  await expect(page.locator('[data-testid="run-view"]')).toBeVisible() // the rest of the page keeps working
  await page.goto('/#/runs/fix-board-ghost-project?tab=board')
  await expect(page.locator('[data-testid="board-banner-not-found"]')).toBeVisible()
})

test('a reachable project with zero tasks shows the explicit empty state', async ({ page }) => {  // clause: CONSOLE-14
  await page.goto('/#/runs/feature-empty-board?tab=board')
  await expect(page.locator('[data-testid="board-empty"]')).toBeVisible()
})

test('a healthy board never shows the connection-lost line', async ({ page }) => {  // clause: CONSOLE-15
  // Honest scope: the mock cannot fail on demand headless, so the positive
  // path (a real transient failure keeps data and shows the line) is pinned
  // at the unit tier, where board.store.test.ts and BoardTab.test.ts drive
  // real 500s through the store. This tier pins the healthy absence.
  await page.goto('/#/runs/feature-graph-demo?tab=board')
  await expect(page.locator('[data-testid="board-tab"]')).toBeVisible()
  await expect(page.locator('[data-testid="board-connection-lost"]')).toHaveCount(0)
})

test('Graph is unchanged after a Board round trip', async ({ page }) => {  // clause: CONSOLE-16
  await page.goto('/#/runs/feature-graph-demo')
  const canvas = page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')
  await expect(canvas.locator('[data-testid="graph-node"]')).toHaveCount(12)
  await page.locator('[data-testid="tab-board"]').click()
  await expect(page.locator('[data-testid="board-tab"]')).toBeVisible()
  await page.locator('[data-testid="tab-graph"]').click()
  await expect(canvas.locator('[data-testid="graph-node"]')).toHaveCount(12)
  // 018 T032: the run header's stage strip is gone (v5 draws none on the
  // run); the clause keeps its Graph-unchanged rule.
  await expect(page.locator('[data-testid="run-view"] [data-testid="stage-dot"]')).toHaveCount(0)
})
