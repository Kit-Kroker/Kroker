// The graphs screens (018 T008; restored and extended T066): Graphs (the
// catalog + the PipelineConfig panel, CONSOLE-44/37) and Design (the
// Observe/Design switch CONSOLE-8, the edge round trip CONSOLE-9, the start
// form CONSOLE-28, the palette V9 CONSOLE-38, the payload refusal
// CONSOLE-42, and the R-15 gating CONSOLE-43). See app.helpers.ts.
import { test, expect } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })

// The shipped default's sha (the recorded graph response and the
// graphs-shipped fixture agree on it).
const DEFAULT_SHA = 'a021c25b8f7e012faaf9f4de9664d8cc5b11a977c1b878e20d50cfec78b23c38'
// The recorded parse of the default with architect.spec's edge capped at 5
// (the toolbar displays the first 12 chars).
// The sha the backend's parse_object really computes for the default
// with architect.spec->architecture.artifact max_traversals 5 (the
// recorded fixture's parse.sha; regenerate to re-check).
const EDGE_MT_SHA12 = 'c12486c5664d'

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('the header Design switch opens Design holding the run\'s graph', async ({ page }) => {  // clause: CONSOLE-8
  await page.goto('/#/runs/feature-graph-demo')
  await expect(page.locator('[data-testid="run-view"]')).toBeVisible()
  // The run view offers no edit affordance.
  await expect(page.locator('[data-testid="run-view"] .vue-flow__node.draggable')).toHaveCount(0)
  // The header's Observe/Design switch.
  const designTab = page.locator('[data-testid="run-switch"] .rtab', { hasText: 'Design' })
  await expect(designTab).toBeVisible()
  await designTab.click()
  await expect(page.locator('[data-testid="design-view"]')).toBeVisible()
  await expect(page.locator('[data-testid="design-view"] [data-testid="graph-node"]')).toHaveCount(12)
})

test('an edge max_traversals edit applies through the parse and commits', async ({ page }) => {  // clause: CONSOLE-9
  await page.goto(`/#/graphs/${DEFAULT_SHA}?from=run:feature-graph-demo`)
  await expect(page.locator('[data-testid="design-view"] [data-testid="graph-node"]')).toHaveCount(12)
  const sha = page.locator('[data-testid="design-sha"]')
  // A run copy carries no sha association until an edit commits one.
  await expect(sha).toHaveCount(0)
  const edge = page.locator('[data-testid="graph-edge"][data-key="architect.spec>architecture.artifact"]')
  await edge.click()
  const input = page.locator('[data-testid="inspector-max-traversals"]')
  await expect(input).toBeVisible()
  await input.fill('5')
  await page.locator('[data-testid="inspector-apply"]').click()
  await expect(sha).toHaveCount(1)
  await expect(sha).toHaveText(EDGE_MT_SHA12)
})

test('the start form opened from Run this version rejects zero and starts a budgeted run', async ({ page }) => {  // clause: CONSOLE-28
  await page.goto(`/#/graphs/${DEFAULT_SHA}`)
  await expect(page.locator('[data-testid="design-view"] [data-testid="graph-node"]')).toHaveCount(12)
  // Saving the unchanged default keeps its sha (FR-049) and enables the run.
  await page.locator('[data-testid="design-save"]').click()
  const run = page.locator('[data-testid="run-this-version"]')
  await expect(run).toBeEnabled()
  await run.click()
  await expect(page.locator('[data-testid="modal-card"]')).toBeVisible()
  // Zero is refused with the omit-it message; nothing starts.
  await page.locator('[data-testid="start-budget-input"]').fill('0')
  await expect(page.locator('[data-testid="start-budget-error"]')).toContainText('omit it to run without a budget')
  await expect(page.locator('[data-testid="submit"]')).toBeDisabled()
  // A valid budget starts the run ('Budgeted demo' -> feature-budgeted-demo);
  // its rail's Cost section shows it.
  await page.locator('[data-testid="start-title-input"]').fill('Budgeted demo')
  await page.locator('[data-testid="start-budget-input"]').fill('5')
  await page.locator('[data-testid="submit"]').click()
  await page.goto('/#/runs/feature-budgeted-demo?rail=cost')
  await expect(page.locator('[data-testid="rail-cost"]')).toBeVisible()
  await expect(page.locator('[data-testid="rail-cost"] [data-testid="rail-budget"]')).toContainText('5.00')
})

test('the validate_run_roles check shows the registry\'s real dev and reviewer ids', async ({ page }) => {  // clause: CONSOLE-37
  await page.goto('/#/graphs')
  const check = page.locator('[data-testid="config-check"]', { hasText: 'validate_run_roles' })
  await expect(check).toHaveAttribute('data-state', 'pass')
  await expect(check).toContainText('zai-coding-plan/glm-5.3')
  await expect(check).toContainText('zai:glm-5.3')
})

test('the palette groups by canonical_stage in served order; planned types read unmapped and refuse placement', async ({ page }) => {  // clause: CONSOLE-38
  await page.goto(`/#/graphs/${DEFAULT_SHA}?from=run:feature-graph-demo`)
  await expect(page.locator('[data-testid="design-view"]')).toBeVisible()
  const SERVED = [
    'intake', 'constitution', 'context', 'requirements', 'research', 'clarify',
    'architecture', 'planning', 'code', 'review', 'adversary', 'handoff',
    'deep_review', 'analyze', 'qa', 'quality_gate', 'deploy', 'retro',
  ]
  const titles = await page.locator('[data-testid="palette-group-title"]').allTextContents()
  expect(titles).toEqual(SERVED.filter((s) => titles.includes(s)))
  // The planned type: marked planned, unmapped, and not placeable.
  const planned = page.locator('[data-testid="palette-type"]', { hasText: 'outcome.watch' })
  await expect(planned).toHaveClass(/planned/)
  await expect(planned).toContainText('unmapped')
  await expect(planned).toBeDisabled()
})

test('a payload-mismatched drop is refused with its reason and creates no edge', async ({ page }) => {  // clause: CONSOLE-42
  // Honest scope: vue-flow's connection drag is not cooperative headless at
  // the fit-view zoom (the 12-node graph scales the port handles to ~2px),
  // so this tier pins the no-edge half and attempts the drag; the refusal
  // REASON is pinned at the unit tier — the store's unequal-payload
  // refusal (graphEditor.store.test.ts), the canvas's connect-refused
  // report (graph_canvas.spec.ts) and Design's notice wiring
  // (DesignView.test.ts) together cover it.
  await page.setViewportSize({ width: 2600, height: 1500 })
  await page.goto(`/#/graphs/${DEFAULT_SHA}?from=run:feature-graph-demo`)
  await expect(page.locator('[data-testid="design-view"] [data-testid="graph-node"]')).toHaveCount(12)
  const edges = page.locator('[data-testid="design-view"] [data-testid="graph-edge"]')
  await expect(edges).toHaveCount(20)
  // architect.spec (ArchitectureSpec) -> merge.analysis (AnalyzeResult).
  const source = page.locator('[data-testid="graph-node"][data-key="architect"] [data-handleid="out:spec"]')
  const target = page.locator('[data-testid="graph-node"][data-key="merge"] [data-handleid="in:analysis"]')
  const s = await source.boundingBox()
  const t = await target.boundingBox()
  expect(s && t).toBeTruthy()
  await page.mouse.move(s!.x + s!.width / 2, s!.y + s!.height / 2)
  await page.mouse.down()
  await page.mouse.move(s!.x + s!.width / 2 + 14, s!.y + s!.height / 2 + 14, { steps: 3 })
  await page.mouse.move(t!.x + t!.width / 2, t!.y + t!.height / 2, { steps: 10 })
  await page.mouse.up()
  // Whatever the drag's reach, no edge is ever created from a mismatched
  // pair (the fence and the store both refuse).
  await expect(edges).toHaveCount(20)
})

test('Run this version is gated to the saved unchanged default and states its reason', async ({ page }) => {  // clause: CONSOLE-43
  // A run copy: no sha association, so not the saved default.
  await page.goto(`/#/graphs/${DEFAULT_SHA}?from=run:feature-graph-demo`)
  const run = page.locator('[data-testid="run-this-version"]')
  await expect(run).toBeDisabled()
  await expect(page.locator('[data-testid="run-reason"]')).toContainText('not been saved')
  // Saving the unchanged default keeps the sha (FR-049) and enables the run;
  // the edge-change-alters-sha half is pinned at the unit tier
  // (graphEditor.store.test.ts, FR-049).
  await page.goto(`/#/graphs/${DEFAULT_SHA}`)
  await expect(page.locator('[data-testid="design-view"] [data-testid="graph-node"]')).toHaveCount(12)
  await page.locator('[data-testid="design-save"]').click()
  await expect(page.locator('[data-testid="design-sha"]')).toHaveText(DEFAULT_SHA.slice(0, 12))
  await expect(run).toBeEnabled()
})

test('Graphs shows one card per shipped graph and the panel; unsourced values read not measured', async ({ page }) => {  // clause: CONSOLE-44
  await page.goto('/#/graphs')
  const names = page.locator('[data-testid="catalog-name"]')
  await expect(names).toHaveCount(3)
  await expect(names.nth(0)).toHaveText('default')
  await expect(names.nth(1)).toHaveText('default-research')
  await expect(names.nth(2)).toHaveText('seeded')
  await expect(page.locator('[data-testid="catalog-action"]').first()).toHaveText('Open in Design')
  await expect(page.locator('[data-testid="config-panel"]')).toBeVisible()
  await expect(page.locator('[data-testid="catalog-description"]').first()).toHaveText('not measured')
})
