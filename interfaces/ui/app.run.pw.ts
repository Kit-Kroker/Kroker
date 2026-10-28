// The run detail screen and its tabs: the canvas, the board's sibling tabs
// and the Cost tab (018 T008, split from app.pw.ts; see app.helpers.ts).
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
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

// --- 018 T043: the CONSOLE-5 tests ('deciding the pending gate from the
// canvas clears it', 'a gate decision shows its busy window before the
// state clears it') were deleted with the interim GateDecision they drove
// (gate-decision / gate-approve test ids); T044 restores the clause on the
// v5 card. CONSOLE-23's inbox half went with T041's inbox tests.

test('selecting a pending node opens its card; deciding closes it and clears the mark', async ({ page }) => {  // clause: CONSOLE-5
  await page.goto('/#/runs/feature-graph-demo')
  // The rail carries one call to action for the recorded pending gate.
  await expect(page.locator('[data-testid="rail-call"]')).toHaveCount(1)
  // Selecting the node with the pending opens the same card over the canvas.
  await page.locator('[data-testid="graph-node"][data-key="architecture"]').dispatchEvent('click')
  const card = page.locator('[data-testid="run-card"]')
  await expect(card).toBeVisible()
  await expect(card).toContainText('architecture#1')
  // Deciding there closes the card, and the next state clears both the
  // call to action and the node's pending mark.
  await card.locator('[data-testid="card-action"]', { hasText: 'Approve' }).click()
  await expect(card).toHaveCount(0)
  await expect(page.locator('[data-testid="rail-call"]')).toHaveCount(0)
  await expect(page.locator('[data-testid="run-view"] [data-testid="pending-mark"]')).toHaveCount(0)
})

test('the rail offers one call to action per pending item, each opening the card', async ({ page }) => {  // clause: CONSOLE-40
  await page.goto('/#/runs/feature-graph-demo')
  const call = page.locator('[data-testid="rail-call"]')
  await expect(call).toHaveCount(1)
  await expect(call).toContainText('architecture#1')
  await call.click()
  const card = page.locator('[data-testid="run-card"]')
  await expect(card).toBeVisible()
  // The card carries the Inbox's actions (the same mapping).
  await expect(card.locator('[data-testid="card-action"]')).toHaveCount(3)
  await expect(card.locator('[data-testid="card-action"]', { hasText: 'Revise' })).toBeDisabled()
})

test('Events lists live decisions with the notes, and closed untimed decisions', async ({ page }) => {  // clause: CONSOLE-41
  // Live (blocked) run: the human decision is timed, and both FR-022
  // notes show.
  await page.goto('/#/runs/feature-graph-demo')
  const events = page.locator('[data-testid="rail-events"]')
  await expect(events).toContainText('revise architecture r1')
  await expect(events).toContainText('Human decisions only while the run is open.')
  await expect(events).toContainText('automatic and timed-out decisions appear when the run ends')
  // Closed run: gates-derived history, untimed, a non-approval reads
  // 'not approved', and no live notes.
  await page.goto('/#/runs/feature-closed-gates')
  const closed = page.locator('[data-testid="rail-events"]')
  await expect(closed).toContainText('approve architecture r1')
  await expect(closed).toContainText('not approved merge r1')
  await expect(closed).not.toContainText('Human decisions only while the run is open.')
})

test('a legacy run shows the no-graph empty state and no canvas', async ({ page }) => {  // clause: CONSOLE-6
  await page.goto('/#/runs/feature-add-sso')
  await expect(page.locator('[data-testid="run-graph-empty"]')).toBeVisible()
  // 018 T032: the run header's stage strip is gone (v5 draws none on the
  // run); the clause keeps its no-graph-empty rule.
  await expect(page.locator('[data-testid="run-view"] [data-testid="stage-dot"]')).toHaveCount(0)
  await expect(page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')).toHaveCount(0)
})

// 018 T063 (S15): the CONSOLE-8 test ('the run view offers no edit
// affordance and opens a copy in the editor') is deleted — it clicked the
// open-copy interim link removed here. T066 restores the clause on the
// header's Observe/Design switch; it reads untested mid-phase, and SG-5
// checks at phase end.

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

// --- The rail's Cost section (018 T033, S3): the CONSOLE-24/25/26 rules
// restored from the retired CostTab (their unit-tier port lives in
// costRail.adapter.test.ts). The budget run is feature-graph-demo; the
// no-budget closed run is feature-dark-mode.

test('the Cost section lists the roles, the total, and both deep links open it', async ({ page }) => {  // clause: CONSOLE-24
  await page.goto('/#/runs/feature-graph-demo?rail=cost')
  const cost = page.locator('[data-testid="rail-cost"]')
  await expect(cost).toBeVisible()
  await expect(cost.locator('.cost-role')).toHaveCount(3)
  await expect(cost.locator('[data-testid="rail-cost-total"]')).toContainText('2.60')
  // The legacy ?tab=cost deep link lands on the same section (SC-005).
  await page.goto('/#/runs/feature-graph-demo?tab=cost')
  await expect(page.locator('[data-testid="rail-cost"]')).toBeVisible()
})

test('a missing price reads "not priced" and no figure in the Cost section is $0.00', async ({ page }) => {  // clause: CONSOLE-25
  await page.goto('/#/runs/feature-graph-demo?rail=cost')
  const cost = page.locator('[data-testid="rail-cost"]')
  await expect(cost.locator('.cost-role .price', { hasText: 'not priced' })).toBeVisible()
  await expect(cost.locator('[data-testid="rail-cost-total"]')).toContainText('partial')
  const prices = cost.locator('.cost-role .price, [data-testid="rail-cost-total"]')
  const count = await prices.count()
  expect(count).toBeGreaterThan(0)
  for (let i = 0; i < count; i++) {
    expect(await prices.nth(i).textContent()).not.toContain('$0.00')
  }
})

test('the budget figures render in the Cost section, or the no-budget sentence', async ({ page }) => {  // clause: CONSOLE-26
  await page.goto('/#/runs/feature-graph-demo?rail=cost')
  const budget = page.locator('[data-testid="rail-cost"] [data-testid="rail-budget"]')
  await expect(budget).toContainText('20.00')
  await expect(budget).toContainText('40.00')
  await expect(budget).toContainText('2.60')
  await expect(budget).toContainText('6%')
  await expect(budget).toContainText('1')
  await expect(budget.locator('.note')).not.toBeEmpty()
  // A closed run without a budget says so and how one is set.
  await page.goto('/#/runs/feature-dark-mode?rail=cost')
  await expect(page.locator('[data-testid="rail-cost"]')).toContainText('No budget')
  await expect(page.locator('[data-testid="rail-cost"]')).toContainText('start form')
})

// --- The Observe outcome fixtures (018 T033, V1-V3/V6). Each V test
// asserts the right element AND the absence of the wrong one (R-11).

test('V1: a halted run lights the failed sink with its result; nothing is labelled halted', async ({ page }) => {  // clause: CONSOLE-30
  await page.goto('/#/runs/feature-halted-demo')
  const failedSink = page.locator('[data-testid="graph-node"][data-key="sink-failed"]')
  await expect(failedSink).toBeVisible()
  await expect(failedSink.locator('[data-testid="sink-outcome"]')).toHaveText('failed')
  await expect(failedSink.locator('[data-testid="sink-sub"]')).toHaveText('failed:quarantined-tasks')
  await expect(failedSink).toHaveClass(/cmp-graph-sink-lit/)
  // The wrong outcomes stay unlit and nothing anywhere reads 'halted'.
  await expect(page.locator('[data-testid="run-view"] .cmp-graph-sink-lit')).toHaveCount(1)
  const sinks = page.locator('[data-testid="run-view"] [data-testid="sink-outcome"]')
  await expect(sinks).toHaveCount(4)
  for (const wrong of ['halted', 'sink-halted']) {
    await expect(page.locator(`[data-testid="run-view"] [data-testid="graph-node"][data-key="${wrong}"]`)).toHaveCount(0)
  }
  expect(await page.locator('[data-testid="run-view"]').innerText()).not.toContain('halted')
})

test('V2: a revise edge at its limit warns, and the escalated sink lights', async ({ page }) => {  // clause: CONSOLE-31
  await page.goto('/#/runs/feature-escalated-demo')
  await expect(page.locator('[data-testid="run-view"] [data-testid="edge-note"]')).toHaveText('next revise escalates the run')
  const escalated = page.locator('[data-testid="graph-node"][data-key="sink-escalated"]')
  await expect(escalated).toHaveClass(/cmp-graph-sink-lit/)
  await expect(page.locator('[data-testid="graph-node"][data-key="sink-failed"]')).not.toHaveClass(/cmp-graph-sink-lit/)
})

test('V3: the completed sink lists every node that completed the run', async ({ page }) => {  // clause: CONSOLE-32
  await page.goto('/#/runs/feature-multisink-demo')
  const completed = page.locator('[data-testid="graph-node"][data-key="sink-completed"]')
  await expect(completed).toHaveClass(/cmp-graph-sink-lit/)
  const sub = await completed.locator('[data-testid="sink-sub"]').innerText()
  expect(sub).toContain('plan')
  expect(sub).toContain('deploy')
  // The wrong outcomes stay unlit.
  await expect(page.locator('[data-testid="run-view"] .cmp-graph-sink-lit')).toHaveCount(1)
})

test('V6: with no budget the rail reads off and draws no bar', async ({ page }) => {  // clause: CONSOLE-35
  await page.goto('/#/runs/feature-dark-mode')
  await expect(page.locator('[data-testid="rail-budget"]')).toContainText('off')
  await expect(page.locator('[data-testid="rail-budget-bar"]')).toHaveCount(0)
  // Slice 4 (T050): a rejected:budget run shows that string on Fleet.
  await page.goto('/')
  const row = page.locator('[data-testid="fleet-row"]', { hasText: 'Rejected at the budget gate' })
  await expect(row.locator('.col-outcome')).toHaveText('rejected:budget')
})

// --- The inspector (018 T033, S13/CONSOLE-49) and the rail's remaining
// sections (CONSOLE-51/52).

test('the inspector marks a configured-vs-answering difference; the code node shows the read-only inner loop', async ({ page }) => {  // clause: CONSOLE-49
  await page.goto('/#/runs/feature-graph-demo')
  // dispatchEvent: the node can sit partly clipped by the canvas pane's
  // overflow; a plain DOM click still bubbles to vue-flow's node handler.
  await page.locator('[data-testid="graph-node"][data-key="architect"]').dispatchEvent('click')
  const inspector = page.locator('[data-testid="run-inspector"]')
  await expect(inspector).toBeVisible()
  // The mock seeds the architect role on model 'm'; the catalog's default
  // is 'architect' — the difference is marked.
  await expect(inspector.locator('[data-testid="inspector-configured"]')).toHaveText('architect')
  await expect(inspector.locator('[data-testid="inspector-answering"]')).toHaveText('m')
  await expect(inspector.locator('[data-testid="inspector-model-diff"]')).toBeVisible()
  // The code node: the inner loop is read-only (the empty list is honest —
  // its step wire arrives with the card slice; assert the list is present
  // with no button anywhere).
  await page.locator('[data-testid="graph-node"][data-key="code"]').dispatchEvent('click')
  await expect(page.locator('[data-testid="run-inspector"] .cmp-step-list')).toBeAttached()
  await expect(page.locator('[data-testid="run-inspector"] button')).toHaveCount(0)
})

test('a retention-expired state shows its reason under the run block, with an empty canvas', async ({ page }) => {  // clause: CONSOLE-51
  await page.goto('/#/runs/feature-retired-demo')
  const note = page.locator('[data-testid="run-graph-state-unavailable"]')
  await expect(note).toBeVisible()
  await expect(note).toContainText('no longer available')
  // R-5a: the reason lives under the rail's run block.
  await expect(note).toHaveClass(/banner/)
  expect(await note.evaluate((el) => (el.closest('[data-testid="rail"]') as HTMLElement | null) !== null)).toBe(true)
  await expect(page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')).toHaveCount(0)
  // The mock never fails a provider read, so the "could not load" half of
  // the clause stays pinned at the unit tier (RunView.test.ts), as
  // CONSOLE-15's positive path is.
})

test('the Cost section lists each revise edge used against max', async ({ page }) => {  // clause: CONSOLE-52
  await page.goto('/#/runs/feature-graph-demo?rail=cost')
  const cost = page.locator('[data-testid="rail-cost"]')
  await expect(cost).toContainText('architecture.revise>architect.guidance')
  await expect(cost).toContainText('0/2')
})
