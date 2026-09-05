import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testMatch: '**/*.pw.ts',
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
    },
  ],
})
