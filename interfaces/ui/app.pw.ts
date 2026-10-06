// The app tier (spec C §6): the net stretched over the pages that ship.
// Every other Playwright spec here asserts a profile in the showcase; this
// one drives the real SPA — the dashboard build served on 4174 by the
// second webServer in playwright.config.ts, with VITE_API=mock baked in at
// build time so the whole console runs headless with no backend.
//
// Canvas run-mode wiring (E75-OQ-1, 2026-09-20): the mock's demo run is the
// RECORDED default graph (12 nodes, 20 edges, 2 back loops, no traversals in
// the blocked projection), and its script is blocked -approve-> completed /
// -reject-> rejected. The editor flows paste the recorded pre_code scenario
// text (the demo run's graph has no recorded serialization — the mock's
// honest fallback is non-canonical JSON, which is not canvas-parseable).
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

test.use({ baseURL: 'http://localhost:4174' })

const PRE_CODE_YAML = (JSON.parse(readFileSync(fileURLToPath(new URL(
  '../dashboard/frontend/src/api/__fixtures__/graph/scenarios/pre_code.json',
  import.meta.url,
)), 'utf8')) as { yaml: string }).yaml

async function pasteRecordedGraph(page: import('@playwright/test').Page) {
  await page.goto('/#/graphs')
  await page.locator('[data-testid="tab-yaml"]').click()
  const text = page.locator('[data-testid="yaml-text"]')
  await text.fill(PRE_CODE_YAML)
  await page.locator('[data-testid="yaml-apply"]').click()
  await expect(page.locator('[data-testid="editor-state"]')).toHaveAttribute('data-state', 'graph_loaded')
  await page.locator('[data-testid="tab-canvas"]').click()
  // The paste flow mounts the canvas before the graph exists, so the initial
  // fit differs from the load-a-graph flow and later nodes can sit under the
  // right-hand inspector aside. Pan the empty bottom band of the pane left
  // (the graph occupies the top row) -- what a user would do.
  const pane = page.locator('[data-testid="graph-canvas"] .vue-flow__pane')
  const box = await pane.boundingBox()
  if (box) {
    await page.mouse.move(box.x + box.width * 0.7, box.y + box.height - 40)
    await page.mouse.down()
    await page.mouse.move(box.x + box.width * 0.25, box.y + box.height - 40, { steps: 6 })
    await page.mouse.up()
  }
}

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('the fleet view renders rows from the provider', async ({ page }) => {  // clause: CONSOLE-1
  await expect(page.locator('[data-testid="fleet-view"]')).toBeVisible()
  // The mock seeds a fleet; rows must render and the empty state must not.
  await expect(page.locator('[data-testid="fleet-row"]').first()).toBeVisible()
  await expect(page.locator('[data-testid="fleet-empty"]')).toHaveCount(0)
})

test('the header renders stats and the inbox badge', async ({ page }) => {  // clause: CONSOLE-2
  const stats = page.locator('.cmp-app-header .stats')
  await expect(stats).toContainText('runs')
  // 011 T008: the label is `spend` (the sum was never windowed by day).
  await expect(stats).toContainText('spend')
  await expect(stats.locator('b').first()).toHaveText(/\d/)
  // The badge is absent at zero (APP_HEADER-1.1); the mock seeds inbox
  // items, so the assembled console must show it.
  const badge = page.locator('[data-testid="inbox-count"]')
  await expect(badge).toBeVisible()
  await expect(badge).toHaveText(/\d+/)
})

test('the fleet strip renders one mark per served canonical stage', async ({ page }) => {  // clause: CONSOLE-3
  const firstRow = page.locator('[data-testid="fleet-row"]').first()
  await expect(firstRow.locator('[data-testid="stage-dot"]')).toHaveCount(18)
  await expect(firstRow.locator('[data-testid="stage-dot"]').nth(4)).toHaveAttribute('title', /^research · /)
})

test('the editor renders recorded text and holds shape errors with the canvas disabled', async ({ page }) => {  // clause: CONSOLE-7
  await page.goto('/#/graphs')
  await page.locator('[data-testid="tab-yaml"]').click()
  const text = page.locator('[data-testid="yaml-text"]')
  await text.fill(PRE_CODE_YAML)
  await expect(text).toHaveValue(/^schema_version: 1/)
  await page.locator('[data-testid="yaml-apply"]').click()
  await page.locator('[data-testid="tab-canvas"]').click()
  await expect(page.locator('[data-testid="graph-editor-view"] [data-testid="graph-node"]')).toHaveCount(8)
  // Text that does not parse: errors with a line, canvas disabled.
  await page.locator('[data-testid="tab-yaml"]').click()
  await text.fill('schema_version: 1\nnodes: [\n')
  await page.locator('[data-testid="yaml-apply"]').click()
  await expect(page.locator('[data-testid="editor-state"]')).toHaveAttribute('data-state', 'text_broken')
  await expect(page.locator('[data-testid="yaml-error"]').first()).toContainText('line 3')
  await page.locator('[data-testid="tab-canvas"]').click()
  await expect(page.locator('[data-testid="canvas-disabled"]')).toBeVisible()
  await expect(page.locator('[data-testid="graph-editor-view"] [data-testid="graph-canvas"]')).toHaveCount(0)
})

test('an inspector edit applies through the parse and commits', async ({ page }) => {  // clause: CONSOLE-9
  // Recorded flow (E-76 spec §7.2): a fully positioned graph, no drag before
  // apply, one touched field -- exactly objects/pre_code_architecture_soft.
  // The pasted scenario's parse associates its sha; the touched-field object
  // is its own recording, so the commit moves the sha.
  await pasteRecordedGraph(page)
  const sha = page.locator('[data-testid="editor-sha"]')
  await expect(sha).toHaveCount(1)
  const before = await sha.textContent()
  await page.locator('[data-testid="graph-node"][data-key="architecture"] .title').click()
  const inspector = page.locator('[data-testid="graph-inspector"]')
  await inspector.locator('[data-path="gate.policy"] select').selectOption('soft')
  await inspector.locator('[data-testid="inspector-apply"]').click()
  await expect(sha).toHaveCount(1)
  expect(await sha.textContent()).not.toBe(before)
  await expect(inspector.locator('[data-testid="field-error"]')).toHaveCount(0)
  await expect(inspector.locator('[data-testid="inspector-apply"]')).toBeDisabled()
})

test('a graph run renders its nodes and its curved backward edges', async ({ page }) => {  // clause: CONSOLE-4
  await page.goto('/#/runs/feature-graph-demo')
  const canvas = page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')
  // The recorded default graph: 12 nodes, the 2 revise loops curved. The
  // blocked projection carries no traversals, so no counter renders here --
  // the counter feature stays pinned by GRAPH_CANVAS-3 (showcase) and the
  // adapter rows over the escalated recording.
  await expect(canvas.locator('[data-testid="graph-node"]')).toHaveCount(12)
  await expect(canvas.locator('.cmp-graph-edge-backward')).toHaveCount(2)
  await expect(canvas.locator('.cmp-graph-node-blocked')).toHaveCount(1)
  await expect(canvas.locator('.cmp-graph-node-skipped')).toHaveCount(1)
})

test('run-state re-renders never drop the canvas edges', async ({ page }) => {  // clause: GRAPH_CANVAS-9
  // Regression (2026-09-14): RunView's elapsed clock re-renders every second;
  // replacing vue-flow's element arrays on each tick dropped every edge.
  await page.clock.install()
  await page.goto('/#/runs/feature-graph-demo')
  const canvas = page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(20)
  // Fire RunView's 1 s clock deterministically -- no sleep, no flake budget.
  await page.clock.runFor(5000)
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(20)
  await expect(canvas.locator('.cmp-graph-node-blocked')).toHaveCount(1)
})

test('deciding the pending gate from the canvas clears it', async ({ page }) => {  // clause: CONSOLE-5
  await page.goto('/#/runs/feature-graph-demo')
  const gate = page.locator('[data-testid="run-view"] [data-testid="gate-decision"]')
  await expect(gate).toHaveCount(1)
  await gate.locator('[data-testid="gate-approve"]').click()
  await expect(gate).toHaveCount(0)
  // The recorded completed projection: the gate resolves, every node of the
  // run's graph is done except the skipped context leg.
  await expect(page.locator('[data-testid="run-view"] .cmp-graph-node-done')).toHaveCount(11)
  await expect(page.locator('[data-testid="run-view"] .cmp-graph-node-skipped')).toHaveCount(1)
})

test('a legacy run shows the no-graph empty state and the strip', async ({ page }) => {  // clause: CONSOLE-6
  await page.goto('/#/runs/feature-add-sso')
  await expect(page.locator('[data-testid="run-graph-empty"]')).toBeVisible()
  await expect(page.locator('[data-testid="run-view"] [data-testid="stage-dot"]')).toHaveCount(18)
  await expect(page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')).toHaveCount(0)
})

test('the run view offers no edit affordance and opens a copy in the editor', async ({ page }) => {  // clause: CONSOLE-8
  await page.goto('/#/runs/feature-graph-demo')
  const view = page.locator('[data-testid="run-view"]')
  await expect(view.locator('.vue-flow__node.draggable')).toHaveCount(0)
  await expect(view.locator('.vue-flow__handle.connectable')).toHaveCount(0)
  await expect(view.locator('[data-testid="node-palette"]')).toHaveCount(0)
  await view.locator('[data-testid="open-copy"]').click()
  await expect(page.locator('[data-testid="graph-editor-view"]')).toBeVisible()
  await expect(page.locator('[data-testid="editor-state"]')).toHaveAttribute('data-state', 'graph_loaded')
  await expect(page.locator('[data-testid="graph-editor-view"] [data-testid="graph-node"]')).toHaveCount(12)
  await expect(page.locator('[data-testid="editor-sha"]')).toHaveCount(0)
})


test('the elapsed clock flows while the canvas structure survives a minute of ticks', async ({ page }) => {  // clause: GRAPH_CANVAS-9
  // Positive control for the regression above: a fix that silenced the clock
  // would also keep the edges. 70 fired seconds must move the minute-grain
  // elapsed readout AND leave every edge in place.
  await page.clock.install()
  await page.goto('/#/runs/feature-graph-demo')
  const canvas = page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')
  const metrics = canvas.locator('[data-key="architecture"] [data-testid="node-metrics"]')
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(20)
  const before = await metrics.textContent()
  await page.clock.runFor(70_000)
  const after = await metrics.textContent()
  expect(after).not.toBe(before)  // the clock really ticks
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(20)
  await expect(canvas.locator('.cmp-graph-node-blocked')).toHaveCount(1)
})

test('a gate decision shows its busy window before the state clears it', async ({ page }) => {  // clause: CONSOLE-5
  await page.goto('/#/runs/feature-graph-demo')
  const gate = page.locator('[data-testid="run-view"] [data-testid="gate-decision"]')
  await expect(gate).toHaveCount(1)
  await gate.locator('[data-testid="gate-approve"]').click()
  // In flight: the controls lock at once, so a rapid second submit cannot fire.
  await expect(gate.locator('[data-testid="gate-approve"]')).toBeDisabled()
  await expect(gate).toHaveCount(0)  // then the next state clears the whole control
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
  // The header title and strip persist above the tab bar on every tab (FR-018).
  await expect(page.locator('[data-testid="run-view"] [data-testid="stage-dot"]')).toHaveCount(18)
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

// --- The Cost tab (011 T010): the budget run is the seeded
// feature-graph-demo (blocked, three roles, one not-priced); the no-budget
// run is the closed feature-dark-mode. Both are non-running, so the mock
// ticker never moves their figures.

test('the Cost tab lists the roles, the total, and reopens from a copied URL', async ({ page }) => {  // clause: CONSOLE-24
  await page.goto('/#/runs/feature-graph-demo?tab=cost')
  const tab = page.locator('[data-testid="cost-tab"]')
  await expect(tab).toBeVisible()
  await expect(tab.locator('[data-testid="cost-row"]')).toHaveCount(3)
  const total = tab.locator('[data-testid="cost-total-price"]')
  await expect(total).toBeVisible()
  await expect(total).toContainText('2.60')
  // A copied URL reopens the tab (SC-005 for cost).
  await page.reload()
  await expect(page.locator('[data-testid="cost-tab"]')).toBeVisible()
})

test('the budget block counts the dollars, the share, the crossings and the scope', async ({ page }) => {  // clause: CONSOLE-26
  await page.goto('/#/runs/feature-graph-demo?tab=cost')
  const budget = page.locator('[data-testid="cost-tab"] [data-testid="cost-budget"]')
  await expect(budget).toContainText('20.00')
  await expect(budget).toContainText('40.00')
  const counted = page.locator('[data-testid="cost-budget-counted"]')
  await expect(counted).toContainText('counted toward budget')
  await expect(counted).toContainText('2.60')
  // Whole percent of the CURRENT limit (2.6 of 40 -> 6%), never cost/budget.
  await expect(page.locator('[data-testid="cost-budget-pct"]')).toHaveText(/^\d+%$/)
  await expect(page.locator('[data-testid="cost-budget-crossings"]')).toContainText('1')
  await expect(page.locator('[data-testid="cost-budget-note"]')).not.toBeEmpty()
  // A closed run without a budget says so and how one is set.
  await page.goto('/#/runs/feature-dark-mode?tab=cost')
  const none = page.locator('[data-testid="cost-tab"] [data-testid="cost-budget"]')
  await expect(none).toContainText('No budget')
  await expect(none).toContainText('start form')
})

test('a missing price reads "not priced" and no figure on the tab is $0.00', async ({ page }) => {  // clause: CONSOLE-25
  await page.goto('/#/runs/feature-graph-demo?tab=cost')
  // The unpriced dev role states the absence in words, never as dollars.
  const rowPrices = page.locator('[data-testid="cost-row-price"]')
  await expect(rowPrices.filter({ hasText: 'not priced' }).first()).toBeVisible()
  // The total says what it left out: partial.
  await expect(page.locator('[data-testid="cost-total-price"]')).toContainText('partial')
  // And nowhere on the tab does a figure read exactly $0.00 (FR-003).
  const priceEls = page.locator('[data-testid="cost-row-price"], [data-testid="cost-total-price"]')
  const count = await priceEls.count()
  expect(count).toBeGreaterThan(0)
  for (let i = 0; i < count; i++) {
    expect(await priceEls.nth(i).textContent()).not.toContain('$0.00')
  }
})

test('the header spend states how many runs it left out', async ({ page }) => {  // clause: CONSOLE-27
  await page.goto('/')
  const stats = page.locator('.cmp-app-header .stats')
  // The spend figure names the excluded runs ("N not priced") rather than
  // summing them in as zeros; the dollar sum itself is ticker-fed on running
  // seeds, so only the exclusion wording is pinned here.
  await expect(stats).toContainText('not priced')
})
