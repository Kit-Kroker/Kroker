import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testMatch: '**/*.pw.ts',
  // 018 T019: the default (cores/2 = 4 here) opens four Chromium contexts
  // at once; under scripts/check_ui.py — npm ci, vitest for two workspaces
  // and two preview servers on the same machine — the commit charge peaks
  // near 12 GB of pagefile and Chromium dies mid-suite with "Target
  // crashed" on random tests. One worker keeps the peak inside the box's
  // headroom; the suite trades minutes for not crashing.
  workers: 1,
  use: {
    baseURL: 'http://localhost:4173',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: 'npm run build --workspace @kroker/ui && npm run preview --workspace @kroker/ui',
      url: 'http://localhost:4173',
      reuseExistingServer: !process.env.CI,
      // 018 T015: under scripts/check_ui.py the whole machine is busy and
      // the build alone can exceed the 60s default; the build is the slow
      // half, the preview binds in seconds.
      timeout: 240_000,
    },
    {
      // The app tier (app.pw.ts): the real SPA, not the showcase. Vite
      // inlines import.meta.env at BUILD time, so VITE_API has to ride this
      // command (it covers the build half), not the test. Explicit port:
      // vite preview defaults to 4173, which the showcase already holds.
      command:
        'npm run build --workspace sdlc-dashboard && npm run preview --workspace sdlc-dashboard -- --port 4174 --strictPort',
      url: 'http://localhost:4174',
      reuseExistingServer: !process.env.CI,
      env: { VITE_API: 'mock' },
      timeout: 240_000,
    },
  ],
})
