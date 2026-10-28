// Shared setup for the app-tier screen specs (018 T008, spec C §6): the net
// stretched over the pages that ship. Every other Playwright spec here
// asserts a profile in the showcase; the app.<screen>.pw.ts files drive the
// real SPA — the dashboard build served on 4174 by the second webServer in
// playwright.config.ts, with VITE_API=mock baked in at build time so the
// whole console runs headless with no backend.
//
// 018 T063: the YAML paste helper (PRE_CODE_YAML + pasteRecordedGraph) is
// deleted with the YAML pane (S15); the Design flows load through the run
// graph or the catalog, never pasted text.
export const APP_BASE_URL = 'http://localhost:4174'
