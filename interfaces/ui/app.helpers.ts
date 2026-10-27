// Shared setup for the app-tier screen specs (018 T008, spec C §6): the net
// stretched over the pages that ship. Every other Playwright spec here
// asserts a profile in the showcase; the app.<screen>.pw.ts files drive the
// real SPA — the dashboard build served on 4174 by the second webServer in
// playwright.config.ts, with VITE_API=mock baked in at build time so the
// whole console runs headless with no backend.
//
// Canvas run-mode wiring (E75-OQ-1, 2026-09-20): the mock's demo run is the
// RECORDED default graph (12 nodes, 20 edges, 2 back loops, no traversals in
// the blocked projection), and its script is blocked -approve-> completed /
// -reject-> rejected. The editor flows paste the recorded pre_code scenario
// text (the demo run's graph has no recorded serialization — the mock's
// honest fallback is non-canonical JSON, which is not canvas-parseable).
import { expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

export const APP_BASE_URL = 'http://localhost:4174'

export const PRE_CODE_YAML = (JSON.parse(readFileSync(fileURLToPath(new URL(
  '../dashboard/frontend/src/api/__fixtures__/graph/scenarios/pre_code.json',
  import.meta.url,
)), 'utf8')) as { yaml: string }).yaml

export async function pasteRecordedGraph(page: Page) {
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
